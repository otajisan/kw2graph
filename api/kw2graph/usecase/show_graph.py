from typing import List, Dict, Any
from kw2graph import config
from kw2graph.domain.graph_fetcher import GraphFetcherService
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository
from kw2graph.usecase.base import UseCaseBase
from kw2graph.usecase.input.base import InputBase
from kw2graph.usecase.output.base import OutputBase
from pydantic import Field


# --- Input/Output モデル定義 ---

class ShowGraphInput(InputBase):
    """グラフ表示の起点となるキーワードと深さ"""
    seed_keyword: str
    max_depth: int = 2  # デフォルト値を設定


class Node(OutputBase):
    id: str
    label: str
    group: str


class Edge(OutputBase):
    id: str
    from_node: str  # キー名を Gremlin の出力に合わせて from_node に統一
    to_node: str  # キー名を Gremlin の出力に合わせて to_node に統一
    score: float


class ShowGraphOutput(OutputBase):
    nodes: List[Node]
    edges: List[Edge]


class ShowGraphUseCase(UseCaseBase):
    def __init__(self, settings: config.Settings, graph_repo: GraphDatabaseRepository):
        super().__init__(settings)
        self.fetcher = GraphFetcherService(settings, graph_repo=graph_repo)

    async def execute(self, in_data: ShowGraphInput) -> ShowGraphOutput:
        # ドメインサービスからグラフデータを取得
        graph_data = await self.fetcher.fetch(
            in_data.seed_keyword,
            in_data.max_depth  # ★ パラメータを追加
        )
        # 辞書の結果をPydanticモデルに変換して返す
        return ShowGraphOutput(
            nodes=graph_data.get('nodes', []),
            edges=graph_data.get('edges', [])
        )
