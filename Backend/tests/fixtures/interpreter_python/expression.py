from abc import ABC, abstractmethod
from typing import List


class Expression(ABC):
    @abstractmethod
    def interpret(self, context):
        ...


class Number(Expression):
    def __init__(self, value):
        self.value = value

    def interpret(self, context):
        return self.value


class Add(Expression):
    def __init__(self):
        self.children: List[Expression] = []

    def interpret(self, context):
        total = 0
        for child in self.children:
            total += child.interpret(context)
        return total
