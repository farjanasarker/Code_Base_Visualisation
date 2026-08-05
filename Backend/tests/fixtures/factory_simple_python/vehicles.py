class Car:
    pass


class Truck:
    pass


class VehicleFactory:
    def create_car(self):
        return Car()

    def create_truck(self):
        return Truck()
