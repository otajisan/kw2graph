from typing import List

from kw2graph.usecase.input.base import InputBase


class AnalyzeKeywordsInput(InputBase):
    seed_keyword: str
    child_keywords: List[str]
