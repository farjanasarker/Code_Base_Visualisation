from abc import ABC, abstractmethod


class Implementor(ABC):
    @abstractmethod
    def operation_impl(self):
        ...


class ConcreteImplementorA(Implementor):
    def operation_impl(self):
        pass


class ConcreteImplementorB(Implementor):
    def operation_impl(self):
        pass


class Abstraction:
    def __init__(self, implementor: Implementor):
        self.implementor = implementor

    def operation(self):
        self.implementor.operation_impl()


class RefinedAbstractionA(Abstraction):
    pass


class RefinedAbstractionB(Abstraction):
    pass
