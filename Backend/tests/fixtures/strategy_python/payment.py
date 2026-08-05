from abc import ABC, abstractmethod


class PaymentStrategy(ABC):
    @abstractmethod
    def pay(self, amount):
        ...


class CreditCardStrategy(PaymentStrategy):
    def pay(self, amount):
        self.charge(amount)

    def charge(self, amount):
        pass


class PayPalStrategy(PaymentStrategy):
    def pay(self, amount):
        self.send(amount)

    def send(self, amount):
        pass


class Checkout:
    def __init__(self, strategy: PaymentStrategy):
        self.strategy = strategy

    def process(self, amount):
        self.strategy.pay(amount)
