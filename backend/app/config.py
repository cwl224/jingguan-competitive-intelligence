from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_path(value: str | None) -> Path:
    backend_root = Path(__file__).resolve().parents[1]
    if not value:
        return backend_root / "data" / "jinguan.db"
    path = Path(value)
    return path if path.is_absolute() else backend_root / path


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "镜观 Agent 竞品分析 API"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    database_path: Path = Path("data/jinguan.db")
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    default_user_id: str = "user_lin_che"
    auth_secret: str = "development-only-change-me"
    auth_token_ttl_minutes: int = 60
    allow_legacy_user_header: bool = True
    collector_user_agent: str = "JinguanCollector/0.2 (+compliance-contact@example.com)"
    collector_max_response_bytes: int = 5 * 1024 * 1024
    collector_allow_private_networks: bool = False
    scheduler_enabled: bool = True
    scheduler_poll_seconds: int = 30
    scheduler_max_concurrency: int = 4
    scheduler_dispatch_batch: int = 20
    ocr_enabled: bool = True
    ocr_command: str = "tesseract"
    ocr_languages: str = "chi_sim+eng"
    ocr_timeout_seconds: int = 60
    near_duplicate_threshold: float = 0.82


def load_settings() -> Settings:
    backend_root = Path(__file__).resolve().parents[1]
    load_dotenv(backend_root / ".env", override=False)
    cors = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    )
    environment = os.getenv("APP_ENV", "development")
    return Settings(
        environment=environment,
        debug=_as_bool(os.getenv("APP_DEBUG"), True),
        database_path=_database_path(os.getenv("DATABASE_PATH")),
        cors_origins=cors or DEFAULT_CORS_ORIGINS,
        default_user_id=os.getenv("DEFAULT_USER_ID", "user_lin_che"),
        auth_secret=os.getenv("AUTH_SECRET", "development-only-change-me"),
        auth_token_ttl_minutes=max(
            1, int(os.getenv("AUTH_TOKEN_TTL_MINUTES", "60"))
        ),
        allow_legacy_user_header=_as_bool(
            os.getenv("ALLOW_LEGACY_USER_HEADER"), environment in {"development", "test"}
        ),
        collector_user_agent=os.getenv(
            "COLLECTOR_USER_AGENT",
            "JinguanCollector/0.2 (+compliance-contact@example.com)",
        ),
        collector_max_response_bytes=int(
            os.getenv("COLLECTOR_MAX_RESPONSE_BYTES", str(5 * 1024 * 1024))
        ),
        collector_allow_private_networks=_as_bool(
            os.getenv("COLLECTOR_ALLOW_PRIVATE_NETWORKS"), False
        ),
        scheduler_enabled=_as_bool(os.getenv("SCHEDULER_ENABLED"), True),
        scheduler_poll_seconds=max(5, int(os.getenv("SCHEDULER_POLL_SECONDS", "30"))),
        scheduler_max_concurrency=max(
            1, int(os.getenv("SCHEDULER_MAX_CONCURRENCY", "4"))
        ),
        scheduler_dispatch_batch=max(
            1, int(os.getenv("SCHEDULER_DISPATCH_BATCH", "20"))
        ),
        ocr_enabled=_as_bool(os.getenv("OCR_ENABLED"), True),
        ocr_command=os.getenv("OCR_COMMAND", "tesseract").strip() or "tesseract",
        ocr_languages=os.getenv("OCR_LANGUAGES", "chi_sim+eng").strip()
        or "chi_sim+eng",
        ocr_timeout_seconds=max(5, int(os.getenv("OCR_TIMEOUT_SECONDS", "60"))),
        near_duplicate_threshold=min(
            0.99,
            max(0.5, float(os.getenv("NEAR_DUPLICATE_THRESHOLD", "0.82"))),
        ),
    )
