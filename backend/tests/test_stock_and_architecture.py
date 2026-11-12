"""Hand-calculated stock examples, and architecture rules enforced by scanning the source."""
import ast
import re
from pathlib import Path

import numpy as np
import pytest

from app import models as m
from app.engine.contracts import StockParams
from app.engine.stock import stockout_hours
from app.seeds import seed_pred, seed_truth

APP = Path(__file__).resolve().parents[1] / "app"


def one(lots, s, r, u):
    return float(stockout_hours([(np.array([t]), q) for t, q in lots], StockParams(s, r, u))[0])


def test_stock_adequate():
    # S = 20, lot arrives T = 10, u = 1 -> A = 11 < 20 -> no stock-out
    assert one([(10.0, 24.0)], 20.0, 2.0, 1.0) == 0.0


def test_stock_single_lot_after_depletion():
    # S = 12, T = 14, u = 0.5 -> A = 14.5 -> stock-out 2.5 h
    assert one([(14.0, 24.0)], 12.0, 2.0, 0.5) == pytest.approx(2.5)


def test_stock_split_urgent_arrives_after_depletion():
    # S = 12; urgent T = 13 (A = 13.5, 8 t), remainder T = 19 (A = 19.5, 16 t), r = 2 t/h, u = 0.5
    # urgent: +1.5 h; cover_end = 13.5 + 4 = 17.5; remainder: +2.0 h; total 3.5 h
    assert one([(13.0, 8.0), (19.0, 16.0)], 12.0, 2.0, 0.5) == pytest.approx(3.5)


def test_stock_remainder_arrives_before_urgent():
    # S = 12; remainder T = 11 (A = 11.5, 16 t) arrives first: no stock-out; cover_end = max(12, 11.5) + 8 = 20
    # urgent T = 13 (A = 13.5) -> before 20 -> no stock-out. Order of the list must not matter.
    assert one([(13.0, 8.0), (11.0, 16.0)], 12.0, 2.0, 0.5) == 0.0
    assert one([(11.0, 16.0), (13.0, 8.0)], 12.0, 2.0, 0.5) == 0.0


# ---------- architecture ----------
def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
            names |= {"." * node.level + (node.module or "") + "." + a.name for a in node.names}
    return names


def test_engine_imports_no_framework_and_no_simulator():
    for f in (APP / "engine").glob("*.py"):
        for name in _imports(f):
            assert not re.search(r"fastapi|sqlalchemy|simulator|services|models", name), f"{f.name} imports {name}"


def test_mapping_layer_never_imports_the_simulator():
    for f in ("services/mapping.py", "services/predictions.py", "services/warroom.py", "services/alerts.py",
              "services/views.py", "services/paths.py"):
        for name in _imports(APP / f):
            assert "simulator" not in name, f"{f} imports {name}"


def test_no_wall_clock_or_python_hash_in_business_logic():
    banned = re.compile(r"datetime\.now\(|datetime\.utcnow\(|time\.time\(|(?<![\w.])hash\(")
    for f in APP.rglob("*.py"):
        if f.name == "security.py":                # token expiry / login throttle only (documented exception)
            continue
        text = "\n".join(line.split("#")[0] for line in f.read_text(encoding="utf-8").splitlines()
                         if not line.strip().startswith(('"""', "#")))
        hit = banned.search(text)
        assert hit is None, f"{f.relative_to(APP)} uses {hit.group(0)}"


def test_only_one_eta_engine_function():
    hits = [f.name for f in APP.rglob("*.py") if "def simulate_arrival(" in f.read_text(encoding="utf-8")]
    assert hits == ["eta.py"]


def test_prediction_and_truth_seeds_differ_for_every_seeded_shipment(db):
    st = db.get(m.SimulationState, 1)
    rows = db.query(m.Shipment).all()
    assert len(rows) >= 150
    for sh in rows:
        assert seed_pred(st.global_seed, sh.id) != seed_truth(st.global_seed, sh.id, sh.route_id, sh.lot_type)


def test_seed_meets_data_requirements(db):
    active = db.query(m.Shipment).filter(m.Shipment.is_historical.is_(False)).count()
    hist = db.query(m.Shipment).filter(m.Shipment.is_historical.is_(True))
    assert 12 <= active <= 14
    assert hist.count() >= 150
    assert len({s.route_id for s in hist}) >= 4 and len({s.transporter_id for s in hist}) >= 3
    span = max(s.arrived_at for s in hist) - min(s.arrived_at for s in hist)
    assert span.days >= 49
    assert db.query(m.Customer).count() >= 3
