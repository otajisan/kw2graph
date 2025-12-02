from typing import List, Dict, Any

from openai import OpenAI, OpenAIError

from kw2graph import config
from kw2graph.infrastructure.base import RepositoryBase

OpenAiExtractionResult = List[Dict[str, Any]]


class OpenAiRepository(RepositoryBase):
    MODEL = "gpt-5-nano"

    def __init__(self, settings: config.Settings):
        super().__init__(settings)
        self.client = OpenAI(api_key=settings.openai_api_key)

    @staticmethod
    def _generate_prompt(self, seed_keyword: str, titles: List[str]) -> str:
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
3. 結果をJSON形式の配列として出力する。**出力は必ずJSON形式のみ**とし、他の説明や前置きは含めないでください。

#JSON出力形式:
[
  {{"keyword": "抽出された語句", "score": 関連度スコア}},
  {{"keyword": "別の語句", "score": 関連度スコア}},
  ...
]
"""
        return prompt

    def extract_related_keywords(self, seed_keyword: str, titles: List[str]) -> OpenAiExtractionResult:
        prompt = self._generate_prompt(seed_keyword, titles)

        try:
            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system",
                     "content": "あなたは与えられたテキストから関連キーワードを抽出し、指定されたJSON形式で出力するエキスパートです。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )

            # 応答からJSON文字列を取得し、Pythonの辞書/リストに変換
            json_string = response.choices[0].message.content
            import json
            return json.loads(json_string)

        except Exception as e:
            print(f"OpenAI API呼び出しエラー: {e}")
            return []
