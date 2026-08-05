class Target:
    def request(self):
        raise NotImplementedError


class Adaptee:
    def specific_request(self):
        pass


class Adapter(Target):
    def __init__(self, adaptee: Adaptee):
        self.adaptee = adaptee

    def request(self):
        self.adaptee.specific_request()
