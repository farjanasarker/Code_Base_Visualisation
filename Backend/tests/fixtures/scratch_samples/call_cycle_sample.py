def a():
    b()
    d()

def b():
    print("hello")
    c()

def c():
    print("world")
    d()

def d():
    print("d")
    c()