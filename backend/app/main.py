"""FlowGuard API. Run with ONE worker:  uvicorn app.main:app --port 8000

FastAPI serves the API and, when it exists, the production frontend build
(same origin, SPA fallback). No CDN, paid API or live external service is needed.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from . import models as m
from . import schemas as s
from .api import coordinator, extras, public
from .db import Base, SessionLocal, engine
from .simulator.runner import run_forever

# The app shell must never be cached: after a rebuild the browser has to fetch the new index.html.
NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        empty = db.get(m.SimulationState, 1) is None
    if empty and config.DEMO_MODE:
        from .seed.reset import reset
        reset()
    runner = asyncio.create_task(run_forever())      # ONE task; idle while the clock is paused
    try:
        yield
    finally:
        runner.cancel()


app = FastAPI(
    title="FlowGuard - Order-to-Delivery Control Tower",
    version="1.0.0",
    description="Hackathon prototype for the fictional Plant X. All data is fictional. ETA and risk come from a "
                "transparent Monte Carlo simulation and deterministic rules - not a trained ML model and not "
                "runtime generative AI.",
    lifespan=lifespan,
)
app.include_router(public.router)
app.include_router(coordinator.router)
app.include_router(extras.router)


def _built_at():
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(index.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@app.get("/health", response_model=s.HealthOut, tags=["health"])
def health():
    return s.HealthOut(status="ok", demo_mode=config.DEMO_MODE, frontend_built_at=_built_at())


if (FRONTEND_DIST / "assets").is_dir():
    class ImmutableAssets(StaticFiles):
        """Hashed build files never change: cache them hard."""

        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp

    app.mount("/assets", ImmutableAssets(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    """SPA fallback: any non-API path returns the built index.html."""
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(404, "Frontend build not found. Run: npm --prefix frontend run build")
    candidate = (FRONTEND_DIST / full_path).resolve()
    if full_path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
        return FileResponse(candidate, headers=NO_CACHE)
    return FileResponse(index, headers=NO_CACHE)
