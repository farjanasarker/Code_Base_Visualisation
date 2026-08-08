class Circle:
    pass


class Square:
    pass


class Rectangle:
    pass


class ShapeFactory:
    def get_shape(self, shape_type):
        if shape_type == "CIRCLE":
            return Circle()
        elif shape_type == "SQUARE":
            return Square()
        elif shape_type == "RECTANGLE":
            return Rectangle()
        return None
