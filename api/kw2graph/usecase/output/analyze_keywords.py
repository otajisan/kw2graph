from typing import List, Dict

from kw2graph.usecase.output.base import OutputBase


class AnalyzeKeywordsOutputItem(OutputBase):
    keyword: str
    score: float
    iab_categories: List[str]
    entity_type: str


class AnalyzeKeywordsOutput(OutputBase):
    seed_keyword: str
    results: List[AnalyzeKeywordsOutputItem]
