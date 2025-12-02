from kw2graph.domain.base import ServiceBase
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository
from kw2graph.usecase.input.create_graph import CreateGraphInput
from kw2graph.usecase.output.create_graph import CreateGraphOutput


class GraphCreatorService(ServiceBase):
    def __init__(self, settings):
        super().__init__(settings)
        self.repo = GraphDatabaseRepository(settings)

    async def create(self, in_data: CreateGraphInput) -> CreateGraphOutput:
        children = [item.model_dump() for item in in_data.children]
        result = await self.repo.register_related_keywords(in_data.seed_keyword, children)
        return CreateGraphOutput(result=result)
