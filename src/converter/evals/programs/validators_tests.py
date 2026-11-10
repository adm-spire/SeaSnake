import pytest
from validators import clamp, is_balanced, parse_positive_int


def test_parse_positive():
    assert parse_positive_int("42") == 42


def test_parse_negative():
    with pytest.raises(ValueError):
        parse_positive_int("-1")


def test_parse_not_a_number():
    pytest.raises(ValueError, parse_positive_int, "abc")


def test_clamp_high():
    assert clamp(15, 0, 10) == 10


def test_clamp_low():
    assert clamp(-5, 0, 10) == 0


def test_clamp_invalid_bounds():
    with pytest.raises(ValueError):
        clamp(5, 10, 0)


def test_balanced():
    assert is_balanced("([]{})") == True


def test_unbalanced():
    assert is_balanced("([)]") == False
