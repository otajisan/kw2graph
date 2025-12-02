from kw2graph.domain.base import ServiceBase
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository, GraphData


class GraphFetcherService(ServiceBase):
    def __init__(self, settings):
        super().__init__(settings)
        self.repo = GraphDatabaseRepository(settings)

    async def fetch(self, seed_keyword: str) -> GraphData:
        """
        グラフリポジトリから関連グラフデータを取得する。
        """
        # 現在、特別なドメインロジックはないため、リポジトリを直接呼び出す
        return await self.repo.fetch_related_graph(seed_keyword)
