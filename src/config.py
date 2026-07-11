"""Central configuration for DrugLens.

All model endpoints, credentials, and feature flags resolve from environment
variables here (``.env`` is loaded by the entry points before this module is
imported). Other modules must reference these values at call time
(``config.FIREWORKS_API_KEY``) rather than copying them, so tests and the UI
can override a single source of truth.
"""

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

# Feature flags (defaults for the UI toggles; CPU-only deployments set these
# to false so no local vLLM connection is attempted)
USE_LLM_PARSER = os.getenv("USE_LLM_PARSER", "false").lower() == "true"
USE_TXGEMMA = os.getenv("USE_TXGEMMA", "false").lower() == "true"
USE_GEMMA4 = os.getenv("USE_GEMMA4", "true").lower() == "true"
