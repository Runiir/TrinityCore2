"""Read target roles from encounter-owned contracts, never creature-name guesses."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_encounter_damage_targets(primary_entry: int, root: Path = ROOT) -> dict[str, Any]:
    result: dict[str, Any] = {
        "boss_entries": [primary_entry] if primary_entry > 0 else [],
        "add_entries": [], "basis": "native_primary_boss_only",
        "unlisted_target_class": "other_hostile", "sources": [],
    }
    contracts = []
    for path in sorted((root / "experiments/configs/cata_raid_encounters").glob("*/*.json")):
        data = path.read_bytes()
        row = json.loads(data).get("native_damage_targets")
        if not isinstance(row, dict) or row.get("primary_entry") != primary_entry:
            continue
        groups = [row.get("boss_auxiliary_entries"), row.get("add_entries")]
        if not all(isinstance(group, list) and all(
            isinstance(entry, int) and not isinstance(entry, bool) and entry > 0
            for entry in group
        ) for group in groups):
            raise ValueError(f"invalid native damage target roles: {path}")
        if set(groups[0] + [primary_entry]) & set(groups[1]):
            raise ValueError(f"conflicting native damage target roles: {path}")
        contracts.append(row)
        result["sources"].append({
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "basis": row.get("basis"), "source_paths": row.get("source_paths", []),
        })
    if not contracts:
        return result
    roles = {(tuple(sorted(set(row["boss_auxiliary_entries"]))),
              tuple(sorted(set(row["add_entries"])))) for row in contracts}
    if len(roles) != 1:
        result["basis"] = "conflicting_encounter_contracts"
        return result
    bosses, adds = next(iter(roles))
    result.update(boss_entries=sorted({primary_entry, *bosses}),
                  add_entries=list(adds), basis="declared_native_encounter_contract")
    return result
