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

# Optional: the trained DANN-EDL checkpoint instead of the rule-based backend.
# Off by default (torch is a large dependency). Build with --build-arg
# WITH_TORCH=1 and set VICTUS_TRIAGE_MODEL_PATH to enable it — the demo stack
# does exactly that, because the rule-based fallback is so uncertain that it can
# never call a risk trend significant.
# NOTE: the CPU wheel index is essential. Plain `pip install torch` resolves the
# CUDA build and drags in several GB of nvidia-* wheels, which blows up the
# image (and the build). Inference here is CPU-only.
ARG WITH_TORCH=0
RUN if [ "$WITH_TORCH" = "1" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch; \
    fi

# The application package + migrations. Installed with --no-deps so the torch
# `ml` extra in pyproject is never pulled in implicitly.
COPY pyproject.toml README.md* ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY models ./models
COPY docker-entrypoint.sh ./
RUN pip install --no-deps . \
    && chmod +x docker-entrypoint.sh

# Drop root.
RUN useradd --create-home --uid 10001 victus
USER victus

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "victus_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
