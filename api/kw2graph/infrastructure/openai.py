from json import JSONDecodeError
from typing import List, Dict, Any

import json
import structlog
from openai import OpenAI, OpenAIError

from kw2graph import config
from kw2graph.infrastructure.base import RepositoryBase

logger = structlog.get_logger(__name__)

OpenAiExtractionResult = List[Dict[str, Any]]


class OpenAiRepository(RepositoryBase):
    MODEL = "gpt-5-nano"

    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.client = OpenAI(api_key=settings.openai_api_key)

    @staticmethod
    def _generate_prompt(seed_keyword: str, titles: List[str]) -> str:
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
                response_format={"type": "json_object"}
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
