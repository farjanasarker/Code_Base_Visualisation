from abc import ABC, abstractmethod


class Product(ABC):
    pass


class ConcreteProductA(Product):
    pass


class ConcreteProductB(Product):
    pass


class Creator(ABC):
    @abstractmethod
    def create_product(self):
        ...


class CreatorA(Creator):
    def create_product(self):
        return ConcreteProductA()


class CreatorB(Creator):
    def create_product(self):
        return ConcreteProductB()
