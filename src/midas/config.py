"""Midas configuration — reads all settings from .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///midas.db")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# LLM
OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_PROD_MODEL: str = os.environ.get("OPENAI_PROD_MODEL", "gpt-4o")
OPENAI_DEV_MODEL: str = os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini")
DEFAULT_LLM_MODEL: str = os.environ.get("DEFAULT_LLM_MODEL", OPENAI_PROD_MODEL)

# Data sources
EODHD_API_KEY: str | None = os.environ.get("EODHD_API_KEY")
PERPLEXITY_API_KEY: str | None = os.environ.get("PERPLEXITY_API_KEY")
FRED_API_KEY: str | None = os.environ.get("FRED_API_KEY")

# IBKR
IBKR_CLIENT_ID: str = os.environ.get("IBKR_CLIENT_ID", "midas")
IBKR_ACCOUNT_ID: str | None = os.environ.get("IBKR_ACCOUNT_ID")

# Application
APP_ENV: str = os.environ.get("APP_ENV", "development")
DEBUG: bool = os.environ.get("DEBUG", "true").lower() in ("true", "1", "yes")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

# Base directory for file paths
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
