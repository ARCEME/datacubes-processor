# Contributing

Thanks for helping with the ARCEME Data Cube Pipeline. This guide describes how to set up the environment, run the pipeline, and propose changes.

## Scope
- Main code lives in [src/processor](src/processor).
- Keep large outputs (Zarr, logs, data cubes) outside the repo in the configured output directory.
- Avoid committing credentials or generated artifacts.

## Requirements
- Python 3.11+
- uv (https://astral.sh/uv/)

## Setup
```bash
cd /home/eouser/datacubes/data-cubes-arceme
uv sync
```

## Configuration
- Default config: [src/processor/pipeline_config.yaml](src/processor/pipeline_config.yaml)
- Quick local run: [src/processor/test_config.yaml](src/processor/test_config.yaml)
- Custom config: pass `--config /path/to/file.yaml`

Create a local [.env](.env) with S3 credentials (do not commit real secrets). See [README.md](README.md) for the full template and endpoint notes.

## Running
```bash
uv run python src/processor/pipeline_orchestrator.py
```

Custom config:
```bash
uv run python src/processor/pipeline_orchestrator.py --config src/processor/test_config.yaml
```

## Tests / checks
There is a simple cloud-mask smoke script:
```bash
uv run python test/senselv_tests.py
```

For a pipeline smoke run, use [src/processor/test_config.yaml](src/processor/test_config.yaml) to keep runtime short.

## Dependencies
Dependencies are managed with uv.

- Add/update: `uv add <package>`
- Sync lockfile: `uv sync`
- Commit changes to [pyproject.toml](pyproject.toml) and [uv.lock](uv.lock) together.

## Submitting changes
- Keep changes focused and describe how to reproduce or validate.
- Update [README.md](README.md) when adding new options or workflow steps.
- If you touch configs or outputs, note the config used and the expected output location.
