def parse_positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise ValueError("value must be positive")
    return value


def clamp(value: int, low: int, high: int) -> int:
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(high, value))


def is_balanced(text: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for character in text:
        if character in "([{":
            stack.append(character)
        elif character in ")]}":
            if not stack or stack.pop() != pairs[character]:
                return False
    return not stack
