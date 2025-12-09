from typing import List

from kw2graph.usecase.output.base import OutputBase


class Node(OutputBase):
    id: str
    label: str
    group: str
    entity_type: str
    iab_categories: List[str] | None


class Edge(OutputBase):
    id: str
    from_node: str  # キー名を Gremlin の出力に合わせて from_node に統一
    to_node: str  # キー名を Gremlin の出力に合わせて to_node に統一
    score: float


class ShowGraphOutput(OutputBase):
    nodes: List[Node]
    edges: List[Edge]
