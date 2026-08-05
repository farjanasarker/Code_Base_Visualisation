from abc import ABC, abstractmethod
from typing import List


class Observer(ABC):
    @abstractmethod
    def update(self, event):
        ...


class EmailObserver(Observer):
    def update(self, event):
        pass


class SmsObserver(Observer):
    def update(self, event):
        pass


class Subject:
    def __init__(self):
        self.observers: List[Observer] = []

    def attach(self, observer: Observer):
        self.observers.append(observer)

    def notify(self, event):
        for observer in self.observers:
            observer.update(event)
