import structlog
import asyncio
from typing import List, Dict, Any, Set

from gremlin_python.driver import client, serializer
from gremlin_python.driver.client import Client
from gremlin_python.driver.resultset import ResultSet
from gremlin_python.process.graph_traversal import __, constant

from kw2graph import config
from kw2graph.infrastructure.base import RepositoryBase

logger = structlog.get_logger(__name__)

# 関連語句の抽出結果の型定義
ExtractionResult = List[Dict[str, Any]]
# 表示用のグラフ構造の型を定義
GraphData = Dict[str, List[Dict[str, Any]]]


class GraphDatabaseRepository(RepositoryBase):
    """
    Gremlin互換のグラフデータベースに接続するリポジトリ。
    I/Oはasyncio.to_thread()を使って非同期ループから分離する。
    """

    NODE_LABEL_KEYWORD = 'Keyword'
    NODE_LABEL_CATEGORY = 'Category'
    NODE_LABEL_CHANNEL = 'Channel'
    EDGE_LABEL_RELATED = 'RELATED_TO'
    EDGE_LABEL_IS_A = 'IS_A'
    EDGE_LABEL_BELONGS_TO = 'BELONGS_TO'

    def __init__(self, settings: config.Settings, client_instance: Client):
        super().__init__(settings)
        self.endpoint = settings.graphdb_host
        self.port = settings.graphdb_port
        self.url = f'ws://{self.endpoint}:{self.port}/gremlin'

        logger.info("Initializing GraphDatabaseRepository (Thread-Safe Client)", url=self.url)
        self.client: Client = client_instance

    # --- 同期 Gremlin I/O実行メソッド ---
    def _sync_execute_gremlin(self, query: str) -> List[Any]:
        """Gremlinクエリを同期的に実行します。"""
        if not self.client:
            raise ConnectionError("Gremlin Client is not initialized.")

        try:
            results: ResultSet = self.client.submit(query)
            return results.all().result()
        except Exception as e:
            logger.error("Synchronous Gremlin query execution failed.", query=query, error=str(e))
            raise

    # --- 非同期ラッパーメソッド ---

    async def _execute_gremlin(self, query: str) -> List[Any]:
        """非同期でスレッドプールにGremlin I/Oを投げる"""
        try:
            return await asyncio.to_thread(self._sync_execute_gremlin, query)
        except Exception as e:
            raise e

    async def upsert_node(self, label: str, name: str, properties: Dict[str, Any] = None) -> str:
        """
        指定されたラベルのノードをUpsertし、そのIDを返します。
        ノードが存在する場合も、propertiesを上書き更新します。
        """
        properties = properties or {}

        # 1. プロパティ更新用の Gremlin ステップを構築 (prop_parts)
        prop_parts = ""
        for key, value in properties.items():

            if isinstance(value, list):
                # iab_categoriesなどのマルチプロパティ対応: 各要素に対して property() を繰り返す
                for item in value:
                    # Gremlin構文: .property('key', 'value')
                    quoted_item = f"'{item}'"
                    prop_parts += f".property('{key}', {quoted_item})"

            elif isinstance(value, str):
                # entity_typeなどのシングルプロパティ
                gremlin_value = f"'{value}'"
                prop_parts += f".property('{key}', {gremlin_value})"

            else:
                # 数値などのプリミティブ型
                gremlin_value = str(value)
                prop_parts += f".property('{key}', {gremlin_value})"

        # 2. Gremlin Upsert クエリの構築: 検索/作成後に属性を適用 (FINAL FIX)
        upsert_query = (
            f"g.V().has('{label}', 'name', '{name}')"
            f".fold().coalesce("
            f"  unfold(),"  # 既存ノードを見つける
            f"  addV('{label}').property('name', '{name}')"  # ノードがなければ 'name' のみで新規作成
            f")"
            f"{prop_parts}"  # ★ 修正: coalesce の外で、既存ノードまたは新規ノードの両方にプロパティを適用
            f".id()"  # 最終的にノードのIDを返す
        )

        try:
            results = await self._execute_gremlin(upsert_query)
            return str(results[0]) if results else None
        except Exception as e:
            logger.error("Synchronous Gremlin query execution failed.", query=upsert_query, error=str(e))
            raise

    # -----------------------------------------------------------------
    # ★ 修正: エッジ Upsert メソッドを分離・汎用化 (汎用化)
    # -----------------------------------------------------------------

    async def upsert_edge(self, from_id: str, to_id: str, label: str, score: float = None) -> None:
        """
        2つのノード間にエッジをUpsertします。
        """
        # エッジのプロパティとしてスコアを含めるか判断
        score_prop = f".property('score', {score})" if score is not None else ""

        # Gremlin Edge Upsert クエリの構築
        edge_upsert_query = (
            f"g.V('{from_id}').as('a').V('{to_id}').coalesce("
            # 1. 既存エッジを探す
            f"  inE('{label}').where(outV().is('a')),"
            # 2. なければ新しいエッジを作成し、プロパティを設定
            f"  addE('{label}').from('a')"
            # 3. どちらの場合もスコアプロパティを更新（scoreがない場合は更新しない）
            f"){score_prop}"
        )

        await self._execute_gremlin(edge_upsert_query)

    # -----------------------------------------------------------------
    # ★ 修正: メイン登録メソッドのロジック変更 (DIによるノード/エッジ登録)
    # -----------------------------------------------------------------

    async def register_related_keywords(self,
                                        seed_keyword: str,
                                        extracted_data: ExtractionResult,
                                        channel_name: str = None) -> bool:  # ★ チャンネル名パラメータ追加
        """
        GPTから抽出されたデータとチャネル名をグラフに登録します。
        """
        logger.info("Starting registration to GraphDB.", seed_keyword=seed_keyword)

        try:
            # 1. シードキーワードノードのUpsert
            seed_node_id = await self.upsert_node(self.NODE_LABEL_KEYWORD, seed_keyword)
            if not seed_node_id:
                logger.error("Failed to upsert seed keyword node.", keyword=seed_keyword)
                return False

            # 2. チャンネルノードと BELONGS_TO エッジの Upsert (サービス固有のドメイン知識)
            if channel_name:
                channel_node_id = await self.upsert_node(self.NODE_LABEL_CHANNEL, channel_name, {'platform': 'YouTube'})
                if channel_node_id:
                    # シードキーワードからチャンネルへの関連付け (スコアは不要)
                    await self.upsert_edge(seed_node_id, channel_node_id, self.EDGE_LABEL_BELONGS_TO)

            # 3. 各関連キーワードの Upsert とエッジ作成
            for item in extracted_data:
                related_keyword = item['keyword']
                score = item['score']
                entity_type = item.get('entity_type', 'General')  # 存在しない場合は 'General'
                iab_categories = item.get('iab_categories', [])  # 存在しない場合は空リスト

                # Categoryノード用の名前を取得（IABカテゴリの最初の要素をカテゴリ名として利用する）
                category_name = iab_categories[0] if iab_categories else None

                # ノードに渡すプロパティを構築
                node_properties = {
                    'entity_type': entity_type,
                    # リスト型プロパティは Gremlin で multi-property として格納される
                    'iab_categories': iab_categories
                }

                # A. 関連キーワードノードのUpsert
                # ★ 修正: 属性を渡してノードをUpsert
                related_node_id = await self.upsert_node(
                    self.NODE_LABEL_KEYWORD,
                    related_keyword,
                    properties=node_properties
                )

                if related_node_id:
                    # B. RELATED_TO エッジのUpsert (GPTスコアを使用)
                    await self.upsert_edge(seed_node_id, related_node_id, self.EDGE_LABEL_RELATED, score=score)

                    # C. IS_A エッジのUpsert (カテゴリ階層: IABのTier 1をCategoryノードとして利用)
                    if category_name:
                        # CategoryノードのUpsert (カテゴリ名は IAB Tier 1 を利用)
                        category_node_id = await self.upsert_node(self.NODE_LABEL_CATEGORY, category_name)
                        if category_node_id:
                            # 関連キーワードからカテゴリへの階層エッジを登録 (スコアは不要)
                            await self.upsert_edge(related_node_id, category_node_id, self.EDGE_LABEL_IS_A)

            logger.info("GraphDB registration finished successfully.", seed_keyword=seed_keyword)
            return True

        except Exception as e:
            logger.error("GraphDB registration failed due to a critical error.", seed_keyword=seed_keyword,
                         error=str(e))
            return False

    # --- グラフ取得メソッド ---

    async def fetch_related_graph(
            self,
            seed_keyword: str,
            max_depth: int = 2,
            min_score: float = 0.0,
            entity_type: str | None = None,
            iab_category: str | None = None
    ) -> GraphData:
        logger.info("Fetching graph data with filters.",
                    seed_keyword=seed_keyword,
                    max_depth=max_depth,
                    min_score=min_score,
                    entity_type=entity_type,
                    iab_category=iab_category)

        # フィルタリング条件のGremlinクエリ部品を構築

        # 1. ノードフィルタ部品 (entity_type, iab_category)
        # ノード取得後の project/by ステップでも使用するため、必要なプロパティも project で取得するように修正
        node_filter_parts = ""

        # a) entity_type フィルタ
        if entity_type:
            node_filter_parts += f".has('entity_type', '{entity_type}')"

        # b) iab_category フィルタ (iab_categoriesはリストプロパティと仮定)
        if iab_category:
            # iab_categories リストの中に指定されたカテゴリが含まれているノードのみを選択
            node_filter_parts += f".where(values('iab_categories').unfold().is('{iab_category}'))"

        # 2. エッジフィルタ部品 (min_score)
        # score プロパティが min_score 以上であること
        edge_filter_parts = f".has('{self.EDGE_LABEL_RELATED}', 'score', gt({min_score}))"

        # ----------------------------------------------------
        # 3. ノード取得クエリの実行
        # ----------------------------------------------------

        # ノード取得クエリ: (最終修正版 - constant() を使用)
        nodes_query = (
            f"g.V().has('{self.NODE_LABEL_KEYWORD}', 'name', '{seed_keyword}')"
            f"{node_filter_parts}.as('start')."
            f"repeat(both('{self.EDGE_LABEL_RELATED}')).times({max_depth}).emit()."
            f"union(identity(), select('start'))."
            f"dedup()"
            f"{node_filter_parts}"
            f".project('id', 'name', 'entity_type', 'iab_categories')"
            f".by(id())"
            f".by(coalesce(values('name'), constant('')))"

            f".by(coalesce(values('entity_type'), __.constant('')))"  # __.constant('') を使用
            f".by(values('iab_categories').fold().coalesce(unfold(), __.constant([])))"  # __.constant([]) を使用
            f".toList()"
        )

        # ----------------------------------------------------
        # 4. エッジ取得クエリの実行
        # ----------------------------------------------------

        # エッジ取得クエリ: (安定版をベースにスコアフィルタを追加)
        edges_query = (
            f"g.V().has('{self.NODE_LABEL_KEYWORD}', 'name', '{seed_keyword}')."
            f"repeat(bothE('{self.EDGE_LABEL_RELATED}').otherV()).times({max_depth})."
            f"bothE('{self.EDGE_LABEL_RELATED}').dedup()"
            f"{edge_filter_parts}"  # エッジフィルタ（min_score）を適用
            f".project('id', 'score', 'from_id', 'to_id')"
            f".by(id())"
            f".by(coalesce(values('score'), constant(0.0)))"
            f".by(__.outV().id())"
            f".by(__.inV().id())"
            f".toList()"
        )

        # ----------------------------------------------------
        # 5. 実行と結果の整形
        # ----------------------------------------------------

        try:
            raw_nodes = await self._execute_gremlin(nodes_query)
            raw_edges = await self._execute_gremlin(edges_query)
        except Exception as e:
            logger.error("Failed to fetch graph data from Gremlin (Filtered Query).", error=str(e))
            return {"nodes": [], "edges": []}

        # 6. 結果の整形（Python側で結合と型変換）
        nodes = {}
        edges = []

        # ノード整形 (Long IDをStringに、nameをlabelに, プロパティを追加)
        for item in raw_nodes:
            iab_categories_raw = item.get('iab_categories')

            # 💡 修正: iab_categories がリストでない (単一の文字列である) 場合はリスト化
            if iab_categories_raw is None:
                # Gremlinから何も返されなかった場合（属性なしノード）
                final_iab_categories = []
            elif isinstance(iab_categories_raw, str):
                # 単一の文字列が返された場合（プロパティが一つだけの場合）
                final_iab_categories = [iab_categories_raw]
            elif not isinstance(iab_categories_raw, list):
                # リストでないが None/str でもない予期せぬ型の場合、リストに変換 (安全策)
                final_iab_categories = [str(iab_categories_raw)]
            else:
                # 既にリストである場合
                final_iab_categories = iab_categories_raw

            node_id = str(item.get('id'))
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": item.get('name'),
                    "group": self.NODE_LABEL_KEYWORD,  # ノードラベルは 'Keyword' で固定
                    "entity_type": item.get('entity_type'),  # ★ 新しいプロパティ
                    "iab_categories": final_iab_categories  # ★ 新しいプロパティ
                }

        # エッジ整形 (Long IDをStringに、BigDecimalをFloatに)
        for item in raw_edges:
            score_value = item.get('score')

            # BigDecimalをfloatに変換
            if hasattr(score_value, 'unscaled_value') and hasattr(score_value, 'scale'):
                score_float = float(score_value.unscaled_value) / (10 ** score_value.scale)
            else:
                score_float = float(score_value)

            edges.append({
                "id": str(item.get('id')),
                "from_node": str(item.get('from_id')),
                "to_node": str(item.get('to_id')),
                "score": score_float
            })

        # 6. 結果の整形（Python側で結合と型変換）
        nodes = {}
        edges = []

        # ... (既存のノード整形ロジック)
        for item in raw_nodes:
            # ... (iab_categories のリスト化ロジック)

            node_id = str(item.get('id'))
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": item.get('name'),
                    "group": self.NODE_LABEL_KEYWORD,
                    "entity_type": item.get('entity_type'),
                    "iab_categories": final_iab_categories
                }

        # ... (既存のエッジ整形ロジック)
        for item in raw_edges:
            # ... (スコアのfloat変換ロジック)

            edges.append({
                "id": str(item.get('id')),
                "from_node": str(item.get('from_id')),
                "to_node": str(item.get('to_id')),
                "score": score_float
            })

        # ----------------------------------------------------
        # 7. 【追加】孤立ノードの除去 (Orphan Node Removal)
        # ----------------------------------------------------

        # a. フィルタリングされたエッジに含まれるノードIDを収集
        connected_node_ids: Set[str] = set()
        for edge in edges:
            # エッジが残っているなら、その両端のノードは接続されている
            connected_node_ids.add(edge['from_node'])
            connected_node_ids.add(edge['to_node'])

        # b. 接続されたノードのみをフィルタリングして最終リストを作成
        final_nodes = []
        for node_id, node_data in nodes.items():
            # Edgeのいずれかの端点に含まれるノードのみを採用
            if node_id in connected_node_ids:
                final_nodes.append(node_data)

        # 最終的な戻り値として、フィルタリングされたノードとエッジを返す
        return {"nodes": final_nodes, "edges": edges}  # nodes.values() ではなく final_nodes を使用する

    async def get_new_and_eligible_keywords(self,
                                            seed_keyword: str,
                                            min_score: float,
                                            entity_type: str,
                                            max_depth: int = 1) -> List[str]:
        """
        指定された条件に合致し、かつ、まだ起点キーワードとして登録されていない
        新しい（New）の関連キーワードをGraphDBから発見します。

        この処理はブロッキングなので、asyncio.to_thread で呼び出されます。

        :return: 条件を満たす新規キーワードのリスト
        """

        # 1. フィルタリング条件の定義
        # - entity_typeが指定値であること
        # - scoreがmin_score以上であること

        # 2. Gremlin クエリの構築
        # (1) 起点キーワードV1から関連エッジを辿り、ノードV2に到達
        # (2) V2が指定された entity_type を持つことを確認
        # (3) V1->V2のエッジが min_score 以上であることを確認
        # (4) V2を起点として「まだRELATED_TOエッジが出されていない」ことを確認 (新規性チェック)

        query = (
            f"g.V().has('{self.NODE_LABEL_KEYWORD}', 'name', '{seed_keyword}')."
            f"outE('{self.EDGE_LABEL_RELATED}').has('score', gt({min_score})).inV().as('target')."
            f"has('entity_type', '{entity_type}')."
            f"where(outE('{self.EDGE_LABEL_RELATED}').count().is(0))."  # 💡 新規性チェック: ターゲットノードから外向きのエッジがないこと（つまり、まだ起点として使われていない）
            f"values('name').toList()"
        )

        try:
            results = await asyncio.to_thread(self._sync_execute_gremlin, query)
            # results はキーワード名 (str) のリスト
            return [str(name) for name in results]

        except Exception as e:
            logger.error("Failed to fetch new eligible keywords from Gremlin.", error=str(e))
            return []
