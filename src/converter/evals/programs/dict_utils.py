def get_value(mapping: dict[str, int], key: str) -> int:
    if key not in mapping:
        raise KeyError(key)
    return mapping[key]


def word_lengths(words: list[str]) -> dict[str, int]:
    result = {}
    for word in words:
        result[word] = len(word)
    return result


def merge_counts(first: dict[str, int], second: dict[str, int]) -> dict[str, int]:
    result = dict(first)
    for key, value in second.items():
        result[key] = result.get(key, 0) + value
    return result


def safe_get(mapping: dict[str, int], key: str, default: int) -> int:
    return mapping.get(key, default)
