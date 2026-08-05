from abc import ABC, abstractmethod
from typing import List


class Graphic(ABC):
    @abstractmethod
    def render(self):
        ...


class Dot(Graphic):
    def render(self):
        pass


class CompoundGraphic(Graphic):
    def __init__(self):
        self.children: List[Graphic] = []

    def add(self, child: Graphic):
        self.children.append(child)

    def render(self):
        for child in self.children:
            child.render()
