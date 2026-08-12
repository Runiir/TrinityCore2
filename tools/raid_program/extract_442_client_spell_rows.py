from __future__ import annotations

import argparse
import csv
import hashlib
import json
import io
from pathlib import Path
import re
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
BUILD = "4.4.2.59185"
TABLES = (
    "SpellName",
    "SpellEffect",
    "SpellMisc",
    "SpellAuraOptions",
    "SpellTargetRestrictions",
    "SpellCooldowns",
    "SpellScaling",
    "SpellDuration",
    "SpellRadius",
    "SpellRange",
    "SpellCastTimes",
)
ID_FIELDS = frozenset({"SpellID", "EffectTriggerSpell", "AuraSpellID"})
LOOKUP_TABLES = frozenset({"SpellDuration", "SpellRadius", "SpellRange", "SpellCastTimes"})
REFERENCE_PATTERN = re.compile(
    r"(?:spell(?:_id)?|spell id|spell identity)[\s\"'`:=_-]{0,16}([1-9][0-9]{3,5})",
    re.IGNORECASE,
)


def referenced_spell_ids(paths: list[Path]) -> set[int]:
    ids: set[int] = set()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        ids.update(int(match) for match in REFERENCE_PATTERN.findall(text))
        if path.suffix == ".json":
            collect_json_spell_ids(json.loads(text), ids)
    return ids


def collect_json_spell_ids(value: Any, result: set[int], key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child in value.items():
            collect_json_spell_ids(child, result, str(child_key))
    elif isinstance(value, list):
        for child in value:
            collect_json_spell_ids(child, result, key)
    elif isinstance(value, int) and "spell" in key.lower() and 1000 <= value <= 999999:
        result.add(value)


def download_table(table: str, spell_ids: set[int]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    url = f"https://wago.tools/db2/{table}/csv?build={BUILD}"
    request = Request(url, headers={"User-Agent": "trinity-cata-raid-research/1"})
    digest = hashlib.sha256()
    rows: list[dict[str, str]] = []
    byte_count = 0
    line_count = 0
    with urlopen(request, timeout=120) as response:  # noqa: S310 - frozen HTTPS source
        raw_csv = io.StringIO()
        for raw in response:
            digest.update(raw)
            byte_count += len(raw)
            line_count += 1
            raw_csv.write(raw.decode("utf-8-sig" if line_count == 1 else "utf-8"))
        raw_csv.seek(0)
        reader = csv.DictReader(raw_csv)
        for row in reader:
            relevant = table in LOOKUP_TABLES
            relevant = relevant or any(row.get(field, "").isdigit() and int(row[field]) in spell_ids for field in ID_FIELDS)
            if table == "SpellName" and row.get("ID", "").isdigit():
                relevant = int(row["ID"]) in spell_ids
            if relevant:
                rows.append(dict(row))
    return (
        {
            "table": table,
            "url": url,
            "full_csv_sha256": digest.hexdigest(),
            "full_csv_bytes": byte_count,
            "full_csv_lines": line_count,
            "retained_rows": len(rows),
            "full_csv_retained": False,
        },
        rows,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, default=ROOT / "experiments/configs/cata_raid_encounters")
    parser.add_argument("--dossiers", type=Path, default=ROOT / "docs/bot_raids/strategies")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("output exists; client extracts are immutable")
    sources = sorted(args.contracts.rglob("*.json")) + sorted(args.dossiers.rglob("*.md"))
    spell_ids = referenced_spell_ids(sources)
    if not spell_ids:
        raise SystemExit("no referenced spell IDs found")

    manifests: list[dict[str, Any]] = []
    retained: dict[str, list[dict[str, str]]] = {}
    for table in TABLES:
        manifest, rows = download_table(table, spell_ids)
        manifests.append(manifest)
        retained[table] = rows
    payload = {
        "schema_version": 1,
        "extract_id": "cata_raid_442_59185_client_spell_rows_v1",
        "product": "Cataclysm Classic",
        "patch": "4.4.2",
        "build": 59185,
        "locale": "enUS",
        "source_provider": "wago.tools",
        "source_contract": "full CSV hashes freeze upstream table identity; only encounter-referenced rows are retained",
        "referenced_spell_ids": sorted(spell_ids),
        "table_manifests": manifests,
        "rows": retained,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "spell_ids": len(spell_ids), "tables": len(manifests)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
