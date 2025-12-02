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

    NODE_LABEL = 'Keyword'
    EDGE_LABEL = 'RELATED_TO'

    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.endpoint = settings.graphdb_host
        self.port = settings.graphdb_port
        self.url = f'ws://{self.endpoint}:{self.port}/gremlin'

        logger.info("Initializing GraphDatabaseRepository (Thread-Safe Client)", url=self.url)
        self.client: Client = client.Client(
            self.url,
            'g',
            message_serializer=serializer.GraphSONSerializersV3d0()
        )

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

    # ... (upsert_keyword_node, register_related_keywords はそのまま)

    # --- グラフ取得メソッド ---

    async def fetch_related_graph(self, seed_keyword: str, max_depth: int = 2) -> GraphData:
        logger.info("Fetching graph data.", seed_keyword=seed_keyword, max_depth=max_depth)

        # 1. ノード取得クエリ: 起点ノードと max_depth ホップ先のノードをすべて取得
        nodes_query = (
            f"g.V().has('{self.NODE_LABEL}', 'name', '{seed_keyword}').as('start')."
            f"repeat(both('{self.EDGE_LABEL}')).times({max_depth}).emit()."
            f"union(identity(), select('start'))."  # 始点ノードを確実に追加
            f"dedup()."
            f"project('id', 'name')."
            f"by(id())."
            f"by(coalesce(values('name'), constant('')))."
            f"toList()"
        )

        # 2. エッジ取得クエリ: 多ホップで接続されたノード間すべてのエッジを取得
        edges_query = (
            f"g.V().has('{self.NODE_LABEL}', 'name', '{seed_keyword}')."
            f"repeat(bothE('{self.EDGE_LABEL}').otherV()).times({max_depth})."  # ノード間を移動し、emitで経路上のノードを収集
            f"emit()."
            f"bothE('{self.EDGE_LABEL}').dedup()."  # 収集されたノード群からすべての関連エッジを再度取得し、重複を排除
            f"project('id', 'score', 'from_id', 'to_id')."
            f"by(id())."
            f"by(coalesce(values('score'), constant(0.0)))."
            f"by(__.outV().id())."
            f"by(__.inV().id())."
            f"toList()"
        )

        try:
            # 3. 実行
            raw_nodes = await self._execute_gremlin(nodes_query)
            raw_edges = await self._execute_gremlin(edges_query)
        except Exception as e:
            logger.error("Failed to fetch graph data from Gremlin (Final Query).", error=str(e))
            return {"nodes": [], "edges": []}

        # 4. 結果の整形（Python側で結合と型変換）
        nodes = {}
        edges = []

        # ノード整形 (Long IDをStringに、nameをlabelに)
        for item in raw_nodes:
            node_id = str(item.get('id'))
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": item.get('name'),
                    "group": self.NODE_LABEL
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

        return {"nodes": list(nodes.values()), "edges": edges}