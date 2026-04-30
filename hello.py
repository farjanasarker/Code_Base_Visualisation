def a():
    b()

def b():
    print("hello")
    c()

def c():
    print("world")
    d()

def d():
    print("d")