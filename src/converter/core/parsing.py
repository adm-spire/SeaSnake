"""Helpers for extracting code and JSON from free-form LLM responses.

LLMs often wrap JSON in prose or markdown fences. These helpers are deliberately
tolerant because a malformed extraction should surface as a clear LLMError, not
as a mysterious downstream crash.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .errors import LLMError

_FENCE_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_+-]*)\s*\n(?P<body>.*?)```", re.DOTALL)


def extract_code_block(text: str, language: str = "c") -> str:
    """Return the first fenced block for ``language``, else the first fence, else text."""
    matches = list(_FENCE_RE.finditer(text))
    for match in matches:
        if match.group("lang").lower() == language.lower():
            return match.group("body").strip() + "\n"
    if matches:
        return matches[0].group("body").strip() + "\n"
    return text.strip() + "\n"


def parse_json(text: str) -> Any:
    """Parse JSON that may be wrapped in prose or a markdown fence."""
    candidate = text.strip()

    fenced = extract_code_block(candidate, "json")
    if fenced.strip() != candidate:
        candidate = fenced.strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(candidate):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(candidate[index:])
            return value
        except json.JSONDecodeError:
            continue

    raise LLMError("LLM response did not contain valid JSON")
