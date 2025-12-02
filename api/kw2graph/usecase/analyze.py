from kw2graph.domain.keywords_analyzer import KeywordsAnalyzerService
from kw2graph.usecase.base import UseCaseBase
from kw2graph.usecase.input.analyze import AnalyzeKeywordsInput
from kw2graph.usecase.output.analyze import AnalyzeKeywordsOutput


class AnalyzeKeywordsUseCase(UseCaseBase):
    def __init__(self, settings):
        super().__init__(settings)
        self.analyzer = KeywordsAnalyzerService(settings)

    def execute(self, in_data: AnalyzeKeywordsInput) -> AnalyzeKeywordsOutput:
        return self.analyzer.analyze(in_data)
