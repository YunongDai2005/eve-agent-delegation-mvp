import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)
DATA_DIR = Path(os.getenv("EVE_DATA_DIR", str(ROOT / "runtime"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
AGENT_URL = os.getenv("EVE_AGENT_URL", "http://127.0.0.1:9101").rstrip("/")
TOOL_TIMEOUT = float(os.getenv("EVE_TOOL_TIMEOUT", "45"))
TOTAL_TIMEOUT = float(os.getenv("EVE_TOTAL_TIMEOUT", "120"))
