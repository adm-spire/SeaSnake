"""Environment-driven settings.

Every secret and tunable comes from the environment (or a local .env file).
Nothing is hard-coded. Field names map to upper-case environment variables,
for example ``llm_api_key`` <- ``LLM_API_KEY``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM provider (OpenAI-compatible chat completions; DeepSeek by default).
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_timeout_s: float = 120.0
    llm_max_retries: int = 3
    llm_temperature: float = 0.0

    # Deep-agent translator. When enabled, the translate/repair nodes run an
    # autonomous filesystem + build/test loop instead of a single LLM call.
    # ``deep_agent_max_steps`` is the LangGraph recursion limit for that inner
    # graph (each model/tool turn consumes steps).
    deep_agent_enabled: bool = True
    deep_agent_max_steps: int = 60

    # Optional local observability. MLflow writes traces to a local directory;
    # no account or hosted service is required.
    mlflow_enabled: bool = True
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    mlflow_experiment_name: str = "python-to-rust"

    # Sandbox.
    sandbox_mode: Literal["docker", "subprocess"] = "docker"
    sandbox_image: str = "converter-sandbox:latest"
    sandbox_fallback_to_subprocess: bool = True
    sandbox_memory_mb: int = 512
    sandbox_cpus: float = 1.0
    sandbox_pids_limit: int = 128
    test_timeout_s: int = 5
    compile_timeout_s: int = 60
    run_timeout_s: int = 120

    # Conversion limits.
    max_source_lines: int = 500
    max_attempts: int = 3
    max_generation_rounds: int = 2

    # API.
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Logging.
    log_level: str = "INFO"

    # Optional price table, USD per 1K tokens. Defaults to zero so a run without
    # pricing configured never reports a misleading cost.
    prompt_cost_per_1k: float = 0.0
    completion_cost_per_1k: float = 0.0

    # Pass criteria defaults (per category).
    edge_case_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    strict_threshold: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one process-wide Settings instance (cached)."""
    return Settings()
