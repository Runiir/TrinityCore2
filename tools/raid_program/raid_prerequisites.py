"""Per-raid boss prerequisite graphs for seeded raid lockouts.

The files live in ``experiments/configs/raid_prerequisites/<raid>.json`` (schema
``raid_prerequisites_v1``, docs/bot_raids/full_raid_parallel_shards.md). The
in-server seeder reads the same files through
``src/server/game/Bots/BotRaidLockoutDefinitionJson.h``; ``validate`` mirrors
``BotRaidLockout::ValidateDefinition`` so both sides reject the same files.

A shard for boss X needs the transitive closure of X's predecessors dead:
``precompleted_bosses(doc, "maloriak")`` gives the boss keys to pass to
``.botauto lockout seed <cohort> <raid> <difficulty> <keys>``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREQUISITES_DIR = REPO_ROOT / "experiments/configs/raid_prerequisites"
SCHEMA = "raid_prerequisites_v1"
DIFFICULTY_TOKENS = ("10n", "25n", "10h", "25h")
MAX_ENCOUNTER_COUNT = 32
STATE_NOT_STARTED = 0
STATE_DONE = 3
STATE_TO_BE_DECIDED = 5
# The state a native script leaves an untouched boss in (see
# BotRaidLockout::RaidDefinition::InitialBossState).
INITIAL_BOSS_STATES = {"not_started": STATE_NOT_STARTED, "to_be_decided": STATE_TO_BE_DECIDED}
_KEY = re.compile(r"^[a-z0-9_]{1,64}$")
_WHITESPACE_BYTES = {9, 10, 11, 12, 13, 32}


class PrerequisiteError(ValueError):
    """A prerequisite file or a seed request is invalid."""


def raid_path(raid: str) -> Path:
    if not _KEY.match(raid):
        raise PrerequisiteError(f"invalid_raid_key:{raid}")
    return PREREQUISITES_DIR / f"{raid}.json"


def load(raid: str) -> dict[str, Any]:
    """Load and validate one raid file; raises PrerequisiteError when invalid."""
    path = raid_path(raid)
    if not path.is_file():
        raise PrerequisiteError(f"unknown_raid:{raid}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    failure = validate(doc)
    if failure:
        raise PrerequisiteError(f"{path.name}:{failure}")
    if doc["raid"] != raid:
        raise PrerequisiteError(f"{path.name}:raid_key_file_name_mismatch")
    return doc


def load_all() -> dict[str, dict[str, Any]]:
    return {path.stem: load(path.stem) for path in sorted(PREREQUISITES_DIR.glob("*.json"))}


def boss(doc: dict[str, Any], key: str) -> dict[str, Any]:
    for row in doc["bosses"]:
        if row["key"] == key:
            return row
    raise PrerequisiteError(f"unknown_boss:{key}")


def boss_difficulties(doc: dict[str, Any], row: dict[str, Any]) -> list[str]:
    return list(row.get("difficulties") or doc["difficulties"])


def _is_uint(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xFFFFFFFF


def _nullable_uint(row: dict[str, Any], name: str) -> bool:
    return name in row and (row[name] is None or _is_uint(row[name]))


def _has_cycle(doc: dict[str, Any]) -> str:
    edges = {row["key"]: list(row["predecessors"]) for row in doc["bosses"]}
    color: dict[str, int] = {}

    def visit(key: str) -> str:
        mark = color.get(key, 0)
        if mark == 1:
            return key
        if mark == 2:
            return ""
        color[key] = 1
        for predecessor in edges.get(key, ()):
            found = visit(predecessor)
            if found:
                return found
        color[key] = 2
        return ""

    for row in doc["bosses"]:
        found = visit(row["key"])
        if found:
            return found
    return ""


def _shape_failure(doc: Any) -> str:
    """Type checks the C++ parser performs before validation."""
    if not isinstance(doc, dict):
        return "json_parse_error"
    for name in ("schema", "raid", "script_name", "script_header"):
        if not isinstance(doc.get(name), str):
            return "raid_identity_required"
    if not _is_uint(doc.get("map_id")):
        return "raid_identity_required"
    if doc.get("initial_boss_state") not in INITIAL_BOSS_STATES:
        return "invalid_initial_boss_state"
    difficulties = doc.get("difficulties")
    if not isinstance(difficulties, list) or any(item not in DIFFICULTY_TOKENS for item in difficulties):
        return "invalid_difficulties"
    counts = doc.get("encounter_count")
    if not isinstance(counts, dict):
        return "encounter_count_required"
    if any(token not in DIFFICULTY_TOKENS or not _is_uint(value) for token, value in counts.items()):
        return "invalid_encounter_count"
    bosses = doc.get("bosses")
    if not isinstance(bosses, list) or not bosses:
        return "bosses_required"
    for row in bosses:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            return "boss_key_required"
        context = ":" + row["key"]
        if not _is_uint(row.get("boss_index")):
            return "boss_index_required" + context
        for name in ("creature_entry", "credit_entry", "dungeon_encounter_bit", "dungeon_encounter_id"):
            if not _nullable_uint(row, name):
                return f"{name}_required" + context
        by_difficulty = row.get("dungeon_encounter_id_by_difficulty", {})
        if not isinstance(by_difficulty, dict) or any(
            token not in DIFFICULTY_TOKENS or not _is_uint(value) for token, value in by_difficulty.items()
        ):
            return "invalid_dungeon_encounter_id_by_difficulty" + context
        predecessors = row.get("predecessors")
        if not isinstance(predecessors, list) or not all(isinstance(item, str) for item in predecessors):
            return "predecessors_required" + context
        extras = row.get("extra_save_values")
        if not isinstance(extras, dict):
            return "extra_save_values_required" + context
        if not all(_is_uint(value) for value in extras.values()):
            return "invalid_extra_save_value" + context
        if "dead_db_spawn_entries" not in row:
            return "dead_db_spawn_entries_required" + context
        dead = row["dead_db_spawn_entries"]
        if dead is not None and (not isinstance(dead, list) or not all(_is_uint(item) for item in dead)):
            return "invalid_dead_db_spawn_entries" + context
        summoned = row.get("summoned_entries")
        if not isinstance(summoned, list) or not all(_is_uint(item) for item in summoned):
            return "summoned_entries_required" + context
        if "difficulties" in row and (
            not isinstance(row["difficulties"], list)
            or any(item not in DIFFICULTY_TOKENS for item in row["difficulties"])
        ):
            return "invalid_boss_difficulties" + context
    extras = doc.get("save_extras")
    if not isinstance(extras, list):
        return "save_extras_required"
    for extra in extras:
        if (
            not isinstance(extra, dict)
            or not isinstance(extra.get("name"), str)
            or extra.get("encoding") != "raw_uint8"
            or not _is_uint(extra.get("default"))
        ):
            return "invalid_save_extra"
    doors = doc.get("readback_doors", [])
    if not isinstance(doors, list):
        return "invalid_readback_doors"
    for door in doors:
        if (
            not isinstance(door, dict)
            or not _is_uint(door.get("entry"))
            or not isinstance(door.get("open_when_done"), list)
            or not all(isinstance(item, str) for item in door["open_when_done"])
        ):
            return "invalid_readback_doors"
    return ""


def validate(doc: Any) -> str:
    """Return "" when valid, else the first failure (same strings as the C++ reader)."""
    failure = _shape_failure(doc)
    if failure:
        return failure
    if doc["schema"] != SCHEMA:
        return "schema_mismatch"
    if not _KEY.match(doc["raid"]):
        return "invalid_raid_key"
    if not doc["map_id"]:
        return "invalid_map_id"
    if not doc["script_name"]:
        return "script_name_required"
    if not any(char.isalpha() for char in doc["script_header"]):
        return "script_header_required"
    difficulties = doc["difficulties"]
    if not difficulties:
        return "difficulties_required"
    if len(set(difficulties)) != len(difficulties):
        return "invalid_difficulty"
    counts = doc["encounter_count"]
    if len(counts) != len(difficulties):
        return "encounter_count_difficulty_mismatch"
    for token, count in counts.items():
        if token not in difficulties or not count or count > MAX_ENCOUNTER_COUNT:
            return "invalid_encounter_count"

    extra_names: set[str] = set()
    for extra in doc["save_extras"]:
        if not _KEY.match(extra["name"]) or extra["name"] in extra_names:
            return "invalid_save_extra:" + extra["name"]
        extra_names.add(extra["name"])
        if extra["default"] > 255:
            return "invalid_save_extra_default:" + extra["name"]

    keys: set[str] = set()
    for row in doc["bosses"]:
        if not _KEY.match(row["key"]) or row["key"] in keys:
            return "invalid_boss_key:" + row["key"]
        keys.add(row["key"])

    for difficulty in difficulties:
        count = counts[difficulty]
        seen = [0] * count
        for row in doc["bosses"]:
            if difficulty not in boss_difficulties(doc, row):
                continue
            if row["boss_index"] >= count:
                return "boss_index_out_of_range:" + row["key"]
            if seen[row["boss_index"]]:
                return "duplicate_boss_index:" + row["key"]
            seen[row["boss_index"]] += 1
        for index, value in enumerate(seen):
            if not value:
                return f"missing_boss_index:{index}:{difficulty}"

    by_key = {row["key"]: row for row in doc["bosses"]}
    for row in doc["bosses"]:
        key = row["key"]
        for difficulty in row.get("difficulties", []):
            if difficulty not in difficulties:
                return "boss_difficulty_not_in_raid:" + key
        for token, encounter_id in row.get("dungeon_encounter_id_by_difficulty", {}).items():
            if token not in difficulties or not encounter_id:
                return "invalid_dungeon_encounter_id:" + key
        bit = row["dungeon_encounter_bit"]
        if bit is not None and bit >= MAX_ENCOUNTER_COUNT:
            return "invalid_dungeon_encounter_bit:" + key
        direct: set[str] = set()
        for predecessor in row["predecessors"]:
            other = by_key.get(predecessor)
            if other is None or predecessor == key or predecessor in direct:
                return f"invalid_predecessor:{key}:{predecessor}"
            direct.add(predecessor)
            for difficulty in difficulties:
                if difficulty in boss_difficulties(doc, row) and difficulty not in boss_difficulties(doc, other):
                    return f"predecessor_unavailable:{key}:{predecessor}"
        for name, value in row["extra_save_values"].items():
            if name not in extra_names:
                return f"unknown_extra_save_value:{key}:{name}"
            if value > 255 or value in _WHITESPACE_BYTES:
                return f"extra_save_value_not_round_trip:{key}:{name}"
        if any(not entry for entry in row["dead_db_spawn_entries"] or []):
            return "invalid_dead_db_spawn_entry:" + key
        if any(not entry for entry in row["summoned_entries"]):
            return "invalid_summoned_entry:" + key
    dead_entries = {entry for row in doc["bosses"] for entry in row["dead_db_spawn_entries"] or []}
    for row in doc["bosses"]:
        for entry in row["summoned_entries"]:
            if entry in dead_entries:
                return f"entry_both_dead_spawn_and_summoned:{entry}"
    cycle = _has_cycle(doc)
    if cycle:
        return "predecessor_cycle:" + cycle
    for door in doc.get("readback_doors", []):
        if not door["entry"] or not door["open_when_done"]:
            return "invalid_readback_door"
        for key in door["open_when_done"]:
            if key not in keys:
                return "invalid_readback_door_boss:" + key
    return ""


def predecessor_closure(doc: dict[str, Any], key: str) -> list[str]:
    """Transitive predecessors of ``key`` (excluding it), ordered by boss index."""
    boss(doc, key)
    by_key = {row["key"]: row for row in doc["bosses"]}
    closure: set[str] = set()
    pending = list(by_key[key]["predecessors"])
    while pending:
        current = pending.pop()
        if current == key or current in closure:
            continue
        closure.add(current)
        pending.extend(by_key[current]["predecessors"])
    return sorted(closure, key=lambda name: by_key[name]["boss_index"])


def precompleted_bosses(doc: dict[str, Any], target: str, difficulty: str) -> list[str]:
    """Bosses a shard for ``target`` must have dead on ``difficulty``."""
    row = boss(doc, target)
    if difficulty not in doc["difficulties"]:
        raise PrerequisiteError(f"difficulty_not_supported:{difficulty}")
    if difficulty not in boss_difficulties(doc, row):
        raise PrerequisiteError(f"boss_not_available_on_difficulty:{target}")
    return predecessor_closure(doc, target)


def seed_argument(bosses_done: list[str]) -> str:
    """The ``<boss-key,...|none>`` token of ``.botauto lockout seed``."""
    return ",".join(bosses_done) if bosses_done else "none"


def seed_plan(doc: dict[str, Any], difficulty: str, bosses_done: Iterable[str]) -> dict[str, Any]:
    """Mirror of BotRaidLockout::BuildSeedPlan; raises PrerequisiteError on refusal."""
    if difficulty not in doc["encounter_count"]:
        raise PrerequisiteError(f"difficulty_not_supported:{difficulty}")
    count = doc["encounter_count"][difficulty]
    done: set[str] = set()
    for key in bosses_done:
        row = boss(doc, key)
        if difficulty not in boss_difficulties(doc, row):
            raise PrerequisiteError(f"boss_not_available_on_difficulty:{key}")
        if key in done:
            raise PrerequisiteError(f"duplicate_boss:{key}")
        done.add(key)
    ordered = sorted((boss(doc, key) for key in done), key=lambda row: row["boss_index"])
    states = [INITIAL_BOSS_STATES[doc["initial_boss_state"]]] * count
    extras = {extra["name"]: extra["default"] for extra in doc["save_extras"]}
    owners: dict[str, str] = {}
    mask = 0
    dead: list[tuple[str, int]] = []
    summoned: list[tuple[str, int]] = []
    for row in ordered:
        for predecessor in row["predecessors"]:
            if predecessor not in done:
                raise PrerequisiteError(f"bosses_done_not_predecessor_closed:{row['key']}:{predecessor}")
        if row["dungeon_encounter_bit"] is None:
            raise PrerequisiteError(f"boss_encounter_bit_unknown:{row['key']}")
        if row["dead_db_spawn_entries"] is None:
            raise PrerequisiteError(f"boss_dead_spawns_unverified:{row['key']}")
        states[row["boss_index"]] = STATE_DONE
        mask |= 1 << row["dungeon_encounter_bit"]
        for name, value in row["extra_save_values"].items():
            if name in owners and extras[name] != value:
                raise PrerequisiteError(f"extra_save_value_conflict:{name}")
            extras[name] = value
            owners[name] = row["key"]
        dead.extend((row["key"], entry) for entry in row["dead_db_spawn_entries"])
        summoned.extend((row["key"], entry) for entry in row["summoned_entries"])
    extra_values = [(extra["name"], extras[extra["name"]]) for extra in doc["save_extras"]]
    return {
        "bosses_done": [row["key"] for row in ordered],
        "boss_indices_done": [row["boss_index"] for row in ordered],
        "boss_states": states,
        "completed_encounters_mask": mask,
        "extra_values": extra_values,
        "save_data": build_save_data(doc["script_header"], states, [value for _, value in extra_values]),
        "dead_db_spawns": dead,
        "summoned_entries": summoned,
    }


def build_save_data(header: str, states: list[int], raw_extras: list[int]) -> bytes:
    """InstanceScript::GetSaveData bytes: header chars and spaces, states and spaces, raw bytes."""
    data = bytearray()
    for char in header:
        if char.isalpha():
            data += f"{char} ".encode("ascii")
    for state in states:
        data += f"{state} ".encode("ascii")
    data += bytes(raw_extras)
    return bytes(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate every prerequisite file")
    closure = sub.add_parser("closure", help="print the precompleted bosses for a shard")
    closure.add_argument("raid")
    closure.add_argument("boss")
    closure.add_argument("--difficulty", default="10n")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            docs = load_all()
            print(json.dumps({"ok": True, "raids": sorted(docs)}))
            return 0
        doc = load(args.raid)
        done = precompleted_bosses(doc, args.boss, args.difficulty)
        plan = seed_plan(doc, args.difficulty, done)
        print(json.dumps({
            "ok": True,
            "raid": args.raid,
            "boss": args.boss,
            "difficulty": args.difficulty,
            "precompleted": done,
            "seed_argument": seed_argument(done),
            "boss_states": plan["boss_states"],
            "completed_encounters_mask": plan["completed_encounters_mask"],
        }))
        return 0
    except PrerequisiteError as error:
        print(json.dumps({"ok": False, "failure_reason": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
