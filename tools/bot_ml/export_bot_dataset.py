from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

try:
    from .common import EXPORT_TABLES, table_path, write_json, write_jsonl, write_parquet_if_available
except ImportError:
    from common import EXPORT_TABLES, table_path, write_json, write_jsonl, write_parquet_if_available


def connect(database_url: str):
    try:
        import pymysql
    except Exception as exc:
        raise SystemExit("pymysql is required for --database-url exports; install with pixi or export JSONL another way") from exc
    parsed = urlparse(database_url)
    return pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def table_columns(conn, table: str) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM `{table}`")
        return {row["Field"] for row in cursor.fetchall()}


def export_table(conn, table: str, run_ids: list[int] | None) -> list[dict]:
    where = ""
    params: list[object] = []
    if run_ids:
        columns = table_columns(conn, table)
        filter_column = "run_id" if "run_id" in columns else "id" if table == "experiment_bot_runs" else ""
        if filter_column:
            where = f" WHERE `{filter_column}` IN (" + ",".join(["%s"] * len(run_ids)) + ")"
            params = list(run_ids)
    with conn.cursor() as cursor:
        cursor.execute(f"SELECT * FROM `{table}`{where}", params)
        return list(cursor.fetchall())


def canonical_dataset_events(rows_by_table: dict[str, list[dict]]) -> list[dict]:
    events: list[dict] = []
    for table, rows in rows_by_table.items():
        for row in rows:
            payload = row.get("canonical_event_json")
            if not payload:
                continue
            try:
                event = json.loads(payload) if isinstance(payload, str) else payload
            except Exception:
                continue
            if isinstance(event, dict):
                event.setdefault("source_table", table)
                event.setdefault("source_id", row.get("id"))
                events.append(event)
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Export autonomous bot DB tables to JSONL and optional Parquet.")
    parser.add_argument("--database-url", help="mysql://user:pass@host:3306/characters")
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/bot_ml/raw"))
    parser.add_argument("--run-id", type=int, action="append", dest="run_ids")
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("--database-url is required for DB export")

    conn = connect(args.database_url)
    manifest = {"tables": {}, "run_ids": args.run_ids or []}
    rows_by_table: dict[str, list[dict]] = {}
    try:
        for table in EXPORT_TABLES:
            rows = export_table(conn, table, args.run_ids)
            rows_by_table[table] = rows
            jsonl = table_path(args.output_dir, table)
            count = write_jsonl(jsonl, rows)
            parquet = args.output_dir / f"{table}.parquet"
            manifest["tables"][table] = {
                "jsonl": str(jsonl),
                "parquet": str(parquet) if write_parquet_if_available(parquet, rows) else None,
                "rows": count,
            }
    finally:
        conn.close()
    canonical_rows = canonical_dataset_events(rows_by_table)
    canonical_jsonl = args.output_dir / "bot_dataset_events.jsonl"
    canonical_count = write_jsonl(canonical_jsonl, canonical_rows)
    canonical_parquet = args.output_dir / "bot_dataset_events.parquet"
    manifest["canonical_dataset"] = {
        "jsonl": str(canonical_jsonl),
        "parquet": str(canonical_parquet) if write_parquet_if_available(canonical_parquet, canonical_rows) else None,
        "rows": canonical_count,
        "schema_version": "bot_dataset_event_v1",
    }
    write_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
