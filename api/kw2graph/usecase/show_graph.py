from kw2graph import config
from kw2graph.domain.graph_fetcher import GraphFetcherService
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository
from kw2graph.usecase.base import UseCaseBase
from kw2graph.usecase.input.show_graph import ShowGraphInput
from kw2graph.usecase.output.show_graph import ShowGraphOutput


class ShowGraphUseCase(UseCaseBase):
    def __init__(self, settings: config.Settings, graph_repo: GraphDatabaseRepository):
        super().__init__(settings)
        self.fetcher = GraphFetcherService(settings, graph_repo=graph_repo)

    async def execute(self, in_data: ShowGraphInput) -> ShowGraphOutput:
        # ドメインサービスからグラフデータを取得
        graph_data = await self.fetcher.fetch(in_data)
        # 辞書の結果をPydanticモデルに変換して返す
        return ShowGraphOutput(
            nodes=graph_data.get('nodes', []),
            edges=graph_data.get('edges', [])
        )
