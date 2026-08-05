class Shape:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def clone(self):
        return Shape(self.x, self.y)
