import asyncio
from json import JSONDecodeError
from typing import List, Dict, Any, Awaitable

import json
import structlog
from openai import OpenAI, OpenAIError

from kw2graph import config
from kw2graph.infrastructure.base import RepositoryBase

logger = structlog.get_logger(__name__)

OpenAiExtractionResult = List[Dict[str, Any]]


class OpenAiRepository(RepositoryBase):
    MODEL = "gpt-5-nano"
    BATCH_SIZE = 10

    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.client = OpenAI(api_key=settings.openai_api_key)

    @staticmethod
    def _generate_prompt_old(seed_keyword: str, titles: List[str]) -> str:
        titles_str = "\n".join([f"{i + 1}. {title}" for i, title in enumerate(titles)])

        prompt = f"""
    あなたはキーワード抽出とスコアリングの専門家です。
    以下の手順で、提供されたコンテンツタイトル群からシードキーワードに関連性の高い語句を抽出し、関連度をスコア化してください。

    #シードキーワード: {seed_keyword}

    #コンテンツタイトル群:
    {titles_str}

    #手順
    1. タイトルからシードキーワード「{seed_keyword}」に**直接関連する単語やフレーズ**を抽出する。
    2. 抽出された各語句に対し、シードキーワード「{seed_keyword}」との**関連度を0.0から1.0の間でスコア**（float型）として付与する。
    3. 結果をJSON形式のオブジェクトとして出力する。**出力は必ずJSON形式のみ**とし、他の説明や前置きは含めないでください。

    #JSON出力形式:
    {{
      "related_keywords": [
        {{"keyword": "抽出された語句", "score": 関連度スコア}},
        {{"keyword": "別の語句", "score": 関連度スコア}},
        ...
      ]
    }}
    """
        logger.debug(f"Generating prompt: \n{prompt}")
        return prompt

    @staticmethod
    def _generate_prompt_old2(seed_keyword: str, titles: List[str]) -> str:
        titles_str = "\n".join([f"{i + 1}. {title}" for i, title in enumerate(titles)])

        prompt = f"""
        あなたはキーワード抽出とスコアリングの専門家です。
        以下の手順で、提供されたコンテンツタイトル群から**シードキーワードを修飾する最も具体的かつ独立した語句**を抽出してください。

        #シードキーワード: {seed_keyword}

        #コンテンツタイトル群:
        {titles_str}

        #手順
        1. 抽出対象は、シードキーワード「{seed_keyword}」から**独立して意味を持つ、単一の要素**（カスタム名、部品名、行為など）とする。
        2. 抽出語句は、**シードキーワード（例: ランクル70）を繰り返して含めない**こと。（例: "新型ランクル70 カスタム" ではなく、**"カスタム"** を抽出すること）
        3. 抽出された各語句に対し、シードキーワードとの**関連度を0.0から1.0の間でスコア**（float型）として付与する。
        4. 結果をJSON形式のオブジェクトとして出力する。**出力は必ずJSON形式のみ**とし、他の説明や前置きは含めないでください。

        #出力例 (シードキーワードが「ランクル70」の場合の期待値):
        {{
          "related_keywords": [
            {{"keyword": "カスタム", "score": 0.98}},
            {{"keyword": "アイアンバンパー", "score": 0.90}},
            {{"keyword": "再販", "score": 0.95}},
            {{"keyword": "納車", "score": 0.85}},
            ...
          ]
        }}

        """
        logger.debug(f"Generating prompt: \n{prompt}")
        return prompt

    @staticmethod
    def _generate_prompt_old3(seed_keyword: str, titles: List[str]) -> str:
        titles_str = "\n".join([f"{i + 1}. {title}" for i, title in enumerate(titles)])

        prompt = f"""
        あなたはキーワード抽出とスコアリングの専門家です。
        提供されたコンテンツタイトル群から、**シードキーワードが属する上位概念**および**具体的な関連詳細語句**の両方を抽出し、関連度をスコア化してください。

        #シードキーワード: {seed_keyword}

        #コンテンツタイトル群:
        {titles_str}

        #手順
        1. 抽出対象は、以下の2種類とする。
           - **上位概念/主題**: シードキーワードが属する**最も重要なカテゴリ**（例: 「ちいかわ」「アニメ」「キャラクター」）。これらのスコアは高く設定すること。
           - **具体的な詳細**: シードキーワードを**修飾する**最も具体的かつ独立した語句（例: 「アイアンバンパー」「カップラーメン」「描き方」）。抽出語句は、**シードキーワード（例: くりまんじゅう）を繰り返して含めない**こと。
        2. 抽出された各語句に対し、シードキーワード「{seed_keyword}」との**関連度を0.0から1.0の間でスコア**（float型）として付与する。
        3. 結果をJSON形式のオブジェクトとして出力する。**出力は必ずJSON形式のみ**とし、他の説明や前置きは含めないでください。

        #出力例 (シードキーワードが「くりまんじゅう」の場合の期待値):
        {{
          "related_keywords": [
            {{"keyword": "ちいかわ", "score": 0.99}},          // 上位概念
            {{"keyword": "アニメ", "score": 0.96}},            // 上位概念
            {{"keyword": "栗まんじゅう編", "score": 0.92}},      // 詳細（エピソード名）
            {{"keyword": "カップラーメン", "score": 0.85}},      // 詳細（商品名/モノ）
            {{"keyword": "描き方", "score": 0.82}},             // 詳細（行為）
            ...
          ]
        }}
        """
        logger.debug(f"Generating prompt: \n{prompt}")
        return prompt

    @staticmethod
    def _generate_prompt_old4(seed_keyword: str, titles: List[str]) -> str:
        titles_str = "\n".join([f"{i + 1}. {title}" for i, title in enumerate(titles)])

        # 広告業界標準の IAB Tier 1 カテゴリリスト
        IAB_CATEGORIES = [
            "Arts & Entertainment", "Automotive", "Business", "Careers", "Education",
            "Family & Relationships", "Food & Drink", "Health & Fitness", "Hobbies & Interests",
            "Home & Garden", "Law, Govt & Politics", "News", "Personal Finance", "Pets",
            "Science", "Shopping", "Sports", "Style & Fashion", "Technology & Computing",
            "Travel", "Video Gaming", "Other"
        ]
        iab_list_str = ", ".join(IAB_CATEGORIES)

        prompt = f"""
        あなたはキーワード抽出、階層分析、および標準化された分類を専門とするエキスパートAIです。
        提供されたコンテンツタイトル群を分析し、シードキーワード「{seed_keyword}」に関する以下の3つの属性を持つ語句を抽出し、JSON形式でリスト化してください。

        #シードキーワード: {seed_keyword}

        #コンテンツタイトル群:
        {titles_str}

        #手順
        1. **上位概念の特定**: タイトル群全体から、「{seed_keyword}」が属する**最も重要なカテゴリ名や主題**を抽出する。これらの語句には最も高いスコアを付与すること。
        2. **詳細語句の分解**: タイトルから、シードキーワードを修飾する**具体的かつ独立した語句**（部品名、エピソード名、行為など）を抽出する。抽出語句は、シードキーワード自体（例: くりまんじゅう）を**含めない**ように徹底して分解すること。
        3. **entity_type の判断**: 抽出された各語句が、**特定の固有名詞（人名、作品名、商品名など）であれば 'Proper'** を、**一般的な名詞や概念であれば 'General'** を判断し付与する。
        4. **IAB分類へのマッピング**: 抽出された各語句に対し、その語句の意味を最も適切に表す**IAB Tier 1 カテゴリを**、以下のリストから**最大3つまで選択**し、'iab_categories' として**文字列の配列（リスト）**で付与すること。

        【IAB Tier 1 カテゴリ リスト】: {iab_list_str}

        #JSON出力形式:
        {{
          "related_keywords": [
            {{
              "keyword": "抽出された語句", 
              "score": 関連度スコア, 
              "iab_categories": ["カテゴリ1", "カテゴリ2"], // ★ 修正: リスト型
              "entity_type": "Proper/General"        
            }},
            {{
              "keyword": "別の語句", 
              "score": 別の関連度スコア,
              "iab_categories": ["別のカテゴリ名"],
              "entity_type": "Proper/General"
            }},
            ...
          ]
        }}

        #出力例 (シードキーワードが「くりまんじゅう」の場合の期待値):
        {{
          "related_keywords": [
            {{"keyword": "ちいかわ", "score": 0.99, "iab_categories": ["Arts & Entertainment", "Family & Relationships"], "entity_type": "Proper"}},
            {{"keyword": "カップラーメン", "score": 0.85, "iab_categories": ["Food & Drink"], "entity_type": "Proper"}},
            ...
          ]
        }}
        """
        logger.debug(f"Generating prompt: \n{prompt}")
        return prompt

    @staticmethod
    def _generate_prompt(seed_keyword: str, titles: List[str]) -> str:
        titles_str = "\n".join([f"{i + 1}. {title}" for i, title in enumerate(titles)])

        # IAB カテゴリリストはそのまま維持（必須情報）
        IAB_CATEGORIES = [
            "Arts & Entertainment", "Automotive", "Business", "Careers", "Education",
            "Family & Relationships", "Food & Drink", "Health & Fitness", "Hobbies & Interests",
            "Home & Garden", "Law, Govt & Politics", "News", "Personal Finance", "Pets",
            "Science", "Shopping", "Sports", "Style & Fashion", "Technology & Computing",
            "Travel", "Video Gaming", "Other"
        ]
        iab_list_str = ", ".join(IAB_CATEGORIES)

        prompt = f"""
        コンテンツタイトル群を分析し、シードキーワード「{seed_keyword}」に関する以下の属性を持つ語句を抽出し、JSON形式でリスト化してください。

        #シードキーワード: {seed_keyword}

        #コンテンツタイトル群:
        {titles_str}

        #抽出と分類のルール
        * **語句 (keyword)**: 
            1. タイトル群の**上位概念/主題**（例: ちいかわ、アニメ）を抽出する。
            2. シードキーワードを**修飾する具体的かつ独立した語句**（例: 部品名、エピソード名）を、シードキーワードを含めずに**徹底して分解**し抽出する。
        * **関連度 (score)**: 0.0〜1.0 の間で付与する。上位概念には最も高いスコアを付与する。
        * **エンティティ種別 (entity_type)**: 固有名詞（作品名、商品名など）は 'Proper'、一般的名詞/概念は 'General' とする。
        * **IABカテゴリ (iab_categories)**: 以下の【IAB Tier 1 カテゴリ リスト】から、**最大3つ**をリストとして選択する。

        【IAB Tier 1 カテゴリ リスト】: {iab_list_str}

        #JSON出力形式:
        {{
          "related_keywords": [
            {{
              "keyword": "抽出された語句", 
              "score": 関連度スコア, 
              "iab_categories": ["カテゴリ1", "カテゴリ2"],
              "entity_type": "Proper/General"        
            }},
            {{
              "keyword": "別の語句", 
              "score": 別の関連度スコア,
              "iab_categories": ["別のカテゴリ名"],
              "entity_type": "Proper/General"
            }},
            ...
          ]
        }}
        """
        logger.debug(f"Generating prompt: \n{prompt}")
        return prompt

    def extract_related_keywords(self, seed_keyword: str, titles: List[str]) -> OpenAiExtractionResult:
        prompt = self._generate_prompt(seed_keyword, titles)

        try:
            logger.info(f"Extracting related keywords: {seed_keyword}")
            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system",
                     # システムプロンプトもJSON出力を強調
                     "content": "あなたは与えられたテキストから関連キーワードを抽出し、指定されたJSON形式のオブジェクトで出力するエキスパートです。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
            )

            logger.debug(f'Generated response: {response}')

            json_string = response.choices[0].message.content

            # 💡 ルートがオブジェクトであることを想定してパース
            data = json.loads(json_string)
            logger.debug(f"Parsed OpenAI response: {data}")

            # 💡 期待されるキー 'related_keywords' が存在するかチェック
            if isinstance(data, dict) and 'related_keywords' in data:
                return data['related_keywords']
            else:
                logger.error("OpenAI response did not contain 'related_keywords' list.", data=data)
                # 応答が期待通りでない場合、空のリストを返す
                return []

        except JSONDecodeError:
            logger.error("Failed to decode JSON from OpenAI response.", raw_content=json_string)
            return []
        except Exception as e:
            print(f"OpenAI API呼び出しエラー: {e}")
            return []

    # -----------------------------------------------------------
    # 2. 新規関数: 非同期バッチ処理 (Parallel/Non-Blocking) を追加
    # -----------------------------------------------------------

    async def _process_batch_async(self, seed_keyword: str, batch_titles: List[str]) -> OpenAiExtractionResult:
        """
        単一のタイトルバッチに対してOpenAI APIコールを非同期(スレッド)で実行します。
        """
        # 同期関数を asyncio.to_thread でラップし、メインイベントループをブロックしないようにする
        return await asyncio.to_thread(self.extract_related_keywords, seed_keyword, batch_titles)

    async def async_extract_related_keywords_batch(self, seed_keyword: str,
                                                   titles: List[str]) -> OpenAiExtractionResult:
        """
        タイトルリストをバッチに分割し、OpenAI APIを並列で実行します。(非同期処理)
        """
        # タイトルリストをバッチに分割
        batches: List[List[str]] = [
            titles[i:i + self.BATCH_SIZE]
            for i in range(0, len(titles), self.BATCH_SIZE)
        ]

        logger.info(f"OpenAI extraction split into {len(batches)} batches for parallel processing (ASYNC).")

        # 各バッチの処理タスクを作成
        tasks: List[Awaitable[OpenAiExtractionResult]] = [
            self._process_batch_async(seed_keyword, batch)
            for batch in batches
        ]

        # asyncio.gather() を使って、すべてのバッチを並列実行
        results_from_batches: List[OpenAiExtractionResult] = await asyncio.gather(*tasks, return_exceptions=True)

        final_result: OpenAiExtractionResult = []
        for result in results_from_batches:
            if isinstance(result, list):
                final_result.extend(result)
            else:
                # バッチ処理中に例外が発生した場合
                logger.error("A batch failed during parallel execution.", exception=result)

        # 重複排除が必要な場合は、ここで実装します。
        # (例: return list({frozenset(d.items()): d for d in final_result}.values()))

        return final_result
