from typing import List

from kw2graph.usecase.input.base import InputBase


class CreateGraphInputItem(InputBase):
    keyword: str
    score: float


class CreateGraphInput(InputBase):
    seed_keyword: str
    children: List[CreateGraphInputItem]
