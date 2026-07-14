# Victus API — FastAPI (async ASGI) on Python 3.12.
#
# Installs the torch-free runtime (requirements-cpanel.txt): the API serves the
# clinically-grounded rule-based per-disease backend, identical in response shape
# to the trained checkpoint. This keeps the image small enough for a modest VPS.
# To run the trained model instead, add `torch` and set VICTUS_TRIAGE_MODEL_PATH.
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime deps first (best layer caching). All wheels are manylinux — no compiler
# needed. curl is only for the container healthcheck.
COPY requirements-cpanel.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install -r requirements-cpanel.txt

# The application package + migrations. Installed with --no-deps so the torch
# `ml` extra in pyproject is never pulled in.
COPY pyproject.toml README.md* ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker-entrypoint.sh ./
RUN pip install --no-deps . \
    && chmod +x docker-entrypoint.sh

# Drop root.
RUN useradd --create-home --uid 10001 victus
USER victus

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "victus_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
