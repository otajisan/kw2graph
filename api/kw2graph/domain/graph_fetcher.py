import structlog

from kw2graph.domain.base import ServiceBase
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository, GraphData
from kw2graph.usecase.input.show_graph import ShowGraphInput

logger = structlog.get_logger(__name__)


class GraphFetcherService(ServiceBase):
    def __init__(self, settings, graph_repo: GraphDatabaseRepository):
        super().__init__(settings)
        self.repo = graph_repo

    async def fetch(self, in_data: ShowGraphInput) -> GraphData:
        """
        グラフリポジトリから関連グラフデータを取得する。
        """
        # 現在、特別なドメインロジックはないため、リポジトリを直接呼び出す
        response = await self.repo.fetch_related_graph(in_data.seed_keyword, in_data.max_depth, in_data.min_score,
                                                       in_data.entity_type, in_data.iab_category)

        logger.info(f"fetch {in_data.seed_keyword} result: {response}")

        return response
