import structlog

from kw2graph import config
from kw2graph.infrastructure.elasticsearch import ElasticsearchClient
from kw2graph.domain.base import ServiceBase
from kw2graph.usecase.input.candidate import GetCandidateInput
from kw2graph.usecase.output.candidate import GetCandidateOutput

logger = structlog.get_logger(__name__)


class ContentsFetcherService(ServiceBase):

    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.client = ElasticsearchClient(settings)

    def fetch(self, in_data: GetCandidateInput) -> GetCandidateOutput:
        response = self.client.search(in_data.index, in_data.field, in_data.keyword)
        logger.info(f"Found {len(response['hits'])} candidates")

        return self.parse_response(response)

    @staticmethod
    def parse_response(response) -> GetCandidateOutput:
        candidates = []
        for hit in response['hits']['hits']:
            source = hit['_source']
            candidates.append(source)

        return GetCandidateOutput(candidates=candidates)
