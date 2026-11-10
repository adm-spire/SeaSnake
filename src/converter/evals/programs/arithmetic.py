def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b


def multiply(a: int, b: int) -> int:
    return a * b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b


def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("factorial is undefined for negative numbers")
    result = 1
    for number in range(2, n + 1):
        result *= number
    return result
