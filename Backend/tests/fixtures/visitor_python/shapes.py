class ShapeVisitor:
    def visit_circle(self, circle):
        circle.get_radius()

    def visit_square(self, square):
        square.get_side()


class Shape:
    def accept(self, visitor):
        raise NotImplementedError


class Circle(Shape):
    def __init__(self, radius):
        self.radius = radius

    def accept(self, visitor):
        visitor.visit_circle(self)

    def get_radius(self):
        return self.radius


class Square(Shape):
    def __init__(self, side):
        self.side = side

    def accept(self, visitor):
        visitor.visit_square(self)

    def get_side(self):
        return self.side
