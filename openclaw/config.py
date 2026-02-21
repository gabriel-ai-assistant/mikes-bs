"""Application configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


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


settings = Settings()
