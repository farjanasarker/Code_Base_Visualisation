class Mediator:
    def notify(self, sender, event):
        pass


class ColleagueA:
    def __init__(self, mediator: Mediator):
        self.mediator = mediator

    def do_a(self):
        self.mediator.notify(self, "A")


class ColleagueB:
    def __init__(self, mediator: Mediator):
        self.mediator = mediator

    def do_b(self):
        self.mediator.notify(self, "B")
