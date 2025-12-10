from typing import List

from pydantic import field_validator

from kw2graph.usecase.input.base import InputBase


class ShowGraphInput(InputBase):
    """グラフ表示の起点となるキーワードと深さ"""
    seed_keywords: List[str]
    max_depth: int = 2  # デフォルト値を設定
    min_score: float = 0.0
    entity_type: str | None = None
    iab_category: str | None = None

    # @field_validator('seed_keywords', mode='before')
    # @classmethod
    # def split_keywords(cls, v):
    #     if isinstance(v, str):
    #         # カンマ区切り文字列を List[str] に変換
    #         return [kw.strip() for kw in v.split(',') if kw.strip()]
    #     # List[str] またはその他の型の場合はそのまま返す
    #     return v
