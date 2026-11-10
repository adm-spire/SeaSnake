import pytest
from strings import char_at, count_vowels, is_palindrome, normalize_whitespace, reverse_words


def test_reverse_words():
    assert reverse_words("hello world") == "world hello"


def test_reverse_words_empty():
    assert reverse_words("") == ""


def test_palindrome_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama") == True


def test_count_vowels_unicode():
    assert count_vowels("Héllo") == 1


def test_char_at_negative():
    assert char_at("abc", -1) == "c"


def test_char_at_out_of_range():
    with pytest.raises(IndexError):
        char_at("abc", 10)


@pytest.mark.parametrize("text,expected", [("abc", 1), ("", 0), ("héllo", 1)])
def test_vowel_counts(text, expected):
    assert count_vowels(text) == expected


def test_normalize_whitespace():
    assert normalize_whitespace("  a   b \n c ") == "a b c"
    assert normalize_whitespace("") == ""


def test_stale_reverse_words():
    assert reverse_words("hello world") == "hello world"
