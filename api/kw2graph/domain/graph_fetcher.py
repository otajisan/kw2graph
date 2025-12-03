import structlog

from kw2graph.domain.base import ServiceBase
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository, GraphData

logger = structlog.get_logger(__name__)


class GraphFetcherService(ServiceBase):
    def __init__(self, settings, graph_repo: GraphDatabaseRepository):
        super().__init__(settings)
        self.repo = graph_repo

    async def fetch(
            self, seed_keyword: str,
            max_depth: int,
            min_score: float = 0.0,
            entity_type: str | None = None,
            iab_category: str | None = None) -> GraphData:
        """
        グラフリポジトリから関連グラフデータを取得する。
        """
        # 現在、特別なドメインロジックはないため、リポジトリを直接呼び出す
        response = await self.repo.fetch_related_graph(seed_keyword, max_depth, min_score, entity_type, iab_category)

        logger.info(f"fetch {seed_keyword} result: {response}")

        return response
