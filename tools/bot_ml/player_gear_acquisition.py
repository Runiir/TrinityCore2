"""Bind heuristic equipment candidates to retained player acquisition records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_ITEM_SOURCE_INDEX = Path("dataset/world_planner/item_source_index.jsonl")
SOURCE_TYPES = {"vendor", "creature_loot", "gameobject_loot", "quest_reward", "quest_choice"}


def bind_player_acquisition(
    items: list[dict[str, Any]], path: Path = DEFAULT_ITEM_SOURCE_INDEX,
) -> list[dict[str, Any]]:
    """Missing acquisition is excluded, including client-only test items.

    Reference-loot placeholder rows do not establish acquisition of their item
    field. Indirect acquisition requires a resolved source, not an assumption.
    The exact WoWSims preset path is separate from this heuristic generator.
    """
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    wanted = {int(item["ID"]) for item in items}
    sources: dict[int, list[dict[str, Any]]] = {}
    for line in payload.splitlines():
        row = json.loads(line)
        item_id = int(row["item_id"])
        if item_id not in wanted or item_id <= 0:
            continue
        admitted = [source for source in row.get("sources", [])
                    if source.get("source_type") in SOURCE_TYPES
                    and int(source.get("item_id") or 0) == item_id
                    and int(source.get("source_entry") or 0) > 0
                    and int(source.get("reference") or 0) == 0]
        if admitted:
            sources[item_id] = admitted
    return [dict(item, player_acquisition={
        "index_path": str(path), "index_sha256": digest,
        "sources": sources.get(int(item["ID"]), []),
    }) for item in items]
