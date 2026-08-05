from abc import ABC, abstractmethod


class Coffee(ABC):
    @abstractmethod
    def cost(self):
        ...


class SimpleCoffee(Coffee):
    def cost(self):
        return 2


class MilkDecorator(Coffee):
    def __init__(self, wrapped: Coffee):
        self.wrapped = wrapped

    def cost(self):
        base = self.wrapped.cost()
        return base + self.milk_charge()

    def milk_charge(self):
        return 1


class LoggingProxy(Coffee):
    def __init__(self, wrapped: Coffee):
        self.wrapped = wrapped

    def cost(self):
        return self.wrapped.cost()
