"""Small, read-only projections of an existing encounter ledger for research resumes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def project(ledger: dict, key: str | None = None) -> dict:
    result = {name: ledger.get(name) for name in
              ("raid", "boss_slug", "fidelity_state", "fidelity_target",
               "repository_revision_audited", "contract_path")}
    if key is None:
        coverage = ledger.get("research_completion")
        result["coverage_present"] = coverage is not None
        result["next_questions"] = [
            {name: row.get(name) for name in ("key", "status", "next")}
            for row in coverage or []
        ]
        if coverage is None:
            result["unresolved"] = ledger.get("unresolved", [])
            result["warning"] = "No completion inventory; an empty unresolved list does not prove completeness."
        return result
    result["claims"] = {
        section: [row for row in ledger.get(section, []) if row.get("key") == key]
        for section in ("values", "timers", "lifecycle", "unresolved", "research_completion")
    }
    result["claims"] = {section: rows for section, rows in result["claims"].items() if rows}
    if not result["claims"]:
        raise ValueError(f"Unknown claim key: {key}")
    source_ids = {source for rows in result["claims"].values() for row in rows
                  for source in row.get("source_refs", [])}
    source_ids.update(row.get("client_59185_reference", {}).get("source_ref")
                      for rows in result["claims"].values() for row in rows)
    result["sources"] = [row for row in ledger.get("source_catalog", []) if row["id"] in source_ids]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--key", help="Show the exact claim and its source records")
    args = parser.parse_args()
    try:
        result = project(json.loads(args.ledger.read_text()), args.key)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
