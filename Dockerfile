# Production image: read-only API + built frontend. No ingestion, no analysis.
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy MARGINALIS_ENV=production
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
# Frozen results the API serves (committed artifacts, never regenerated here).
COPY reports/holdout_results.json reports/eda_findings.md ./reports/
COPY --from=web /app/frontend/dist ./frontend/dist
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 10000
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn marginalis.api.app:app --host 0.0.0.0 --port ${PORT:-10000}"]
