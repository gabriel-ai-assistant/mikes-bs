"""Application configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+psycopg2://openclaw:password@postgis:5432/openclaw")

    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    NOTIFY_EMAIL: str = os.getenv("NOTIFY_EMAIL", "")

    COST_SHORT_PLAT_BASE: int = int(os.getenv("COST_SHORT_PLAT_BASE", "8000"))
    COST_ENGINEERING_PER_LOT: int = int(os.getenv("COST_ENGINEERING_PER_LOT", "6000"))
    COST_UTILITY_PER_LOT: int = int(os.getenv("COST_UTILITY_PER_LOT", "12000"))
    COST_BUILD_PER_SF: int = int(os.getenv("COST_BUILD_PER_SF", "185"))
    TARGET_HOME_SF: int = int(os.getenv("TARGET_HOME_SF", "2200"))
    ARV_MULTIPLIER: float = float(os.getenv("ARV_MULTIPLIER", "1.0"))

    LOB_API_KEY: str = os.getenv("LOB_API_KEY", "")
    SKIP_TRACE_API_KEY: str = os.getenv("SKIP_TRACE_API_KEY", "")
    SKIP_TRACE_ENABLED: bool = _env_bool("SKIP_TRACE_ENABLED", False)
    SKIP_TRACE_RATE_LIMIT_PER_MIN: int = int(os.getenv("SKIP_TRACE_RATE_LIMIT_PER_MIN", "10"))
    SKIP_TRACE_MAX_RETRIES: int = int(os.getenv("SKIP_TRACE_MAX_RETRIES", "3"))
    BUSINESS_FILINGS_ENABLED: bool = _env_bool("BUSINESS_FILINGS_ENABLED", False)
    ENRICHMENT_RETENTION_DAYS: int = int(os.getenv("ENRICHMENT_RETENTION_DAYS", "365"))
    OSINT_BASE_URL: str = os.getenv("OSINT_BASE_URL", "http://localhost:8450/api")
    OSINT_TIMEOUT_SECONDS: int = int(os.getenv("OSINT_TIMEOUT_SECONDS", "90"))
    OSINT_BATCH_LIMIT: int = int(os.getenv("OSINT_BATCH_LIMIT", "20"))
    OSINT_BATCH_ENABLED: bool = _env_bool("OSINT_BATCH_ENABLED", True)
    OSINT_UI_URL: str = os.getenv("OSINT_UI_URL", "")
    OSINT_ENABLED: bool = _env_bool("OSINT_ENABLED", True)
    EXPORT_MAX_ROWS: int = int(os.getenv("EXPORT_MAX_ROWS", "10000"))
    REMINDER_CHECK_INTERVAL_MIN: int = int(os.getenv("REMINDER_CHECK_INTERVAL_MIN", "5"))
    REMINDER_EMAIL_ENABLED: bool = _env_bool("REMINDER_EMAIL_ENABLED", False)


settings = Settings()
