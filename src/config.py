import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Model endpoints
MEDGEMMA_BASE_URL = os.getenv("MEDGEMMA_BASE_URL", "http://localhost:8001/v1")
MEDGEMMA_MODEL = os.getenv("MEDGEMMA_MODEL", "google/medgemma-4b-it")
TXGEMMA_BASE_URL = os.getenv("TXGEMMA_BASE_URL", "http://localhost:8002/v1")
TXGEMMA_MODEL = os.getenv("TXGEMMA_MODEL", "google/txgemma-2b-it")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")
FIREWORKS_BASE_URL = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "accounts/fireworks/models/gemma-4-31b-it")

# Feature flags
USE_LLM_PARSER = os.getenv("USE_LLM_PARSER", "true").lower() == "true"
USE_TXGEMMA = os.getenv("USE_TXGEMMA", "true").lower() == "true"
USE_GEMMA4 = os.getenv("USE_GEMMA4", "true").lower() == "true"
