"""Translation and repair prompts plus the LLM-facing translator."""

from .translator import repair_rust, translate_to_rust

__all__ = ["repair_rust", "translate_to_rust"]
