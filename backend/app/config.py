"""Runtime configuration, read from the environment (see .env.example)."""
import os
import secrets

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
DB_URL = os.getenv("FLOWGUARD_DB", "sqlite:///./flowguard.db")
GLOBAL_SEED = int(os.getenv("FLOWGUARD_GLOBAL_SEED", "20261116"))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60
DEMO_PASSWORD = os.getenv("FLOWGUARD_DEMO_PASSWORD", "PlantX-demo-2026")

_secret = os.getenv("FLOWGUARD_JWT_SECRET")
if not _secret:
    if not DEMO_MODE:
        raise RuntimeError("FLOWGUARD_JWT_SECRET must be set when DEMO_MODE is not true")
    _secret = secrets.token_hex(32)   # demo only: random per process, never committed
JWT_SECRET = _secret

# Private document storage (invoices and proof of delivery). Never served as static files.
from pathlib import Path  # noqa: E402

DOC_DIR = Path(os.getenv("FLOWGUARD_DOC_DIR", str(Path(__file__).resolve().parents[1] / "storage" / "documents")))
MAX_UPLOAD_MB = float(os.getenv("FLOWGUARD_MAX_UPLOAD_MB", "10"))
MAX_UPLOAD_BYTES = int(MAX_UPLOAD_MB * 1024 * 1024)
