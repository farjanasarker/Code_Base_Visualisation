from abc import ABC, abstractmethod


class Button(ABC):
    pass


class Checkbox(ABC):
    pass


class WinButton(Button):
    pass


class WinCheckbox(Checkbox):
    pass


class MacButton(Button):
    pass


class MacCheckbox(Checkbox):
    pass


class GUIFactory(ABC):
    @abstractmethod
    def create_button(self):
        ...

    @abstractmethod
    def create_checkbox(self):
        ...


class WinFactory(GUIFactory):
    def create_button(self):
        return WinButton()

    def create_checkbox(self):
        return WinCheckbox()


class MacFactory(GUIFactory):
    def create_button(self):
        return MacButton()

    def create_checkbox(self):
        return MacCheckbox()
