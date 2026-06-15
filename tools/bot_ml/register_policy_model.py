from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common import FEATURE_SCHEMA_VERSION, LABELS, git_commit, write_json
except ImportError:
    from common import FEATURE_SCHEMA_VERSION, LABELS, git_commit, write_json


def sql_quote(value: object) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SQL to register a trained bot policy model and evaluation.")
    parser.add_argument("--model", type=Path, default=Path("models/bot_policy/policy_model.json"))
    parser.add_argument("--metrics", type=Path, default=Path("evaluations/bot_policy/metrics.json"))
    parser.add_argument("--diagnostics", type=Path, default=Path("evaluations/bot_policy/diagnostics.json"))
    parser.add_argument("--sql-output", "--output-sql", dest="sql_output", type=Path, default=Path("models/bot_policy/register_model.sql"))
    parser.add_argument("--accepted", action="store_true")
    parser.add_argument("--force", action="store_true", help="Allow accepted registration even when metrics.accepted is false.")
    args = parser.parse_args()
    model = json.loads(args.model.read_text(encoding="utf-8"))
    metrics = json.loads(args.metrics.read_text(encoding="utf-8")) if args.metrics.exists() else {}
    diagnostics = json.loads(args.diagnostics.read_text(encoding="utf-8")) if args.diagnostics.exists() else {}
    payload = {
        "model_version": model.get("model_version", ""),
        "model_type": model.get("model_type", ""),
        "backend": model.get("backend", ""),
        "git_commit": model.get("git_commit") or git_commit(),
        "dataset_path": model.get("dataset_path", ""),
        "artifact_path": str(args.model),
        "feature_schema_json": json.dumps({"version": model.get("feature_schema_version", FEATURE_SCHEMA_VERSION), "features": model.get("features", [])}, sort_keys=True),
        "label_schema_json": json.dumps(model.get("labels") or {"labels": LABELS}, sort_keys=True),
        "train_run_ids": json.dumps(model.get("train_run_ids", [])),
        "eval_run_ids": json.dumps(model.get("eval_run_ids", [])),
        "metrics_json": json.dumps(metrics, sort_keys=True),
        "diagnostics_json": json.dumps(diagnostics, sort_keys=True),
        "accepted": 1 if args.accepted and (args.force or metrics.get("accepted") is True) else 0,
    }
    cols = ["model_version", "model_type", "backend", "git_commit", "dataset_path", "artifact_path", "feature_schema_json", "label_schema_json", "train_run_ids", "eval_run_ids", "metrics_json", "diagnostics_json", "accepted"]
    values = ", ".join(str(payload[col]) if col == "accepted" else sql_quote(payload[col]) for col in cols)
    assignments = ", ".join(f"{col}=VALUES({col})" for col in cols[1:])
    sql = (
        "INSERT INTO bot_policy_models (" + ", ".join(cols) + ") VALUES (" + values + ") "
        "ON DUPLICATE KEY UPDATE " + assignments + ";\n"
        "INSERT INTO bot_policy_evaluations (" + ", ".join(cols) + ") VALUES (" + values + ");\n"
    )
    args.sql_output.parent.mkdir(parents=True, exist_ok=True)
    args.sql_output.write_text(sql, encoding="utf-8")
    write_json(args.sql_output.with_suffix(".json"), payload)
    print(json.dumps({"sql_output": str(args.sql_output), "accepted": bool(payload["accepted"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
