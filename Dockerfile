# --- CSS build stage ---
FROM node:22-alpine AS css

WORKDIR /build
RUN npm install --save-dev tailwindcss @tailwindcss/cli
COPY app/templates/ app/templates/
COPY app/static/css/input.css app/static/css/
RUN npx @tailwindcss/cli -i app/static/css/input.css -o app/static/css/style.css --minify

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
COPY --from=css /build/app/static/css/style.css app/static/css/style.css

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

USER landing

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "app:create_app()"]
