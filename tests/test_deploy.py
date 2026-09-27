"""Production hardening: rate limit on /api/ask, read-only DB role, CLI guard."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from marginalis.api import ratelimit


def _req(xff=None, host="10.0.0.1", cf=None):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    if cf:
        headers.append((b"cf-connecting-ip", cf.encode()))
    return Request({"type": "http", "headers": headers, "client": (host, 1234)})


def test_limiter_caps_per_ip_and_reports_retry_after():
    t = [1000.0]
    rl = ratelimit.RateLimiter(5, clock=lambda: t[0])
    for _ in range(5):
        rl.check("1.1.1.1")
    with pytest.raises(HTTPException) as e:
        rl.check("1.1.1.1")
    assert e.value.status_code == 429 and e.value.headers["Retry-After"] == "60"
    rl.check("2.2.2.2")  # other IPs unaffected
    t[0] += 61
    rl.check("1.1.1.1")  # window has passed


def test_client_ip_uses_cloudflare_header_never_x_forwarded_for():
    assert ratelimit.client_ip(_req("6.6.6.6", cf="203.0.113.9")) == "203.0.113.9"
    # A forged X-Forwarded-For never changes the key.
    assert ratelimit.client_ip(_req("6.6.6.6")) == "10.0.0.1"
    assert ratelimit.client_ip(_req("7.7.7.7, 8.8.8.8")) == "10.0.0.1"


def test_ask_endpoint_returns_429_after_limit(monkeypatch):
    from marginalis.api import app as appmod
    from marginalis.ask import agent

    class Ans:
        def as_dict(self):
            return {"answer": "ok"}

    monkeypatch.setattr(ratelimit, "ask_limiter", ratelimit.RateLimiter(2))
    monkeypatch.setattr(agent, "ask", lambda *a, **k: Ans())
    monkeypatch.setitem(appmod.STATE, "groq", object())
    monkeypatch.setitem(appmod.STATE, "profile", None)
    client = TestClient(appmod.app)  # no lifespan: no DB needed
    h = {"CF-Connecting-IP": "198.51.100.7"}
    assert [client.post("/api/ask", json={"question": "hello?"}, headers=h).status_code for _ in range(3)] == [200, 200, 429]
    forged = {"CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": "9.9.9.9"}
    assert client.post("/api/ask", json={"question": "hello?"}, headers=forged).status_code == 429


@pytest.mark.parametrize("cmd", ["ingest", "build", "report", "analyze", "evaluate"])
def test_mutating_cli_commands_refused_in_production(monkeypatch, cmd):
    from marginalis import cli

    monkeypatch.setenv("MARGINALIS_ENV", "production")
    with pytest.raises(SystemExit) as e:
        cli.main([cmd])
    assert e.value.code == 2


def _local_db():
    import psycopg

    from marginalis.db import DEFAULT_URL
    try:
        return psycopg.connect(DEFAULT_URL, connect_timeout=2, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("local Postgres not running")


def test_read_only_check_passes_for_select_only_role_and_fails_for_owner(monkeypatch):
    from marginalis.api import app as appmod

    owner = _local_db()
    owner.execute("DROP ROLE IF EXISTS marginalis_ro_test")
    owner.execute("CREATE ROLE marginalis_ro_test LOGIN PASSWORD 'ro'")
    try:
        owner.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO marginalis_ro_test")
        owner.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        monkeypatch.setenv("DATABASE_URL", "postgresql://marginalis_ro_test:ro@localhost:5433/marginalis")
        appmod.assert_read_only()  # passes
        monkeypatch.setenv("DATABASE_URL", "postgresql://marginalis:marginalis@localhost:5433/marginalis")
        with pytest.raises(RuntimeError, match="not read-only"):
            appmod.assert_read_only()
    finally:
        owner.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM marginalis_ro_test")
        owner.execute("DROP ROLE marginalis_ro_test")
