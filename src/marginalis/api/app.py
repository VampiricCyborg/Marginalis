"""Marginalis HTTP API. Serves precomputed results; nothing is re-estimated per request.

Run locally:  uv run uvicorn marginalis.api.app:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from marginalis import db
from marginalis.api import evidence as ev
from marginalis.api import service
from marginalis.config import BAS

STATE: dict = {}


def load_profile() -> pd.DataFrame:
    with db.connect() as conn:
        cur = conn.execute("SELECT * FROM mef_profile")
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


@asynccontextmanager
async def lifespan(_: FastAPI):
    STATE["profile"] = load_profile()
    ev.results()  # fail fast if the hold-out results file is missing
    yield
    STATE.clear()


app = FastAPI(title="Marginalis API", version="0.1.0", lifespan=lifespan,
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


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """Natural-language question, answered from mef_profile and the committed reports only."""
    from marginalis.ask import agent
    from marginalis.ask.groq_client import GroqClient, GroqError

    try:
        client = STATE.setdefault("groq", GroqClient())
        return agent.ask(req.question, client, STATE["profile"]).as_dict()
    except GroqError as exc:
        raise HTTPException(503, f"query layer unavailable: {exc}") from exc
