# ---------------------------------------------------------------------------
# Stage 1: Build the Vue frontend.
#
# Outputs static/vue/ (relative to the repo root) via vite.config.ts's
# outDir. That directory is gitignored, so every deployable image needs
# to build it fresh. Multi-stage keeps node_modules out of the runtime
# image.
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@12.18.0 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

# vite.config.ts sets outDir to "../static/vue" — one level up from
# WORKDIR /app, so output lands at /static/vue. Move it under /app so
# the runtime stage's COPY target is stable and predictable.
RUN mkdir -p /app/static && mv /static/vue /app/static/vue

# ---------------------------------------------------------------------------
# Stage 2: Runtime image.
# ---------------------------------------------------------------------------
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Vue build output. Copied after COPY . . so a stale local static/vue/
# (if present in the build context) is overwritten with the fresh build.
COPY --from=frontend /app/static/vue ./static/vue

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "work_schedule.wsgi:application", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "3", \
    "--timeout", "60", \
    "--access-logfile", "-", \
    "--error-logfile", "-"]
