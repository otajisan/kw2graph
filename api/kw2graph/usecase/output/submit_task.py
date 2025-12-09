from kw2graph.usecase.output.base import OutputBase


class SubmitTaskOutput(OutputBase):
    success: bool
    message: str
