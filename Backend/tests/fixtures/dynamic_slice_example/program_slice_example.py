"""Canonical dynamic-slicing example (CodeLens spec §10 / textbook Fig 6.9)."""


def f1(x):
    return x


def g1(x):
    return x


def f2(x):
    return x


def g2(x):
    return x


def f3(x):
    return x


def g3(x):
    return x


def write(value):
    pass


def f(X):
    if X < 0:
        Y = f1(X)
        Z = g1(X)
    else:
        if X == 0:
            Y = f2(X)
            Z = g2(X)
        else:
            Y = f3(X)
            Z = g3(X)
    write(Y)
    write(Z)
