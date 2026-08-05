from abc import ABC, abstractmethod
from typing import Optional


class Approver(ABC):
    @abstractmethod
    def approve(self, amount):
        ...


class Manager(Approver):
    def __init__(self):
        self.next: Optional[Approver] = None

    def approve(self, amount):
        if amount < 1000:
            return True
        return self.next.approve(amount)


class Director(Approver):
    def __init__(self):
        self.next: Optional[Approver] = None

    def approve(self, amount):
        if amount < 10000:
            return True
        return self.next.approve(amount)
