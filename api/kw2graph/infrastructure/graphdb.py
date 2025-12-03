import structlog
import asyncio
from typing import List, Dict, Any

from gremlin_python.driver import client, serializer
from gremlin_python.driver.client import Client
from gremlin_python.driver.resultset import ResultSet

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

        :param label: ノードラベル ('Keyword', 'Category', 'Channel'など)
        :param name: ノードのユニーク名
        :param properties: 追加で設定するプロパティ ({'type': '固有名詞'}など)
        """
        properties = properties or {}

        # プロパティ文字列の構築 (name とその他のプロパティ)
        prop_parts = f".property('name', '{name}')"
        for key, value in properties.items():
            # Gremlinクエリインジェクション対策として、文字列値はエスケープが必要ですが、ここでは簡略化
            prop_parts += f".property('{key}', '{value}')"

        # Gremlin Upsert クエリの構築
        upsert_query = (
            f"g.V().has('{label}', 'name', '{name}')"
            f".fold().coalesce("
            f"  unfold(),"  # ノードが存在すればそれを返す
            f"  addV('{label}').property('name', '{name}'){prop_parts}"  # 存在しなければ作成
            f").id()"  # 最終的にノードのIDを返す
        )

        results = await self._execute_gremlin(upsert_query)
        # TinkerPopはIDをLong型で返すことが多いため、str()にキャスト
        return str(results[0]) if results else None

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
                category = item.get('category')  # GPTがcategoryを返すことを想定

                # A. 関連キーワードノードのUpsert
                related_node_id = await self.upsert_node(self.NODE_LABEL_KEYWORD, related_keyword)

                if related_node_id:
                    # B. RELATED_TO エッジのUpsert (GPTスコアを使用)
                    await self.upsert_edge(seed_node_id, related_node_id, self.EDGE_LABEL_RELATED, score=score)

                    # C. IS_A エッジのUpsert (カテゴリ階層)
                    if category:
                        # CategoryノードのUpsert
                        category_node_id = await self.upsert_node(self.NODE_LABEL_CATEGORY, category)
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

        # ノード取得クエリ: (安定版をベースにフィルタを追加)
        nodes_query = (
            f"g.V().has('{self.NODE_LABEL_KEYWORD}', 'name', '{seed_keyword}')"
            f"{node_filter_parts}.as('start')."  # 始点ノードにフィルタを適用
            f"repeat(both('{self.EDGE_LABEL_RELATED}')).times({max_depth}).emit()."
            f"union(identity(), select('start'))."
            f"dedup()"
            f"{node_filter_parts}"  # 移動後のノードにもフィルタを適用
            f".project('id', 'name', 'entity_type', 'iab_categories')"  # 必要なプロパティも取得
            f".by(id())"
            f".by(coalesce(values('name'), constant('')))"
            f".by(coalesce(values('entity_type'), constant('')))"
            f".by(coalesce(values('iab_categories'), constant([])))"  # リストプロパティを返却
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
            node_id = str(item.get('id'))
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": item.get('name'),
                    "group": self.NODE_LABEL_KEYWORD,  # ノードラベルは 'Keyword' で固定
                    "entity_type": item.get('entity_type'),  # ★ 新しいプロパティ
                    "iab_categories": item.get('iab_categories')  # ★ 新しいプロパティ
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

        # 最終的に、フィルタリングされたノードとエッジの接続を確保するため、
        # エッジリストに含まれるノードのみを nodes から抽出することが理想的ですが、
        # Gremlin側でフィルタリングしているため、ここでは単純にノードを返します。
        return {"nodes": list(nodes.values()), "edges": edges}
