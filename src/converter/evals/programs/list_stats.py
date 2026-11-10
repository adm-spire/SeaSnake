def total(values: list[int]) -> int:
    return sum(values)


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean of empty list")
    return sum(values) / len(values)


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("median of empty list")
    ordered = sorted(values)
    length = len(ordered)
    middle = length // 2
    if length % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def index_of(values: list[int], target: int) -> int:
    return values.index(target)
