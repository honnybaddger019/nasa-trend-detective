
"""Central project settings."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
NASA_DATA_PATH = DATA_DIR / "nasa_data.csv"

# Load environment variables from the project root
load_dotenv(PROJECT_ROOT / ".env")

# Groq configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b",
)

# Forecast configuration
DEFAULT_FORECAST_MONTHS = int(
    os.getenv("DEFAULT_FORECAST_MONTHS", "36")
)

DEFAULT_BACKTEST_MONTHS = int(
    os.getenv("DEFAULT_BACKTEST_MONTHS", "36")
)
