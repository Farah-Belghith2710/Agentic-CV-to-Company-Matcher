"""Runtime settings, read once from environment variables (and backend/.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

load_dotenv(BACKEND_DIR / ".env")


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: Path) -> Path:
    raw = _str(name)
    if not raw:
        return default
    p = Path(raw)
    return p if p.is_absolute() else (BACKEND_DIR / p)


@dataclass(frozen=True)
class Settings:
    # LLM (any OpenAI-compatible endpoint: OpenAI, Gemini, Groq, Ollama, OpenRouter, ...)
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_model_strong: str
    llm_max_rpm: int
    llm_concurrency: int
    llm_timeout: float
    force_offline: bool
    # Retrieval
    embeddings: str  # "auto" | "fastembed" | "tfidf"
    embed_model: str
    # Storage
    cache_dir: Path
    cache_enabled: bool
    snapshot_path: Path
    saved_path: Path  # jobs you saved from LinkedIn with the "Send to CV Matcher" button
    # Pipeline knobs
    shortlist_size: int
    min_relevant: int
    max_refinements: int
    max_rewrite_attempts: int
    bullets_per_job: int
    http_timeout: float

    @property
    def llm_configured(self) -> bool:
        if self.force_offline or not self.llm_model:
            return False
        local = any(h in self.llm_base_url for h in ("localhost", "127.0.0.1", "0.0.0.0"))
        return bool(self.llm_api_key) or local


def load_settings() -> Settings:
    model = _str("LLM_MODEL")
    return Settings(
        llm_base_url=_str("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_api_key=_str("LLM_API_KEY"),
        llm_model=model,
        llm_model_strong=_str("LLM_MODEL_STRONG") or model,
        llm_max_rpm=_int("LLM_MAX_RPM", 0),
        llm_concurrency=max(1, _int("LLM_CONCURRENCY", 4)),
        llm_timeout=float(_int("LLM_TIMEOUT", 90)),
        force_offline=_bool("FORCE_OFFLINE", False),
        embeddings=_str("EMBEDDINGS", "auto").lower(),
        embed_model=_str("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        cache_dir=_path("CACHE_DIR", BACKEND_DIR / ".cache"),
        cache_enabled=_bool("CACHE_ENABLED", True),
        snapshot_path=_path("SNAPSHOT_PATH", DATA_DIR / "demo_jobs.json"),
        saved_path=_path("SAVED_PATH", DATA_DIR / "saved_postings.json"),
        shortlist_size=max(3, _int("SHORTLIST_SIZE", 12)),
        min_relevant=max(1, _int("MIN_RELEVANT", 15)),
        max_refinements=max(0, _int("MAX_REFINEMENTS", 2)),
        max_rewrite_attempts=max(1, _int("MAX_REWRITE_ATTEMPTS", 3)),
        bullets_per_job=max(1, _int("BULLETS_PER_JOB", 3)),
        http_timeout=float(_int("HTTP_TIMEOUT", 20)),
    )


settings = load_settings()
