from typing import List, Dict

from kw2graph.usecase.output.base import OutputBase


class AnalyzeKeywordsOutputItem(OutputBase):
    keyword: str
    score: float


class AnalyzeKeywordsOutput(OutputBase):
    results: List[AnalyzeKeywordsOutputItem]
