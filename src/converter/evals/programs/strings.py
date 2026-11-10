def reverse_words(text: str) -> str:
    return " ".join(reversed(text.split()))


def is_palindrome(text: str) -> bool:
    cleaned = [character.lower() for character in text if character.isalnum()]
    return cleaned == cleaned[::-1]


def count_vowels(text: str) -> int:
    return sum(1 for character in text.lower() if character in "aeiou")


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def char_at(text: str, index: int) -> str:
    try:
        return text[index]
    except IndexError:
        raise IndexError("string index out of range") from None
