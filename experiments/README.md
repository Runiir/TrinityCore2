# Headless Player Bot Experiments

Phase 01 provides a headless experiment runner and universal JSONL frame substrate.

Run the local smoke validation without a live worldserver:

```sh
pixi run python experiments/run_experiment.py experiments/configs/headless_playerbot_smoke_001.json --local
```

Run the DVC-tracked experiment pipeline:

```sh
pixi run dvc repro
pixi run dvc exp run -n smoke-baseline
pixi run dvc exp show
```

The pipeline uses DVC and DVCLive only. ClearML is intentionally not part of
this workflow.

For a live server, set the config adapter to `ra` or `soap` and provide credentials
through the config or environment variables:

- RA: `TRINITY_RA_HOST`, `TRINITY_RA_PORT`, `TRINITY_RA_USER`, `TRINITY_RA_PASSWORD`
- SOAP: `TRINITY_SOAP_URL`, `TRINITY_SOAP_USER`, `TRINITY_SOAP_PASSWORD`

The runner calls existing `playerbot` commands:

- `playerbot spawn <class_spec> [owner <selector>]`
- `playerbot record on [owner <selector>]`
- `playerbot status [owner <selector>]`
- `playerbot record off [owner <selector>]`
- `playerbot remove all [owner <selector>]`

Live clients remain optional. If a live client is attached only for observation,
keep `execution_mode` as `headless_ra_soap` and set `live_client_present` to
`true`. If a human-operated client is the recording source, use
`live_client_recording`; if human and bot actions are mixed in the same episode,
use `mixed_human_bot`. The frame envelope always includes both
`execution_mode` and `live_client_present` so downstream preprocessing can split
headless, observed, and human-recorded data.

## Git and DVC split

Commit reproducible inputs to Git:

- Python source under `experiments/`, `ml/`, `scripts/`, and `tests/`.
- Experiment configs, `params.yaml`, `dvc.yaml`, `dvc.lock`, `pixi.toml`,
  `pixi.lock`, `.gitignore`, and DVC metadata.
- Lightweight documentation and `.gitkeep` files.

Store generated data and artifacts with DVC:

- `dataset/`, including raw frames, processed frames, metadata vocabularies, and
  evaluation outputs.
- `experiments/runs/`, including command logs, run metadata, and summaries.
- `dvclive/` and model artifacts under `models/`.

Do not commit secrets, DVC cache internals, Pixi environments, server logs,
Trinity server data, or build outputs.

To checkpoint current generated files after the split:

```sh
pixi run dvc repro
pixi run dvc status
pixi run dvc push
git add .gitignore pixi.toml pixi.lock dvc.yaml dvc.lock params.yaml .dvc/config
git add experiments ml scripts tests
git commit -m "Add DVC experiment tracking pipeline"
```

`dataset/`, `experiments/runs/`, `dvclive/`, and `models/` remain ignored by
Git; their content is represented by `dvc.yaml` and `dvc.lock`.

## S3-compatible DVC remote

Configure object storage from local environment variables:

```sh
export DVC_S3_URL=s3://bucket/trinity-cata
export DVC_S3_ENDPOINT_URL=https://s3-compatible-endpoint.example
pixi run setup-dvc-s3
```

Credentials should come from the standard AWS environment or local credential
files and should not be committed.
