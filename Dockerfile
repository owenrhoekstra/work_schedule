FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /usr/local/bin/

WORKDIR /app

# Layer 1: Python deps (cached unless pyproject/lock changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Layer 2: project source
COPY . .

# Build Tailwind CSS and collect static into STATIC_ROOT
RUN uv run python manage.py tailwind build \
 && uv run python manage.py collectstatic --noinput

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "work_schedule.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]