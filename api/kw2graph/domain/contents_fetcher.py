import structlog
from elastic_transport import ObjectApiResponse

from kw2graph import config
from kw2graph.infrastructure.elasticsearch import ElasticsearchRepository
from kw2graph.domain.base import ServiceBase
from kw2graph.usecase.input.get_candidate import GetCandidateInput
from kw2graph.usecase.output.get_candidate import GetCandidateOutput

logger = structlog.get_logger(__name__)


class ContentsFetcherService(ServiceBase):

    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.es_repo = ElasticsearchRepository(settings)

    async def fetch(self, in_data: GetCandidateInput) -> GetCandidateOutput:
        response = await self.es_repo.search(in_data.index, in_data.field, in_data.keyword)
        logger.info(f"Found {len(response['hits'])} candidates")

        return self.parse_response(seed_keyword=in_data.keyword, response=response)

    @staticmethod
    def parse_response(seed_keyword: str, response: ObjectApiResponse) -> GetCandidateOutput:
        candidates = []
        for hit in response['hits']['hits']:
            source = hit['_source']
            candidates.append(source)

        logger.debug(f"candidates: {candidates}")
        return GetCandidateOutput(seed_keyword=seed_keyword, candidates=candidates)
