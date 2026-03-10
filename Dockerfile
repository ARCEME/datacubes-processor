FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_CACHE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    gdal-bin \
    libgdal-dev \
    proj-bin \
    proj-data \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY data ./data
COPY test ./test
COPY additionals ./additionals
COPY SEnSeIv2_config ./SEnSeIv2_config

RUN mkdir -p /ARCEME-MERGE

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src/processor" \
    PIPELINE_CONFIG="src/processor/pipeline_config.yaml"

CMD ["sh", "-lc", "python src/processor/pipeline_orchestrator.py --config \"$PIPELINE_CONFIG\""]
