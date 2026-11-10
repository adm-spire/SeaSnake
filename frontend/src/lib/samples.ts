import type { EditableFile } from '../types';

export const DEFAULT_FILES: Record<EditableFile, string> = {
  'main.py': `def classify(n: int) -> str:
    """Return 'negative', 'zero' or 'positive' for an integer."""
    if n < 0:
        return "negative"
    if n == 0:
        return "zero"
    return "positive"


def safe_div(a: int, b: int) -> float:
    if b == 0:
        raise ValueError("division by zero")
    return a / b
`,
  'tests.py': `def test_classify_negative():
    assert classify(-3) == "negative"


def test_classify_zero():
    assert classify(0) == "zero"


def test_classify_positive():
    assert classify(4) == "positive"


def test_safe_div_ok():
    assert safe_div(6, 3) == 2.0


def test_safe_div_by_zero():
    with pytest.raises(ValueError, match="division by zero"):
        safe_div(1, 0)
`,
};
