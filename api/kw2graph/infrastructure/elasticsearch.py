import structlog
from elastic_transport import ObjectApiResponse
from elasticsearch import Elasticsearch

from kw2graph import config
from kw2graph.infrastructure.base import RepositoryBase

logger = structlog.get_logger(__name__)


class ElasticsearchRepository(RepositoryBase):
    RESULTS_SIZE = 100

    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        logger.info("Initializing ElasticsearchClient", es_host=settings.es_host)
        self.host = settings.es_host
        self.api_key = settings.es_api_key
        self.client = Elasticsearch(
            hosts=[self.host],
            api_key=self.api_key
        )

    def search(self, index, field, keyword) -> ObjectApiResponse:
        query_dsl = {
            "match": {
                field: keyword
            }
        }

        response = self.client.search(
            index=index,
            query=query_dsl,
            size=self.RESULTS_SIZE,
            sort=[
                {"_score": {"order": "desc"}}
            ]
        )

        return response

    def analyze(self, index, text):
        body = {
            'analyzer': 'kuromoji',
            'text': text
        }

        response = self.client.indices.analyze(
            index=index,
            body=body
        )

        return response
