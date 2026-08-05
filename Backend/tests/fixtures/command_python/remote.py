from abc import ABC, abstractmethod


class Light:
    def turn_on(self):
        pass

    def turn_off(self):
        pass


class Command(ABC):
    @abstractmethod
    def execute(self):
        ...


class LightOnCommand(Command):
    def __init__(self, light: Light):
        self.light = light

    def execute(self):
        self.light.turn_on()


class LightOffCommand(Command):
    def __init__(self, light: Light):
        self.light = light

    def execute(self):
        self.light.turn_off()
