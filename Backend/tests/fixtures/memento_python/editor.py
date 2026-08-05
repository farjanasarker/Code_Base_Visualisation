class Memento:
    def __init__(self, state):
        self.state = state


class Editor:
    def __init__(self):
        self.content = ""

    def save(self):
        return Memento(self.content)

    def restore(self, memento):
        self.content = memento.state
