from kw2graph import config
from kw2graph.domain.graph_creator import GraphCreatorService
from kw2graph.usecase.base import UseCaseBase
from kw2graph.usecase.input.create_graph import CreateGraphInput
from kw2graph.usecase.output.create_graph import CreateGraphOutput


class CreateGraphUseCase(UseCaseBase):
    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.creator = GraphCreatorService(settings)

    def execute(self, in_data: CreateGraphInput) -> CreateGraphOutput:
        return self.creator.create(in_data)
