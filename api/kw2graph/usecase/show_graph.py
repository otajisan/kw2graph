from typing import List, Dict, Any
from kw2graph import config
from kw2graph.domain.graph_fetcher import GraphFetcherService
from kw2graph.usecase.base import UseCaseBase
from kw2graph.usecase.output.base import OutputBase
from pydantic import Field


# --- Input/Output モデル定義 ---

class ShowGraphInput(OutputBase):
    """グラフ表示の起点となるキーワード"""
    seed_keyword: str


class Node(OutputBase):
    id: str
    label: str
    group: str


class Edge(OutputBase):
    id: str
    from_node: str = Field(alias='from')  # グラフ描画ライブラリと合わせるため別名定義
    to_node: str = Field(alias='to')
    score: float


class ShowGraphOutput(OutputBase):
    nodes: List[Node]
    edges: List[Edge]


class ShowGraphUseCase(UseCaseBase):
    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.fetcher = GraphFetcherService(settings)

    async def execute(self, in_data: ShowGraphInput) -> ShowGraphOutput:
        # ドメインサービスからグラフデータを取得
        graph_data = await self.fetcher.fetch(in_data.seed_keyword)

        # 辞書の結果をPydanticモデルに変換して返す
        return ShowGraphOutput(
            nodes=graph_data.get('nodes', []),
            edges=graph_data.get('edges', [])
        )
