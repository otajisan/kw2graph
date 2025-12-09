from typing import List, Dict, Any

from kw2graph.usecase.output.base import OutputBase


class GetCandidateOutput(OutputBase):
    seed_keyword: str
    candidates: List[Dict[str, Any]]
