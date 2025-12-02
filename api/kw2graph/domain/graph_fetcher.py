import structlog

from kw2graph.domain.base import ServiceBase
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository, GraphData

logger = structlog.get_logger(__name__)


class GraphFetcherService(ServiceBase):
    def __init__(self, settings):
        super().__init__(settings)
        self.repo = GraphDatabaseRepository(settings)

    async def fetch(self, seed_keyword: str) -> GraphData:
        """
        グラフリポジトリから関連グラフデータを取得する。
        """
        # 現在、特別なドメインロジックはないため、リポジトリを直接呼び出す
        response = await self.repo.fetch_related_graph(seed_keyword)

        logger.info(f"fetch {seed_keyword} result: {response}")

        return response
