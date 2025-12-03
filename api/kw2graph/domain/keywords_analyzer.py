from typing import List

import structlog

from kw2graph import config
from kw2graph.domain.base import ServiceBase
from kw2graph.infrastructure.openai import OpenAiRepository, OpenAiExtractionResult
from kw2graph.usecase.input.analyze import AnalyzeKeywordsInput
from kw2graph.usecase.output.analyze import AnalyzeKeywordsOutput, AnalyzeKeywordsOutputItem
from kw2graph.util.text_formatter import TextFormatter

logger = structlog.get_logger(__name__)


class KeywordsAnalyzerService(ServiceBase):
    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.openai_repo = OpenAiRepository(settings)
        self.formatter = TextFormatter()

    def analyze(self, in_data: AnalyzeKeywordsInput) -> AnalyzeKeywordsOutput:
        normalized_keywords = self.formatter.normalize_titles_list(in_data.children)
        response = self.openai_repo.extract_related_keywords(in_data.seed_keyword, normalized_keywords)
        logger.info(f"Extracted {len(response)} related keywords")
        return self.parse_response(seed_keyword=in_data.seed_keyword, response=response)

    def parse_response(self, seed_keyword: str, response: OpenAiExtractionResult) -> AnalyzeKeywordsOutput:
        logger.debug(f"Parsing OpenAI response: {response}")

        results: List[AnalyzeKeywordsOutputItem] = []
        for item in response:
            results.append(AnalyzeKeywordsOutputItem(keyword=item['keyword'], score=item['score']))

        return AnalyzeKeywordsOutput(
            seed_keyword=seed_keyword,
            results=results,
        )
