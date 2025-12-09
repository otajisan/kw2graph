import asyncio
from typing import List

import structlog

from kw2graph import config
from kw2graph.domain.base import ServiceBase
from kw2graph.infrastructure.openai import OpenAiRepository, OpenAiExtractionResult
from kw2graph.usecase.input.analyze_keywords import AnalyzeKeywordsInput
from kw2graph.usecase.output.analyze_keywords import AnalyzeKeywordsOutput, AnalyzeKeywordsOutputItem
from kw2graph.util.text_formatter import TextFormatter

logger = structlog.get_logger(__name__)


class KeywordsAnalyzerService(ServiceBase):
    TOP_N_LIMIT = 5

    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.openai_repo = OpenAiRepository(settings)
        self.formatter = TextFormatter()

    async def analyze(self, in_data: AnalyzeKeywordsInput, use_batch: bool = True) -> AnalyzeKeywordsOutput:
        """
        OpenAI APIを呼び出し、キーワードと属性を抽出します。
        デフォルトでは、パフォーマンス向上のため非同期バッチ処理を使用します。
        """
        normalized_keywords = self.formatter.normalize_titles_list(in_data.children)

        if not normalized_keywords:
            logger.warning("Normalized keywords list is empty. Skipping OpenAI call.")
            return AnalyzeKeywordsOutput(seed_keyword=in_data.seed_keyword, results=[])

        # 処理の分岐
        if use_batch:
            # ★ 修正: 非同期バッチ処理を呼び出し、awaitする
            response = await self.openai_repo.async_extract_related_keywords_batch(
                in_data.seed_keyword,
                normalized_keywords
            )
        else:
            # ★ 修正: 同期処理をスレッドでラップして呼び出す (FastAPI内では推奨)
            # 既存の同期メソッドを呼び出しつつ、FastAPIのイベントループをブロックしないように asyncio.to_thread を使用
            response = await asyncio.to_thread(
                self.openai_repo.extract_related_keywords,
                in_data.seed_keyword,
                normalized_keywords
            )

        logger.info(f"Extracted {len(response)} related keywords")
        parsed_output = self.parse_response(seed_keyword=in_data.seed_keyword, response=response)
        sorted_results = sorted(
            parsed_output.results,
            key=lambda item: item.score,
            reverse=True
        )
        # 上位 N 件に制限
        top_n_results = sorted_results[:self.TOP_N_LIMIT]

        logger.info(f"Filtered to top {self.TOP_N_LIMIT} keywords.", count=len(top_n_results),
                    seed=in_data.seed_keyword)

        return AnalyzeKeywordsOutput(
            seed_keyword=in_data.seed_keyword,
            results=top_n_results,
        )

    @staticmethod
    def parse_response(seed_keyword: str, response: OpenAiExtractionResult) -> AnalyzeKeywordsOutput:
        logger.debug(f"Parsing OpenAI response: {response}")

        results: List[AnalyzeKeywordsOutputItem] = []
        for item in response:
            results.append(AnalyzeKeywordsOutputItem(
                keyword=item['keyword'],
                score=item['score'],
                iab_categories=item['iab_categories'],
                entity_type=item['entity_type']
            ))

        return AnalyzeKeywordsOutput(
            seed_keyword=seed_keyword,
            results=results,
        )
