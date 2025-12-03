from typing import List

from kw2graph.usecase.input.base import InputBase


class CreateGraphInputItem(InputBase):
    keyword: str
    score: float
    iab_categories: List[str]
    entity_type: str


class CreateGraphInput(InputBase):
    seed_keyword: str
    children: List[CreateGraphInputItem]
