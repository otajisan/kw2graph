from abc import ABCMeta, abstractmethod

from pydantic import BaseModel

from kw2graph import config
from kw2graph.usecase.input.base import InputBase
from kw2graph.usecase.output.base import OutputBase


class UseCaseBase(metaclass=ABCMeta):
    def __init__(self, settings: config.Settings):
        self.settings = settings
        pass

    @abstractmethod
    def execute(self, in_data: InputBase) -> OutputBase:
        pass
