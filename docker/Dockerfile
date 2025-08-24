# syntax=docker/dockerfile:1.7

# Use bookworm (stable) + skip apt entirely
FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# --- deps layer ---
FROM base AS deps
WORKDIR /app
COPY requirements.txt /app/
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

# --- runtime ---
FROM base AS runtime
WORKDIR /app
# copy installed site-packages & scripts from deps
COPY --from=deps /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=deps /usr/local/bin /usr/local/bin

# app code
COPY app app
COPY docker/gunicorn_conf.py docker/gunicorn_conf.py

# data dir
RUN mkdir -p /app/data
ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "-c", "docker/gunicorn_conf.py", "app.main:app"]
