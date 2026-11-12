"""Test setup: a private SQLite file, seeded once, restored from a template per test."""
import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="flowguard-test-"))
os.environ["FLOWGUARD_DB"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["DEMO_MODE"] = "true"
os.environ["FLOWGUARD_DOC_DIR"] = str(_TMP / "documents")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, security  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed.reset import reset  # noqa: E402
from app.services import paths  # noqa: E402

DB, TEMPLATE = _TMP / "test.db", _TMP / "template.db"
DOCS, DOCS_TEMPLATE = _TMP / "documents", _TMP / "documents-template"
ROOT_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _restore():
    engine.dispose()
    for suffix in ("-wal", "-shm"):
        Path(str(DB) + suffix).unlink(missing_ok=True)
    shutil.copyfile(TEMPLATE, DB)
    shutil.rmtree(DOCS, ignore_errors=True)               # private document files restored with the database
    shutil.copytree(DOCS_TEMPLATE, DOCS)
    paths.clear_cache()
    security.throttle_clear()


@pytest.fixture(scope="session", autouse=True)
def _template():
    reset()
    with engine.connect() as c:
        c.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    engine.dispose()
    shutil.copyfile(DB, TEMPLATE)
    shutil.copytree(DOCS, DOCS_TEMPLATE)
    yield
    engine.dispose()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture()
def client():
    """A freshly seeded database for every test."""
    _restore()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(client):
    with SessionLocal() as s:
        yield s


def login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": config.DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture()
def auth(client):
    cache = {}

    def get(username):
        if username not in cache:
            cache[username] = login(client, username)
        return cache[username]
    return get


def stage_g1(client, auth, shipment="SHP-G1"):
    """Staged demo opening: driver moves G1 to the plant gate, then flooding is injected."""
    r = client.post(f"/api/transporter/shipments/{shipment}/milestones", headers=auth("driver1"),
                    json={"to_state": "AT_PLANT_GATE"})
    assert r.status_code == 200, r.text
    r = client.post("/api/simulations/disruptions", headers=auth("coordinator"), json={"preset": "FLOOD_R1"})
    assert r.status_code == 201, r.text
    return r.json()


def scenario(case, code):
    return next(s for s in case["scenarios"] if s["code"] == code)
