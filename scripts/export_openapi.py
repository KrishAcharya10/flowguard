"""Export the OpenAPI contract from the running app code (never written by hand).

Run:  backend/.venv/Scripts/python scripts/export_openapi.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402

out = ROOT / "contracts" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print("wrote", out)
