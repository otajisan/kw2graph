from typing import List

from kw2graph.usecase.input.base import InputBase


class AnalyzeKeywordsInput(InputBase):
    seed_keyword: str
    children: List[str]
