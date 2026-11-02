# ---------- base: runtime dependencies only ----------
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------- test: base + pytest + tests (used by the CI "Unit tests" stage) ----------
FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY collectors/ collectors/
COPY tests/ tests/
RUN mkdir -p reports
CMD ["python", "-m", "pytest", "-v", "--junitxml=/app/reports/junit.xml"]

# ---------- runtime: the image that is shipped ----------
FROM base AS runtime
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /app/data \
 && chown app:app /app/data
COPY collectors/ collectors/
USER app
# collected data (data/raw/openalex/*.jsonl) lives here; mount a volume to keep it
VOLUME ["/app/data"]
ENTRYPOINT ["python", "-m", "collectors.openalex_kz"]
CMD ["institutions"]
