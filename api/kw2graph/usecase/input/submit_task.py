from kw2graph.usecase.input.base import InputBase


class SubmitTaskInput(InputBase):
    seed_keyword: str
    index: str
    field: str
    max_titles: int = 50  # 取得するタイトルの最大数
