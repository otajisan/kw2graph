import structlog
import asyncio
from typing import List, Dict, Any

from gremlin_python.driver import client, serializer
from gremlin_python.driver.client import Client
from gremlin_python.driver.resultset import ResultSet

from kw2graph import config
from kw2graph.infrastructure.base import RepositoryBase

logger = structlog.get_logger(__name__)

# 関連語句の抽出結果の型定義 (OpenAIクライアントと共通)
ExtractionResult = List[Dict[str, Any]]
# 表示用のグラフ構造の型を定義
GraphData = Dict[str, List[Dict[str, Any]]]


class GraphDatabaseRepository(RepositoryBase):
    """
    Gremlin互換のグラフデータベース（例: TinkerPop Gremlin Server）
    に接続し、キーワードと関連度を登録するリポジトリ。
    Gremlin I/Oはasyncio.to_thread()を使って非同期ループから分離される。
    """

    NODE_LABEL = 'Keyword'
    EDGE_LABEL = 'RELATED_TO'

    def __init__(self, settings: config.Settings):
        super().__init__(settings)

        # 設定情報から接続URLを構築
        self.endpoint = settings.graphdb_host
        self.port = settings.graphdb_port
        self.url = f'ws://{self.endpoint}:{self.port}/gremlin'

        logger.info("Initializing GraphDatabaseRepository (Thread-Safe Client)", url=self.url)

        # Gremlinクライアントの作成 (接続テストは行わないレイジーロード)
        self.client: Client = client.Client(
            self.url,
            'g',
            message_serializer=serializer.GraphSONSerializersV3d0()
        )
        # クライアントは __init__ で作成し、クエリ実行時にスレッドプール経由で利用する。

    # --- Gremlin I/Oをスレッドで実行するための内部同期メソッド ---

    def _sync_execute_gremlin(self, query: str) -> List[Any]:
        """Gremlinクエリを同期的に実行します（ThreadPoolExecutor経由で実行されます）。"""
        if not self.client:
            raise ConnectionError("Gremlin Client is not initialized.")

        try:
            # 同期的な client.submit() を使用し、.all().result() で結果を待機
            results: ResultSet = self.client.submit(query)
            # .all().result() はスレッド内部で実行されるため、イベントループはブロックされない
            return results.all().result()
        except Exception as e:
            # Gremlin I/Oエラーを捕捉
            logger.error("Synchronous Gremlin query execution failed.", query=query, error=str(e))
            raise

    # --- 非同期でラップされた実行メソッド ---

    async def _execute_gremlin(self, query: str) -> List[Any]:
        """非同期でスレッドプールにGremlin I/Oを投げる"""

        # asyncio.to_thread() を使ってブロッキングI/O (_sync_execute_gremlin) をバックグラウンドスレッドで実行
        try:
            return await asyncio.to_thread(self._sync_execute_gremlin, query)
        except Exception as e:
            # _sync_execute_gremlin内で発生した例外をそのまま再スロー
            raise e

    # --- 公開メソッド ---

    async def upsert_keyword_node(self, keyword: str) -> str:
        """
        キーワードノードをグラフに登録（Upsert: 存在しなければ作成、存在すれば取得）します。
        """
        query = (
            f"g.V().has('{self.NODE_LABEL}', 'name', '{keyword}')"
            f".fold().coalesce(unfold(),"
            f"addV('{self.NODE_LABEL}').property('name', '{keyword}')).id()"
        )

        results = await self._execute_gremlin(query)
        return results[0] if results else None

    async def register_related_keywords(self, seed_keyword: str, extracted_data: ExtractionResult) -> bool:
        """
        GPTから抽出されたデータ（関連キーワードとスコア）をグラフに非同期で登録します。
        """
        logger.info("Starting registration to GraphDB.", seed_keyword=seed_keyword)

        try:
            # 1. 起点ノードを取得または作成
            seed_node_id = await self.upsert_keyword_node(seed_keyword)
            if not seed_node_id:
                logger.error("Failed to upsert seed keyword node.", keyword=seed_keyword)
                return False

            # 2. 各関連キーワードを登録
            for item in extracted_data:
                related_keyword = item['keyword']
                score = item['score']

                # 関連ノードを取得または作成
                related_node_id = await self.upsert_keyword_node(related_keyword)

                if related_node_id:
                    # 3. エッジ (関連) を作成/更新
                    edge_query = (
                        f"g.V('{seed_node_id}').as('a').V('{related_node_id}').coalesce("
                        f"inE('{self.EDGE_LABEL}').where(outV().is('a')),"
                        f"addE('{self.EDGE_LABEL}').from('a')).property('score', {score})"
                    )

                    await self._execute_gremlin(edge_query)
                    logger.debug("Edge registered.", source=seed_keyword, target=related_keyword, score=score)

            logger.info("GraphDB registration finished successfully.", seed_keyword=seed_keyword)
            return True

        except (ConnectionError, Exception) as e:
            # Gremlin I/Oや接続の問題をここで捕捉
            logger.error("GraphDB registration failed due to an error.", seed_keyword=seed_keyword, error=str(e))
            return False

    async def fetch_related_graph(self, seed_keyword: str) -> GraphData:
        logger.info("Fetching graph data.", seed_keyword=seed_keyword)

        # 1. 接続ノード（Vertex）の取得クエリ
        # 始点ノードとその関連ノードをすべて取得し、ノードIDとプロパティを抽出
        nodes_query = (
            f"g.V().has('{self.NODE_LABEL}', 'name', '{seed_keyword}').as('start')."
            f"union(identity(), both('{self.EDGE_LABEL}'))."  # 起点ノード自身と、両方向に繋がるノードを取得
            f"dedup()."
            f"project('id', 'name')."
            f"by(id())."
            f"by(coalesce(values('name'), constant('')))."
            f"toList()"
        )

        # 2. エッジ（Edge）の取得クエリ
        # 始点ノードから出る/入るエッジを取得し、接続情報とスコアを抽出
        edges_query = (
            f"g.V().has('{self.NODE_LABEL}', 'name', '{seed_keyword}')."
            f"bothE('{self.EDGE_LABEL}').dedup()."
            f"project('id', 'score', 'from_id', 'to_id')."
            f"by(id())."
            f"by(coalesce(values('score'), constant(0.0)))."
            f"by(__.outV().id())."  # ここで outV().id() が実行されるのはエッジに対してなので安全
            f"by(__.inV().id())."
            f"toList()"
        )

        try:
            # 3. 実行
            raw_nodes = await self._execute_gremlin(nodes_query)
            raw_edges = await self._execute_gremlin(edges_query)
        except Exception as e:
            logger.error("Failed to fetch graph data from Gremlin (Split Query).", error=str(e))
            return {"nodes": [], "edges": []}

        # 4. 結果の整形（Python側で結合）
        nodes = {}
        edges = []

        for item in raw_nodes:  # ノード情報の整形
            node_id = str(item.get('id'))  # ★ 修正: IDを文字列にキャスト
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": item.get('name'),
                    "group": self.NODE_LABEL
                }

        # エッジの整形
        for item in raw_edges:
            score_value = item.get('score')

            # BigDecimalをfloatに変換するロジック
            if hasattr(score_value, 'unscaled_value') and hasattr(score_value, 'scale'):
                # GremlinのBigDecimalオブジェクトの場合
                score_float = float(score_value.unscaled_value) / (10 ** score_value.scale)
            else:
                # すでにfloatまたはintの場合
                score_float = float(score_value)

            edges.append({
                "id": str(item.get('id')),  # ★ 修正: IDを文字列にキャスト
                "from_node": str(item.get('from_id')),  # ★ 修正: IDを文字列にキャスト
                "to_node": str(item.get('to_id')),  # ★ 修正: IDを文字列にキャスト
                "score": score_float  # ★ 修正: floatに変換した値を格納
            })

        return {"nodes": list(nodes.values()), "edges": edges}
