# Marginalis

*When you run flexible load matters. The obvious answer is often wrong.*

Most "run it when the grid is green" advice uses **average** carbon intensity.
The quantity that matters for a scheduling decision is the **marginal**
emissions factor: how much CO₂ changes when one more MWh of load is added.
Marginalis estimates marginal emissions factors from public EIA-930 hourly data
for three US balancing authorities (ERCOT, CAISO, MISO), 2019-07 → 2026-08,
and measures how often scheduling by average intensity picks a worse hour.

**Live:** <https://marginalis-5xm3.onrender.com> (read-only; free tier, so the first request after idle can take ~1 minute to wake).

## Methodology

- **Data.** EIA-930 hourly demand, net generation, interchange and generation by
  fuel type, stored in UTC; local time is derived in the database. Hourly
  temperature from Open-Meteo, simple average of four load centres per BA.
- **Emissions.** Two series, compared against each other:
  - *Derived* — generation by fuel × a published CO₂ rate per fuel (sources in
    [`data/README.md`](data/README.md)).
  - *Published* — EIA's own hourly CO₂ estimates from the Grid Monitor files.
- **Estimator.** First-difference regression of ΔCO₂ on Δdemand within strata
  (Hawkes 2010; Siler-Evans, Azevedo & Morgan 2012). Robustness check on
  Δ(in-BA fossil generation). Net-import share reported per BA.
- **Validation.** Train 2019-07 → 2024-12; hold out 2025, with 2026 YTD as a
  second check. Evaluation criteria are fixed in
  [`docs/preregistration.md`](docs/preregistration.md) before any hold-out read.

### What the derived marginal factors mean

Because the derived series uses **one CO₂ rate per fuel**, its marginal factors
reflect **which fuel ramps** from hour to hour, **not the efficiency of the
plants that ramp**. A modern combined-cycle unit and an old gas peaker get the
same rate. Plant-level CEMS data (EPA CAMPD) would address this and is a
stretch goal.

## Running it

```bash
docker compose up -d                 # local Postgres
uv sync
uv run marginalis ingest             # raw EIA-930, Grid Monitor workbooks, weather
uv run marginalis build              # clean, validate, load
uv run marginalis report             # reports/data_quality.md
uv run marginalis evaluate           # pre-registered hold-out evaluation (method is frozen)

cd frontend && npm install && npm run build && cd ..
uv run uvicorn marginalis.api.app:app   # API + frontend on http://localhost:8000
```

`/api/ask` needs `GROQ_API_KEY` in `.env`. For frontend development, run `npm run dev` in
`frontend/` (it proxies `/api` to port 8000).

The frontend only displays what the API returns. Hold-out validation is shown on every
chart and card: MISO is validated, and ERCOT and CAISO are marked "Not validated" wherever
their numbers appear.

## Deployment (Render + Neon)

Production is a **read-only copy of the frozen results**. Nothing is ingested, rebuilt or
re-estimated in production.

1. **Database (Neon, AWS us-east-2).** Restore a dump of the frozen local database (not a
   re-run of `ingest`/`build`), then create the read-only role and verify the copy:
   ```bash
   docker compose exec -T db pg_dump -U marginalis -d marginalis -Fc --no-owner --no-privileges > marginalis.dump
   pg_restore --no-owner --no-privileges -d "$NEON_DIRECT_OWNER_URL" marginalis.dump
   psql "$NEON_DIRECT_OWNER_URL" -v pw="'<strong password>'" -f db/deploy/readonly_role.sql
   uv run python scripts/verify_db.py "$NEON_URL"   # must match the local fingerprint
   ```
   Use the direct (non-`-pooler`) host for the restore and the **pooled** host for the app.
2. **App (Render).** New → Blueprint → this repository (`render.yaml`). Set the two secrets
   in the dashboard:
   - `DATABASE_URL`: the Neon **pooled** URL for the `marginalis_app` role.
   - `GROQ_API_KEY`: for `/api/ask`.

   The Docker image builds the frontend and serves it from FastAPI. `EIA_API_KEY` is not
   needed in production.

**Read-only guarantees, layered:**
- The app's database role can only `SELECT`, and it is read-only at the role level.
- With `MARGINALIS_ENV=production`, the app refuses to start if its role can write anything.
- The mutating CLI commands (`ingest`, `build`, `report`, `analyze`, `evaluate`) exit in
  production.
- No HTTP route reaches them.

`/api/ask` is limited to `ASK_RATE_PER_MINUTE` (default 5) requests per client per minute. The client
key is Cloudflare's `CF-Connecting-IP`, not `X-Forwarded-For`: on Render, a client-sent first
`X-Forwarded-For` entry passes through unchanged, so keying on it lets the limit be bypassed.
