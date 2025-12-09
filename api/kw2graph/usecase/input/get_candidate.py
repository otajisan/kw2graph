from kw2graph.usecase.input.base import InputBase


class GetCandidateInput(InputBase):
    index: str
    field: str
    keyword: str
