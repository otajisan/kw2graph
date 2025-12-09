from kw2graph import config
from kw2graph.domain.contents_fetcher import ContentsFetcherService
from kw2graph.usecase.base import UseCaseBase
from kw2graph.usecase.input.get_candidate import GetCandidateInput
from kw2graph.usecase.output.get_candidate import GetCandidateOutput


class GetCandidateUseCase(UseCaseBase):
    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.fetcher = ContentsFetcherService(settings)

    async def execute(self, in_data: GetCandidateInput) -> GetCandidateOutput:
        return await self.fetcher.fetch(in_data)
