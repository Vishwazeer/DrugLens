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

# Cloud report/synthesis model served by Fireworks. This is the third,
# cloud-side model of the pipeline (the local MedGemma/TxGemma models handle
# parsing and DDI prediction on the AMD pod). It is model-agnostic — set
# REPORT_MODEL to any chat model your Fireworks account can serve. The legacy
# GEMMA_MODEL variable is still honored for backward compatibility.
REPORT_MODEL = os.getenv(
    "REPORT_MODEL",
    os.getenv("GEMMA_MODEL", "accounts/fireworks/models/deepseek-v4-pro"),
)
# Whether to request Fireworks structured-JSON mode for the report call.
# Reasoning models emit chain-of-thought before the JSON otherwise, which
# breaks strict parsing; JSON mode forces a clean object.
REPORT_JSON_MODE = os.getenv("REPORT_JSON_MODE", "true").lower() == "true"
# Max completion tokens for the report call. Reasoning models spend a large,
# variable share on hidden reasoning before the JSON, so this needs headroom
# beyond the ~1k tokens the report object itself uses.
REPORT_MAX_TOKENS = int(os.getenv("REPORT_MAX_TOKENS", "4096"))

# Feature flags (defaults for the UI toggles; CPU-only deployments set these
# to false so no local vLLM connection is attempted)
USE_LLM_PARSER = os.getenv("USE_LLM_PARSER", "false").lower() == "true"
USE_TXGEMMA = os.getenv("USE_TXGEMMA", "false").lower() == "true"
USE_GEMMA4 = os.getenv("USE_GEMMA4", "true").lower() == "true"
