"""Marginalis HTTP API. Serves precomputed results; nothing is re-estimated per request.

Run locally:  uv run uvicorn marginalis.api.app:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from marginalis import db
from marginalis.api import evidence as ev
from marginalis.api import service
from marginalis.api.ratelimit import limit_ask
from marginalis.config import BAS, ROOT, is_production

STATE: dict = {}


def load_profile() -> pd.DataFrame:
    with db.connect() as conn:
        cur = conn.execute("SELECT * FROM mef_profile")
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


WRITABLE_SQL = """
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND (has_table_privilege(c.oid, 'INSERT') OR has_table_privilege(c.oid, 'UPDATE')
        OR has_table_privilege(c.oid, 'DELETE') OR has_table_privilege(c.oid, 'TRUNCATE'))
"""


def assert_read_only() -> None:
    """Production refuses to start unless its database role can only read.

    The frozen artifacts (mef_profile, the views, the cleaned tables) can then not be
    modified by anything the public app does, whatever the code path.
    """
    with db.connect() as conn:
        writable = [r[0] for r in conn.execute(WRITABLE_SQL).fetchall()]
        can_create = conn.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')").fetchone()[0]
    if writable or can_create:
        raise RuntimeError(f"production DATABASE_URL role is not read-only (writable: {writable}, "
                           f"create on public: {can_create}); refusing to start")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if is_production():
        assert_read_only()
    STATE["profile"] = load_profile()
    ev.results()  # fail fast if the hold-out results file is missing
    yield
    STATE.clear()


app = FastAPI(title="Marginalis API", version="0.1.1", lifespan=lifespan,
              description="Marginal vs average CO2 intensity for ERCOT, CAISO and MISO (EIA-930).")


@app.exception_handler(service.BadRequest)
async def bad_request(_, exc: service.BadRequest):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mef_profile_rows": len(STATE.get("profile", []))}


@app.get("/api/bas")
def bas() -> list[dict]:
    """Each BA with what the pre-registered hold-out test supports."""
    return [{"ba_code": b.code, "name": b.name, "timezone": b.timezone,
             **{k: v for k, v in ev.ba_status(b.code).items() if k != "ba_code"}} for b in BAS.values()]


@app.get("/api/findings/{ba}")
def findings(ba: str) -> dict:
    ba = service.check_ba(ba)
    out = {"validation": ev.ba_status(ba), "usage": ev.calibration_note()}
    if ba == "MISO":
        out["overnight_check"] = ev.miso_overnight()
    return out


@app.get("/api/mef")
def mef(ba: str, spec: str = "demand", source: str = "eia",
        month: int | None = Query(None, ge=1, le=12), hour: int | None = Query(None, ge=0, le=23)) -> dict:
    return service.mef_rows(STATE["profile"], ba, spec, source, month, hour)


@app.get("/api/schedule")
def schedule(ba: str, day: date = Query(..., alias="date"), duration_h: int = 4, load_mwh: float = 100.0,
             earliest_hour: int | None = Query(None, ge=0, le=23),
             latest_hour: int | None = Query(None, ge=1, le=24), source: str = "eia") -> dict:
    """Marginal- vs average-optimal window for one local day, with what the hold-out supports."""
    return service.schedule(STATE["profile"], ba, day, duration_h, load_mwh, earliest_hour, latest_hour, source)


@app.get("/api/hours")
def hours(ba: str, start: date, end: date) -> dict:
    """Hourly data as reported (read-only), at most 31 days per request."""
    with db.connect() as conn:
        try:
            return service.hours(conn, ba, start, end)
        except service.BadRequest as exc:
            raise HTTPException(400, str(exc)) from exc


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


@app.post("/api/ask", dependencies=[Depends(limit_ask)])
def ask(req: AskRequest) -> dict:
    """Natural-language question, answered from mef_profile and the committed reports only."""
    from marginalis.ask import agent
    from marginalis.ask.groq_client import GroqClient, GroqError

    try:
        client = STATE.setdefault("groq", GroqClient())
        return agent.ask(req.question, client, STATE["profile"]).as_dict()
    except GroqError as exc:
        raise HTTPException(503, f"query layer unavailable: {exc}") from exc


# --- Static frontend (frontend/dist), served last so it never shadows /api ---------------
FRONTEND_DIST = ROOT / "frontend" / "dist"


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/") or not FRONTEND_DIST.exists():
        raise HTTPException(404)
    target = (FRONTEND_DIST / path).resolve()
    if path and target.is_file() and FRONTEND_DIST.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(FRONTEND_DIST / "index.html")  # client-side routes
