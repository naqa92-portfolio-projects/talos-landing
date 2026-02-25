# --- Python dependencies ---
FROM python:3.14-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Runtime ---
FROM python:3.14-slim

WORKDIR /app

RUN groupadd --gid 10001 landing && \
    useradd --uid 10001 --gid landing --no-create-home --shell /usr/sbin/nologin landing

COPY --from=builder /app/.venv .venv/
COPY app/ app/
COPY config/ config/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

USER landing

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--no-control-socket", "app:create_app()"]
