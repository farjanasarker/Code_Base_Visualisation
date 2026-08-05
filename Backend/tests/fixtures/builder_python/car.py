class Car:
    pass


class CarBuilder:
    def __init__(self):
        self.seats = 0
        self.engine = None

    def set_seats(self, seats):
        self.seats = seats
        return self

    def set_engine(self, engine):
        self.engine = engine
        return self

    def build(self):
        return Car()
