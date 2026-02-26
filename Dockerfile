FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    uv sync --frozen --no-dev

COPY src ./src
COPY data ./data
COPY test ./test
COPY SEnSeIv2_config ./SEnSeIv2_config

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src/processor"

CMD ["python", "src/processor/pipeline_orchestrator.py", "--config", "src/processor/pipeline_config.yaml"]
