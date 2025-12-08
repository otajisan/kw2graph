import structlog
import asyncio
from typing import List, Dict, Any

from kw2graph import config
from kw2graph.domain.contents_fetcher import ContentsFetcherService
from kw2graph.usecase.base import UseCaseBase
# 各リポジトリをインポート (DIを想定)
from kw2graph.infrastructure.elasticsearch import ElasticsearchRepository
from kw2graph.infrastructure.openai import OpenAiRepository
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository
from kw2graph.usecase.input.analyze import AnalyzeKeywordsInput
from kw2graph.usecase.input.base import InputBase
from kw2graph.usecase.input.candidate import GetCandidateInput
from kw2graph.usecase.output.base import OutputBase
from kw2graph.util.text_formatter import TextFormatter  # 既に存在
from kw2graph.domain.keywords_analyzer import KeywordsAnalyzerService  # 既存の分析ロジックを使用

logger = structlog.get_logger(__name__)


# 仮定: このユースケースのInput/Outputモデルはシンプル
class SubmitTaskInput(InputBase):
    seed_keyword: str
    index: str
    field: str
    max_titles: int = 50  # 取得するタイトルの最大数


class SubmitTaskOutput(OutputBase):
    success: bool
    message: str


class SubmitGraphAnalysisUseCase(UseCaseBase):
    def __init__(self, settings: config.Settings,
                 graph_repo: GraphDatabaseRepository):
        super().__init__(settings)
        self.graph_repo = graph_repo
        self.formatter = TextFormatter()
        # 既存の分析サービスを初期化（ここではリポジトリを直接注入せず、サービスを初期化）
        self.fetcher = ContentsFetcherService(settings)
        self.analyzer_service = KeywordsAnalyzerService(settings)

    # -----------------------------------------------------
    # ★ メインの統合処理 (時間がかかるため、ルーターから非同期実行される)
    # -----------------------------------------------------
    async def execute(self, in_data: SubmitTaskInput):

        logger.info("START: Integrated graph analysis and registration.", keyword=in_data.seed_keyword)

        search_result = await self.fetcher.fetch(GetCandidateInput(
            index=in_data.index,
            field=in_data.field,
            keyword=in_data.seed_keyword,
        ))

        titles = []
        for candidate in search_result.candidates:
            titles.append(candidate['snippet']['title'])

        # 2. 前処理 (正規化とフィルタリング)
        normalized_titles = self.formatter.normalize_titles_list(titles)
        if not normalized_titles:
            logger.warning("No valid titles found after normalization. Aborting.")
            return

        # 3. OpenAIで非同期バッチ解析 (最も時間のかかるステップ)
        # KeywordsAnalyzerService のロジックを再利用する
        analyze_output = await self.analyzer_service.analyze(
            in_data=AnalyzeKeywordsInput(seed_keyword=in_data.seed_keyword, children=normalized_titles),
            use_batch=True  # 必ず非同期バッチを使用
        )

        if not analyze_output.results:
            logger.warning("OpenAI returned no keywords. Aborting registration.")
            return

        # 4. GraphDBへの登録 (CreateGraphのロジックを再利用)
        # AnalyzeKeywordsOutputItemをCreateGraphInputItemに変換し、登録

        # 登録に必要なデータ形式に変換
        registration_data = [
            {
                'keyword': item.keyword,
                'score': item.score,
                'iab_categories': item.iab_categories,
                'entity_type': item.entity_type
            }
            for item in analyze_output.results
        ]

        # チャンネル名検出ロジックは省略（必要に応じてtitlesから抽出）
        channel_name = None

        success = await self.graph_repo.register_related_keywords(
            seed_keyword=in_data.seed_keyword,
            extracted_data=registration_data,
            channel_name=channel_name
        )

        logger.info("FINISH: Graph registration result.", success=success, keyword=in_data.seed_keyword)

        return success
