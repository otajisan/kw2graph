from kw2graph.usecase.input.base import InputBase


class ShowGraphInput(InputBase):
    """グラフ表示の起点となるキーワードと深さ"""
    seed_keyword: str
    max_depth: int = 2  # デフォルト値を設定
    min_score: float = 0.0
    entity_type: str | None = None
    iab_category: str | None = None
