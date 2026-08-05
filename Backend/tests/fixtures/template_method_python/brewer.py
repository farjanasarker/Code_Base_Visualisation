from abc import ABC, abstractmethod


class CaffeineBeverage(ABC):
    def prepare_recipe(self):
        self.boil_water()
        self.brew()
        self.pour_in_cup()

    def boil_water(self):
        pass

    def pour_in_cup(self):
        pass

    @abstractmethod
    def brew(self):
        ...


class Tea(CaffeineBeverage):
    def brew(self):
        pass


class Coffee(CaffeineBeverage):
    def brew(self):
        pass
