import asyncio

import re
import structlog

from kw2graph import config
from kw2graph.domain.contents_fetcher import ContentsFetcherService
from kw2graph.domain.keywords_analyzer import KeywordsAnalyzerService
from kw2graph.infrastructure.graphdb import GraphDatabaseRepository

from kw2graph.usecase.base import UseCaseBase
from kw2graph.usecase.input.analyze_keywords import AnalyzeKeywordsInput
from kw2graph.usecase.input.get_candidate import GetCandidateInput
from kw2graph.usecase.input.submit_task import SubmitTaskInput
from kw2graph.util.text_formatter import TextFormatter

logger = structlog.get_logger(__name__)


class SubmitGraphAnalysisUseCase(UseCaseBase):
    def __init__(self, settings: config.Settings,
                 graph_repo: GraphDatabaseRepository):
        super().__init__(settings)
        self.graph_repo = graph_repo
        self.formatter = TextFormatter()
        # 既存の分析サービスを初期化（ここではリポジトリを直接注入せず、サービスを初期化）
        self.fetcher = ContentsFetcherService(settings)
        self.analyzer_service = KeywordsAnalyzerService(settings)

    async def execute(self, in_data: SubmitTaskInput):
        """
        最初の起点キーワードの解析と登録を実行し、その後、再帰的な探索をトリガーします。
        """
        logger.info("START: Initial graph analysis task.", keyword=in_data.seed_keyword)

        # 1. 最初の起点キーワードの処理を実行
        success = await self._process_single_keyword(in_data)

        if success:
            logger.info("Initial analysis successful. Starting recursive search (Depth 1).")

            # 2. ステップ 2: 最初のホップ（階層 1）の自動探索を開始
            # 必須条件: entity_type='Proper', score >= 0.90
            await self.execute_recursive_analysis(
                in_data=in_data,
                seed_keyword=in_data.seed_keyword,
                min_score=0.90,
                entity_type='Proper',
                depth=1  # 最初のホップ
            )

            # 3. ステップ 3: 2番目のホップ（階層 2）の自動探索を開始
            # 必須条件: entity_type='Proper', score >= 0.95 (より厳しく)
            await self.execute_recursive_analysis(
                in_data=in_data,
                seed_keyword=in_data.seed_keyword,
                min_score=0.95,
                entity_type='Proper',
                depth=2  # 2番目のホップ
            )

        logger.info("FINISH: All analysis tasks completed.", keyword=in_data.seed_keyword)
        return success

    # -----------------------------------------------------
    # 💡 新規: 再帰的な探索とタスク実行をオーケストレートするメソッド
    # -----------------------------------------------------
    async def execute_recursive_analysis(self,
                                         in_data: SubmitTaskInput,
                                         seed_keyword: str,
                                         min_score: float,
                                         entity_type: str,
                                         depth: int):
        """
        GraphDBから条件に合う新しいキーワードを発見し、それぞれに対して解析タスクを実行します。
        """
        logger.info(f"START: Recursive discovery at Depth {depth}.",
                    source_keyword=seed_keyword, min_score=min_score)

        # 1. GraphDBから次の階層の新しいキーワード候補を取得
        # Note: Gremlinメソッドは depth=1 で呼び出し、直近の関連ノードのみを探す
        new_keywords = await self.graph_repo.get_new_and_eligible_keywords(
            seed_keyword=seed_keyword,
            min_score=min_score,
            entity_type=entity_type,
            max_depth=1
        )

        if not new_keywords:
            logger.info(f"No new eligible keywords found at Depth {depth}.")
            return

        logger.info(f"Discovered {len(new_keywords)} new keywords at Depth {depth}. Starting parallel processing.")

        # 2. 発見された各キーワードに対して並列で解析と登録を実行
        tasks = []
        for new_kw in new_keywords:
            cleaned_seed_keyword = self._clean_keyword_context(new_kw)
            # 新しいキーワードを起点とするタスクを準備
            new_input = SubmitTaskInput(
                seed_keyword=cleaned_seed_keyword,
                index=in_data.index,
                field=in_data.field,
                max_titles=in_data.max_titles  # タイトル数は設定値を利用
            )
            # 各タスクは _process_single_keyword を実行する
            tasks.append(self._process_single_keyword(new_input))

        # 3. すべてのタスクを並列で待機
        await asyncio.gather(*tasks, return_exceptions=False)

        logger.info(f"FINISH: Recursive discovery at Depth {depth} completed.")

    # -----------------------------------------------------
    # 💡 新規: 単一のキーワードの解析と登録を実行するヘルパーメソッド
    # -----------------------------------------------------
    async def _process_single_keyword(self, in_data: SubmitTaskInput) -> bool:
        """
        単一のキーワードに対して、Elasticsearch取得 -> OpenAI解析 -> GraphDB登録を一貫して実行します。
        """
        logger.debug(f"Processing single keyword: {in_data.seed_keyword}")

        # 1. Elasticsearchからタイトルを取得
        # ... (fetcher.fetch のロジックは前のコードを参照)
        search_result = await self.fetcher.fetch(GetCandidateInput(
            index=in_data.index,
            field=in_data.field,
            keyword=in_data.seed_keyword,
        ))

        # titles = [c['snippet']['title'] for c in candidates]
        titles = []
        for candidate in search_result.candidates:
            titles.append(candidate['snippet']['title'])

        # 2. 前処理 (正規化とフィルタリング)
        normalized_titles = self.formatter.normalize_titles_list(titles)
        if not normalized_titles: return False

        # 3. OpenAIで非同期バッチ解析
        analyze_output = await self.analyzer_service.analyze(
            in_data=AnalyzeKeywordsInput(seed_keyword=in_data.seed_keyword, children=normalized_titles),
            use_batch=True
        )
        if not analyze_output.results: return False

        # 4. GraphDBへの登録
        registration_data = [
            {'keyword': item.keyword, 'score': item.score, 'iab_categories': item.iab_categories,
             'entity_type': item.entity_type}
            for item in analyze_output.results
        ]

        # channel_name は省略
        channel_name = None

        success = await self.graph_repo.register_related_keywords(
            seed_keyword=in_data.seed_keyword,
            extracted_data=registration_data,
            channel_name=channel_name
        )
        return success

    @staticmethod
    def _clean_keyword_context(keyword: str) -> str:
        """キーワードから末尾の括弧書きの文脈情報 (例: ' (ちいかわの文脈)') を削除する。"""
        # 正規表現: 末尾の ' (' から ')' までを非貪欲にマッチさせ、削除
        return re.sub(r' \([^)]+\)$', '', keyword).strip()
