"""Translation and repair prompts plus the LLM-facing translator."""

from .translator import repair_c, translate_to_c

__all__ = ["repair_c", "translate_to_c"]
