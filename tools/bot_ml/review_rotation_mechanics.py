"""Translate WoWSims APLs and Trinity bot evidence into a reviewable IR.

This module is deliberately observational.  It does not execute an APL, tune a
profile, or decide that two predicates are semantically equivalent.  Instead it
normalizes action identities, condition families, runtime decision edges, and
route-mechanic obligations so a reviewer can find concrete gaps without
conflating selection, movement, submission, and landed outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA = "trinity_wowsims_rotation_mechanics_review_v1"

_TRINITY_WEIGHT_COLUMNS = (
    "damage_weight",
    "healing_weight",
    "threat_weight",
    "mitigation_weight",
    "survival_weight",
    "movement_weight",
    "progression_weight",
    "profession_weight",
)

_TRINITY_GATE_COLUMNS = (
    "min_enemies",
    "max_enemies",
    "min_target_health_pct",
    "max_target_health_pct",
    "min_self_health_pct",
    "max_self_health_pct",
    "required_self_aura",
    "forbidden_self_aura",
    "required_target_aura",
    "forbidden_target_aura",
    "requires_interruptible_target",
    "requires_target_not_victim",
    "requires_target_victim",
    "requires_melee_range",
    "requires_ranged_range",
    "min_range",
    "max_range",
    "requires_instant_cast",
    "max_cast_time_ms",
    "maintain_aura_id",
    "refresh_aura_below_ms",
    "min_injured_players",
    "max_injured_players",
    "injured_health_pct",
    "min_mana_pct",
    "max_mana_pct",
    "min_primary_power_pct",
    "max_primary_power_pct",
    "min_attackers",
    "max_attackers",
    "requires_stationary",
    "requires_moving",
    "required_owned_target_aura",
    "forbidden_owned_target_aura",
    "required_self_aura_stacks",
    "max_self_aura_stacks",
    "min_self_aura_remaining_ms",
    "max_self_aura_remaining_ms",
    "min_combo_points",
    "max_combo_points",
    "min_ready_runes",
    "required_shapeshift_form",
    "requires_pet",
    "forbids_pet",
    "required_main_hand_enchant",
    "required_off_hand_enchant",
    "cooldown_group",
    "target_creature_type_mask",
    "requires_ground_target",
)

_STRUCTURAL_EXPRESSION_KEYS = {
    "action",
    "actions",
    "condition",
    "interruptIf",
    "and",
    "or",
    "not",
    "val",
    "vals",
    "cmp",
    "lhs",
    "rhs",
    "math",
    "min",
    "max",
    "const",
    "op",
    "auraId",
    "spellId",
    "itemId",
    "otherId",
    "tag",
    "threshold",
    "runeType",
    "runeSlot",
    "statType",
    "statType1",
    "statType2",
    "statType3",
    "targetIndex",
    "maxDots",
    "eclipsePhase",
    "totemType",
    "sequenceName",
    "type",
    "index",
    "owner",
}

_WOWSIMS_ACTION_KEYS = {
    "castSpell",
    "channelSpell",
    "wait",
    "strictSequence",
    "sequence",
    "resetSequence",
    "multidot",
    "itemSwap",
    "move",
    "moveDuration",
    "autocastOtherCooldowns",
    "castAllStatBuffCooldowns",
    "activateAllStatBuffProcAuras",
    "activateAura",
    "activateAuraWithStacks",
    "triggerIcd",
    "cancelAura",
    "catOptimalRotationAction",
}

_WOWSIMS_SPELL_ACTION_KEYS = {"castSpell", "channelSpell", "multidot"}

_EXACT_CONDITION_FAMILIES = {
    "channelClipDelay": "execution_latency",
    "currentFocus": "primary_power",
    "druidCurrentEclipsePhase": "spec_resource_state",
    "inputDelay": "execution_latency",
    "sequenceIsComplete": "sequence_state",
    "shamanCanSnapshotStrongerFireElemental": "pet_totem_state",
    "shamanFireElementalDuration": "pet_totem_state",
    "sourceUnit": "target_scope",
    "spellCanCast": "action_availability",
    "spellIsKnown": "action_availability",
    "targetUnit": "target_scope",
    "totemRemainingTime": "pet_totem_state",
}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON from {path}: {exc}") from exc


def _json_scalar(value: Any) -> Any:
    """Convert DB-driver scalar wrappers without weakening their value."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return int(numeric) if numeric.is_integer() else numeric


def _camelize_key(key: str) -> str:
    parts = key.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _camelize_json_keys(value: Any) -> Any:
    """Normalize native protojson field names to the UI APL vocabulary."""
    if isinstance(value, list):
        return [_camelize_json_keys(item) for item in value]
    if isinstance(value, dict):
        return {
            _camelize_key(str(key)): _camelize_json_keys(child)
            for key, child in value.items()
        }
    return value


def _first_int(mapping: Any, *keys: str) -> int | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _get(mapping: Any, *keys: str, default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


def _identity_from_id(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"kind": "unknown", "id": None, "tag": None}
    spell_id = _first_int(value, "spellId", "spell_id")
    if spell_id is not None:
        return {"kind": "spell", "id": spell_id, "tag": value.get("tag")}
    item_id = _first_int(value, "itemId", "item_id")
    if item_id is not None:
        return {"kind": "item", "id": item_id, "tag": value.get("tag")}
    other = value.get("otherId", value.get("other_id"))
    if other is not None:
        return {"kind": "other", "id": str(other), "tag": value.get("tag")}
    return {"kind": "unknown", "id": None, "tag": value.get("tag")}


def _condition_leaf_names(value: Any) -> set[str]:
    leaves: set[str] = set()
    if isinstance(value, list):
        for item in value:
            leaves.update(_condition_leaf_names(item))
        return leaves
    if not isinstance(value, dict):
        return leaves
    for key, child in value.items():
        if key not in _STRUCTURAL_EXPRESSION_KEYS:
            leaves.add(key)
        leaves.update(_condition_leaf_names(child))
    return leaves


def _condition_family(name: str) -> str:
    if name in _EXACT_CONDITION_FAMILIES:
        return _EXACT_CONDITION_FAMILIES[name]
    lowered = name.lower()
    if "rune" in lowered:
        return "runes"
    if "combo" in lowered:
        return "combo_points"
    if "power" in lowered or "mana" in lowered or "energy" in lowered or "rage" in lowered:
        return "primary_power"
    if "dot" in lowered:
        return "owned_target_aura"
    if "aura" in lowered or "buff" in lowered or "debuff" in lowered:
        return "aura_state"
    if "execute" in lowered or "health" in lowered:
        return "target_health"
    if "target" in lowered and ("count" in lowered or "number" in lowered):
        return "enemy_count"
    if "cooldown" in lowered or "ready" in lowered or "gcd" in lowered:
        return "cooldown"
    if "trinket" in lowered or "proc" in lowered or "icd" in lowered:
        return "proc_state"
    if "pet" in lowered or "totem" in lowered:
        return "pet_totem_state"
    if "time" in lowered:
        return "encounter_time"
    if "moving" in lowered or "distance" in lowered or "range" in lowered:
        return "movement_range"
    return "unmapped_expression"


def _wowsims_action_rows(
    node: Any,
    *,
    phase: str,
    priority_index: int,
    path: str,
    inherited_condition: Any = None,
    hidden: bool = False,
    schedule: Any = None,
) -> Iterator[dict[str, Any]]:
    if not isinstance(node, dict):
        return

    action = node.get("action") if isinstance(node.get("action"), dict) else node
    condition = action.get("condition", inherited_condition)
    is_hidden = bool(node.get("hide", hidden))

    for spell_action_key in sorted(_WOWSIMS_SPELL_ACTION_KEYS):
        spell_action = action.get(spell_action_key)
        if not isinstance(spell_action, dict):
            continue
        control_predicates: dict[str, Any] = {}
        if condition is not None:
            control_predicates["condition"] = condition
        if spell_action_key == "channelSpell" and spell_action.get("interruptIf") is not None:
            control_predicates["interruptIf"] = spell_action["interruptIf"]
        condition_record: Any = control_predicates or None
        identity = _identity_from_id(
            spell_action.get("spellId", spell_action.get("spell_id"))
        )
        leaves = sorted(_condition_leaf_names(condition_record))
        yield {
            "source": "wowsims",
            "phase": phase,
            "priority_index": priority_index,
            "path": f"{path}.{spell_action_key}",
            "action_kind": spell_action_key,
            "identity": identity,
            "action_payload": spell_action,
            "action_payload_sha256": canonical_sha256(spell_action),
            "hidden": is_hidden,
            "schedule": schedule,
            "schedule_sha256": canonical_sha256(schedule) if schedule is not None else None,
            "condition_leaves": leaves,
            "condition_families": sorted({_condition_family(item) for item in leaves}),
            "condition_expression": condition_record,
            "condition_sha256": (
                canonical_sha256(condition_record) if condition_record is not None else None
            ),
        }

    for sequence_key in ("strictSequence", "sequence"):
        sequence = action.get(sequence_key)
        if not isinstance(sequence, dict):
            continue
        for index, child in enumerate(sequence.get("actions") or []):
            yield from _wowsims_action_rows(
                child,
                phase=phase,
                priority_index=priority_index,
                path=f"{path}.{sequence_key}.actions[{index}]",
                inherited_condition=condition,
                hidden=is_hidden,
                schedule=schedule,
            )

    for action_key in sorted(
        _WOWSIMS_ACTION_KEYS
        - _WOWSIMS_SPELL_ACTION_KEYS
        - {"strictSequence", "sequence"}
    ):
        if action_key not in action:
            continue
        leaves = sorted(_condition_leaf_names(condition))
        yield {
            "source": "wowsims",
            "phase": phase,
            "priority_index": priority_index,
            "path": f"{path}.{action_key}",
            "action_kind": action_key,
            "identity": {"kind": "structural", "id": action_key, "tag": None},
            "action_payload": action[action_key],
            "action_payload_sha256": canonical_sha256(action[action_key]),
            "hidden": is_hidden,
            "schedule": schedule,
            "schedule_sha256": canonical_sha256(schedule) if schedule is not None else None,
            "condition_leaves": leaves,
            "condition_families": sorted({_condition_family(item) for item in leaves}),
            "condition_expression": condition,
            "condition_sha256": canonical_sha256(condition) if condition is not None else None,
        }


def find_wowsims_apl(document: Any, player_index: int = 0) -> dict[str, Any]:
    """Find an APL in an exported APL or RaidSimRequest JSON document."""
    normalized_document = _camelize_json_keys(document)
    if isinstance(normalized_document, dict) and (
        isinstance(normalized_document.get("priorityList"), list)
        or isinstance(normalized_document.get("prepullActions"), list)
    ):
        return normalized_document

    candidates: list[Any] = []
    if isinstance(normalized_document, dict):
        candidates.extend(
            normalized_document.get(key)
            for key in ("rotation", "apl", "rotationApl")
        )
        raid = normalized_document.get("raid")
        if isinstance(raid, dict):
            players: list[Any] = []
            for party in raid.get("parties") or []:
                if isinstance(party, dict):
                    players.extend(party.get("players") or [])
            if 0 <= player_index < len(players) and isinstance(players[player_index], dict):
                player = players[player_index]
                candidates.extend(
                    player.get(key) for key in ("rotation", "apl", "rotationApl")
                )

    for candidate in candidates:
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                continue
        if isinstance(candidate, dict) and (
            isinstance(candidate.get("priorityList"), list)
            or isinstance(candidate.get("prepullActions"), list)
        ):
            return candidate
    raise ValueError("no WoWSims APL found in document")


def normalize_wowsims_apl(apl: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(apl.get("prepullActions") or []):
        rows.extend(
            _wowsims_action_rows(
                entry,
                phase="prepull",
                priority_index=index,
                path=f"prepullActions[{index}]",
                schedule=entry.get("doAtValue") if isinstance(entry, dict) else None,
            )
        )
    for index, entry in enumerate(apl.get("priorityList") or []):
        rows.extend(
            _wowsims_action_rows(
                entry,
                phase="combat",
                priority_index=index,
                path=f"priorityList[{index}]",
            )
        )

    return {
        "schema": "rotation_review_wowsims_apl_v1",
        "apl_sha256": canonical_sha256(apl),
        "action_count": len(rows),
        "actions": rows,
        "condition_leaf_counts": dict(
            sorted(Counter(leaf for row in rows for leaf in row["condition_leaves"]).items())
        ),
        "unmapped_condition_leaves": sorted(
            {
                leaf
                for row in rows
                for leaf in row["condition_leaves"]
                if _condition_family(leaf) == "unmapped_expression"
            }
        ),
    }


_WOWSIMS_LOG_ACTION_ID = re.compile(
    r"\{(?P<kind>SpellID|ItemID|OtherID): (?P<id>[^,}]+)(?:, Tag: (?P<tag>-?\d+))?\}"
)
_WOWSIMS_LOG_TIMESTAMP = re.compile(r"^\[(?P<timestamp>-?\d+(?:\.\d+)?)\]")
_WOWSIMS_LOG_ENTITY = re.compile(r"\[(?P<label>Target \d+|[^\]]+\(#\d+\)(?: - [^\]]+)?)\]")


def _identity_from_log(line: str) -> dict[str, Any] | None:
    match = _WOWSIMS_LOG_ACTION_ID.search(line)
    if not match:
        return None
    raw_id = match.group("id").strip()
    kind = {
        "SpellID": "spell",
        "ItemID": "item",
        "OtherID": "other",
    }[match.group("kind")]
    identity_id: int | str = int(raw_id) if raw_id.lstrip("-").isdigit() else raw_id
    return {
        "kind": kind,
        "id": identity_id,
        "tag": int(match.group("tag") or 0),
    }


def _identity_key(identity: dict[str, Any] | None) -> str:
    if not identity:
        return "unknown"
    return f"{identity.get('kind')}:{identity.get('id')}:{identity.get('tag') or 0}"


def _classify_wowsims_log(line: str) -> str:
    if "Completed cast " in line:
        return "cast_completed"
    if " failed to cast:" in line:
        return "cast_failed"
    if " Casting " in line or "] Casting " in line:
        return "cast_started"
    if "Major cooldown used:" in line:
        return "major_cooldown_used"
    if "Aura gained:" in line:
        return "aura_gained"
    if "Aura faded:" in line:
        return "aura_faded"
    if "Aura refreshed:" in line:
        return "aura_refreshed"
    if " stacks: " in line and " --> " in line:
        return "aura_stacks_changed"
    if re.search(
        r"\b(Gained|Spent) \d+(?:\.\d+)? (?:health|mana|energy|focus|rage|combo points|runic power|blood rune|frost rune|unholy rune|death rune|solar energy|lunar energy) from ",
        line,
    ):
        return "resource_changed"
    if re.search(r" for \d+(?:\.\d+)? (?:damage|healing|shielding)", line):
        return "landed_effect"
    if "Moving to " in line or "Movement speed changed" in line:
        return "movement"
    if "Pausing rotation for " in line or "Extending GCD for " in line:
        return "rotation_wait"
    if "No available actions!" in line:
        return "no_available_actions"
    if "Item Swap" in line:
        return "item_swap"
    if "Pet summoned" in line or "Pet dismissed" in line:
        return "pet_lifecycle"
    return "other"


def _normalize_wowsims_log(log_text: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()
    identity_counts: Counter[str] = Counter()
    timestamps_by_identity_kind: dict[tuple[str, str], list[float]] = {}
    for line_index, raw in enumerate(log_text.splitlines()):
        if not raw.strip():
            continue
        time_match = _WOWSIMS_LOG_TIMESTAMP.match(raw)
        timestamp = float(time_match.group("timestamp")) if time_match else None
        identity = _identity_from_log(raw)
        kind = _classify_wowsims_log(raw)
        entities = [match.group("label") for match in _WOWSIMS_LOG_ENTITY.finditer(raw)]
        event: dict[str, Any] = {
            "line_index": line_index,
            "timestamp_seconds": timestamp,
            "kind": kind,
            "identity": identity,
            "source_entity": entities[0] if entities else None,
            "target_entity": entities[1] if len(entities) > 1 else None,
            "raw": raw,
        }
        resource_match = re.search(
            r"\b(?P<direction>Gained|Spent) (?P<amount>\d+(?:\.\d+)?) "
            r"(?P<resource>health|mana|energy|focus|rage|combo points|runic power|blood rune|frost rune|unholy rune|death rune|solar energy|lunar energy) "
            r"from .*? \((?P<before>\d+(?:\.\d+)?) --> (?P<after>\d+(?:\.\d+)?)\)",
            raw,
        )
        if resource_match:
            event["resource"] = {
                "name": resource_match.group("resource"),
                "direction": resource_match.group("direction").lower(),
                "amount": float(resource_match.group("amount")),
                "before": float(resource_match.group("before")),
                "after": float(resource_match.group("after")),
            }
        effect_match = re.search(
            r" for (?P<amount>\d+(?:\.\d+)?) (?P<effect>damage|healing|shielding)",
            raw,
        )
        if effect_match:
            event["landed_effect"] = {
                "kind": effect_match.group("effect"),
                "amount": float(effect_match.group("amount")),
            }
        kind_counts[kind] += 1
        identity_key = _identity_key(identity)
        if identity:
            identity_counts[identity_key] += 1
            if timestamp is not None and kind in {
                "cast_started",
                "cast_completed",
                "major_cooldown_used",
                "landed_effect",
            }:
                timestamps_by_identity_kind.setdefault((identity_key, kind), []).append(
                    timestamp
                )
        events.append(event)

    action_timeline = []
    for (identity_key, event_kind), timestamps in sorted(
        timestamps_by_identity_kind.items()
    ):
        intervals = [
            timestamps[index] - timestamps[index - 1]
            for index in range(1, len(timestamps))
        ]
        action_timeline.append(
            {
                "identity_key": identity_key,
                "event_kind": event_kind,
                "event_count": len(timestamps),
                "first_at_seconds": timestamps[0],
                "last_at_seconds": timestamps[-1],
                "mean_interval_seconds": sum(intervals) / len(intervals) if intervals else None,
                "max_interval_seconds": max(intervals) if intervals else None,
                "timestamps_seconds": timestamps,
            }
        )
    return {
        "line_count": len(events),
        "event_kind_counts": dict(sorted(kind_counts.items())),
        "event_identity_counts": dict(sorted(identity_counts.items())),
        "events": events,
        "action_timeline": action_timeline,
    }


def find_wowsims_result(document: Any) -> dict[str, Any]:
    if isinstance(document, dict) and (
        isinstance(_get(document, "raidMetrics", "raid_metrics"), dict)
        or "logs" in document
    ):
        return document
    if isinstance(document, dict):
        for key in ("result", "finalRaidResult", "final_raid_result"):
            candidate = document.get(key)
            if isinstance(candidate, dict):
                try:
                    return find_wowsims_result(candidate)
                except ValueError:
                    pass
    raise ValueError("no WoWSims RaidSimResult found in document")


def _normalize_action_metric(
    action: dict[str, Any], *, iterations: int, source: dict[str, Any]
) -> dict[str, Any]:
    identity = _identity_from_id(action.get("id"))
    targets: list[dict[str, Any]] = []
    sums: Counter[str] = Counter()
    numeric_keys = (
        "casts",
        "hits",
        "crits",
        "ticks",
        "critTicks",
        "misses",
        "dodges",
        "parries",
        "blocks",
        "glances",
        "damage",
        "healing",
        "shielding",
        "castTimeMs",
    )
    for target in _get(action, "targets", default=[]) or []:
        if not isinstance(target, dict):
            continue
        row = {"unit_index": _get(target, "unitIndex", "unit_index")}
        for key in numeric_keys:
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
            value = _get(target, key, snake, default=0) or 0
            row[snake] = value
            sums[snake] += value
        targets.append(row)
    per_iteration = {
        key: value / iterations for key, value in sorted(sums.items())
    }
    return {
        "identity": identity,
        "source": source,
        "is_melee": bool(_get(action, "isMelee", "is_melee", default=False)),
        "is_passive": bool(_get(action, "isPassive", "is_passive", default=False)),
        "spell_school": _get(action, "spellSchool", "spell_school"),
        "target_metrics": targets,
        "target_metric_sums": dict(sorted(sums.items())),
        "per_iteration_target_metric_sums": per_iteration,
    }


def normalize_wowsims_result(document: Any, player_index: int = 0) -> dict[str, Any]:
    result = find_wowsims_result(document)
    iterations = int(_get(result, "iterationsDone", "iterations_done", default=0) or 0)
    if iterations <= 0:
        iterations = 1
    raid_metrics = _get(result, "raidMetrics", "raid_metrics", default={}) or {}
    players: list[dict[str, Any]] = []
    for party in _get(raid_metrics, "parties", default=[]) or []:
        if isinstance(party, dict):
            players.extend(_get(party, "players", default=[]) or [])
    if not 0 <= player_index < len(players):
        raise ValueError(
            f"WoWSims result player index {player_index} is outside {len(players)} players"
        )
    player = players[player_index]
    action_metrics = [
        _normalize_action_metric(
            action,
            iterations=iterations,
            source={"kind": "player", "player_index": player_index, "name": player.get("name")},
        )
        for action in _get(player, "actions", default=[]) or []
        if isinstance(action, dict)
    ]
    for pet_index, pet in enumerate(_get(player, "pets", default=[]) or []):
        if not isinstance(pet, dict):
            continue
        action_metrics.extend(
            _normalize_action_metric(
                action,
                iterations=iterations,
                source={
                    "kind": "pet",
                    "owner_player_index": player_index,
                    "pet_index": pet_index,
                    "name": pet.get("name"),
                },
            )
            for action in _get(pet, "actions", default=[]) or []
            if isinstance(action, dict)
        )
    aura_metrics = [
        {
            "identity": _identity_from_id(aura.get("id")),
            "uptime_seconds_avg": _get(aura, "uptimeSecondsAvg", "uptime_seconds_avg"),
            "uptime_seconds_stdev": _get(aura, "uptimeSecondsStdev", "uptime_seconds_stdev"),
            "procs_avg": _get(aura, "procsAvg", "procs_avg"),
        }
        for aura in _get(player, "auras", default=[]) or []
        if isinstance(aura, dict)
    ]
    resource_metrics = [
        {
            "identity": _identity_from_id(resource.get("id")),
            "resource_type": _get(resource, "type"),
            "events": _get(resource, "events"),
            "gain": _get(resource, "gain"),
            "actual_gain": _get(resource, "actualGain", "actual_gain"),
        }
        for resource in _get(player, "resources", default=[]) or []
        if isinstance(resource, dict)
    ]
    log_text = str(_get(result, "logs", default="") or "")
    return {
        "schema": "rotation_review_wowsims_result_v1",
        "iterations_done": int(_get(result, "iterationsDone", "iterations_done", default=0) or 0),
        "first_iteration_duration_seconds": _get(
            result, "firstIterationDuration", "first_iteration_duration"
        ),
        "avg_iteration_duration_seconds": _get(
            result, "avgIterationDuration", "avg_iteration_duration"
        ),
        "error": _get(result, "error"),
        "player_index": player_index,
        "player_name": player.get("name"),
        "player_dps": _get(player, "dps", default={}),
        "action_metrics": action_metrics,
        "aura_metrics": aura_metrics,
        "resource_metrics": resource_metrics,
        "debug_log_present": bool(log_text),
        "debug_log_sha256": hashlib.sha256(log_text.encode("utf-8")).hexdigest(),
        "timeline": _normalize_wowsims_log(log_text),
    }


def _trinity_gate_families(gates: dict[str, Any]) -> set[str]:
    families: set[str] = set()
    for key, value in gates.items():
        lowered = key.lower()
        defaultish = value in (None, False, "", 0, 0.0, 1, 1.0, "enemy")
        if lowered.startswith("max_") and value in (0, 1, 1.0):
            defaultish = True
        if defaultish:
            continue
        if "enemy" in lowered or "injured_player" in lowered or "attacker" in lowered:
            families.add("enemy_count")
        elif "target_health" in lowered:
            families.add("target_health")
        elif "self_health" in lowered:
            families.add("self_health")
        elif "combo" in lowered:
            families.add("combo_points")
        elif "rune" in lowered:
            families.add("runes")
        elif "primary_power" in lowered or "mana" in lowered:
            families.add("primary_power")
        elif "owned_target_aura" in lowered or "maintain_aura" in lowered or "refresh_aura" in lowered:
            families.add("owned_target_aura")
        elif "aura" in lowered:
            families.add("aura_state")
        elif "range" in lowered or "moving" in lowered or "stationary" in lowered:
            families.add("movement_range")
        elif "pet" in lowered:
            families.add("pet")
        elif "enchant" in lowered:
            families.add("weapon_enchant")
        elif "cooldown" in lowered or "interruptible" in lowered:
            families.add("cooldown")
        elif "shapeshift" in lowered:
            families.add("form_presence")
        elif "creature_type" in lowered:
            families.add("target_type")
        else:
            families.add("unmapped_gate")
    return families


def normalize_trinity_profile(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("Trinity profile must be a JSON object")
    profile = document.get("profile") if isinstance(document.get("profile"), dict) else {}
    actions = document.get("actions")
    if not isinstance(actions, list):
        raise ValueError("Trinity profile dump has no actions array")

    rows: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        spell_id = _first_int(action, "spell_id", "spellId")
        gates = action.get("gates") if isinstance(action.get("gates"), dict) else {}
        weights = action.get("weights") if isinstance(action.get("weights"), dict) else {}
        score = action.get("score")
        rows.append(
            {
                "source": "trinity",
                "profile_index": index,
                "action_kind": "cast" if spell_id else str(action.get("category") or "unknown"),
                "identity": {"kind": "spell", "id": spell_id, "tag": None},
                "category": action.get("category", action.get("action_category")),
                "priority_bucket": int(action.get("priority_bucket", 255)),
                "sort_order": int(action.get("sort_order", index)),
                "score": score if isinstance(score, (int, float)) else None,
                "weights": weights,
                "mechanic_tags": action.get("tags", action.get("mechanic_tags", "")),
                "target_selector": action.get("target_selector"),
                "movement_directive": action.get("movement_directive"),
                "auto_attack_mode": action.get("auto_attack_mode"),
                "gates": gates,
                "gate_families": sorted(_trinity_gate_families(gates)),
                "priority_evidence": (
                    "runtime_candidate_score"
                    if isinstance(score, (int, float))
                    else "static_bucket_then_dynamic_score_unknown"
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            row["priority_bucket"],
            -(float(row["score"]) if isinstance(row["score"], (int, float)) else 0.0),
            row["sort_order"],
            row["identity"]["id"] or 0,
        )
    )
    return {
        "schema": "rotation_review_trinity_profile_v1",
        "source_authority": document.get(
            "source_authority", "runtime_botauto_rotation_dump"
        ),
        "identity_status": (
            "runtime_snapshot_bound"
            if isinstance(document.get("snapshot_generation"), int)
            and bool(document.get("snapshot_content_hash"))
            else "informational_only_identity_incomplete"
        ),
        "profile": profile,
        "snapshot_generation": document.get("snapshot_generation"),
        "snapshot_content_hash": document.get("snapshot_content_hash"),
        "action_count": len(rows),
        "actions": rows,
        "priority_model": (
            "lower priority_bucket, then higher runtime candidate score, then lower "
            "sort_order, then stable action identity; a profile dump has no runtime score"
        ),
    }


def trinity_profile_document_from_database_rows(
    profile_row: dict[str, Any], action_rows: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Project read-only DB rows into the runtime dump review shape.

    This is intentionally not called a runtime snapshot: a loaded worldserver
    can still be on an older generation, and an uncommitted SQL migration can
    differ from both the database and the process snapshot.
    """
    profile_fields = (
        "class_id",
        "spec_tag",
        "role",
        "range_band",
        "movement_directive",
        "auto_attack_mode",
        "profile_source",
        "version",
        "source_note",
        "scope_note",
    )
    actions: list[dict[str, Any]] = []
    for index, row in enumerate(action_rows):
        actions.append(
            {
                "sort_order": int(row.get("sort_order") or index),
                "spell_id": int(row.get("spell_id") or 0),
                "category": row.get("category"),
                "tags": row.get("mechanic_tags") or "",
                "target_selector": row.get("target_selector"),
                "movement_directive": row.get("movement_directive"),
                "auto_attack_mode": row.get("auto_attack_mode"),
                "priority_bucket": int(row.get("priority_bucket") or 255),
                "weights": {
                    key.removesuffix("_weight"): _json_scalar(row.get(key))
                    for key in _TRINITY_WEIGHT_COLUMNS
                },
                "gates": {
                    key: _json_scalar(row.get(key)) for key in _TRINITY_GATE_COLUMNS
                },
            }
        )
    profile = {
        key: _json_scalar(profile_row.get(key))
        for key in profile_fields
        if key in profile_row
    }
    database_rows = {"profile": profile, "actions": actions}
    return {
        "source_authority": "world_database_read_only_static_not_runtime_snapshot",
        "database_rows_content_hash": canonical_sha256(database_rows),
        "snapshot_generation": None,
        "snapshot_content_hash": None,
        **database_rows,
    }


def load_trinity_profile_from_world_database(
    worldserver_conf: Path, class_id: int, spec_tag: str, role: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one enabled profile without exposing database credentials."""
    try:
        from .extract_world_knowledge import (
            connect_mysql,
            database_url_from_worldserver_conf,
            sanitize_database_url,
        )
    except ImportError:
        # The skill documents both ``python -m`` and direct-script use.  A
        # direct invocation has tools/bot_ml on sys.path but no package parent.
        from extract_world_knowledge import (  # type: ignore[no-redef]
            connect_mysql,
            database_url_from_worldserver_conf,
            sanitize_database_url,
        )

    database_url = database_url_from_worldserver_conf(
        worldserver_conf, "WorldDatabaseInfo"
    )
    connection = connect_mysql(database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM bot_rotation_profile "
                "WHERE class_id=%s AND spec_tag=%s AND role=%s LIMIT 1",
                (class_id, spec_tag, role),
            )
            profile = cursor.fetchone()
            if not profile:
                raise ValueError(
                    f"Trinity world database has no profile {class_id}:{spec_tag}:{role}"
                )
            cursor.execute(
                "SELECT * FROM bot_rotation_action "
                "WHERE profile_id=%s AND enabled=1 "
                "ORDER BY priority_bucket, sort_order, id",
                (profile["id"],),
            )
            actions = cursor.fetchall()
    finally:
        connection.close()

    document = trinity_profile_document_from_database_rows(profile, actions)
    return document, {
        "source_authority": document["source_authority"],
        "worldserver_conf": _source_record(worldserver_conf),
        "database": sanitize_database_url(database_url),
        "profile_key": {
            "class_id": class_id,
            "spec_tag": spec_tag,
            "role": role,
        },
        "database_rows_content_hash": document["database_rows_content_hash"],
        "identity_status": "informational_only_identity_incomplete",
    }


def _ordered_unique_spell_ids(rows: Iterable[dict[str, Any]]) -> list[int]:
    ordered: list[int] = []
    seen: set[int] = set()
    for row in rows:
        identity = row.get("identity") or {}
        spell_id = identity.get("id") if identity.get("kind") == "spell" else None
        if not isinstance(spell_id, int) or spell_id <= 0 or spell_id in seen:
            continue
        seen.add(spell_id)
        ordered.append(spell_id)
    return ordered


def _first_spell_rows(rows: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        identity = row.get("identity") or {}
        spell_id = identity.get("id") if identity.get("kind") == "spell" else None
        if isinstance(spell_id, int) and spell_id > 0:
            result.setdefault(spell_id, row)
    return result


def _trinity_priority_relation(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[int | None, str]:
    """Return -1 when left precedes right, 1 when right precedes left."""
    left_bucket = int(left["priority_bucket"])
    right_bucket = int(right["priority_bucket"])
    if left_bucket != right_bucket:
        return (-1 if left_bucket < right_bucket else 1), "priority_bucket"
    left_score = left.get("score")
    right_score = right.get("score")
    if isinstance(left_score, (int, float)) and isinstance(right_score, (int, float)):
        if left_score != right_score:
            return (-1 if left_score > right_score else 1), "runtime_candidate_score"
        left_sort = int(left["sort_order"])
        right_sort = int(right["sort_order"])
        if left_sort != right_sort:
            return (-1 if left_sort < right_sort else 1), "sort_order_tiebreak"
    return None, "runtime_candidate_score_missing"


def compare_rotations(wowsims: dict[str, Any], trinity: dict[str, Any]) -> dict[str, Any]:
    wow_combat = [row for row in wowsims["actions"] if row["phase"] == "combat"]
    wow_prepull = [row for row in wowsims["actions"] if row["phase"] == "prepull"]
    wow_spells = _ordered_unique_spell_ids(wow_combat)
    wow_prepull_spells = _ordered_unique_spell_ids(wow_prepull)
    trinity_spells = _ordered_unique_spell_ids(trinity["actions"])
    wow_set = set(wow_spells)
    trinity_set = set(trinity_spells)
    shared = sorted(wow_set & trinity_set)

    wow_rank = {spell_id: index for index, spell_id in enumerate(wow_spells)}
    trinity_rank = {spell_id: index for index, spell_id in enumerate(trinity_spells)}
    trinity_first = _first_spell_rows(trinity["actions"])
    inversions: list[dict[str, Any]] = []
    uncertain_pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(shared):
        for right in shared[left_index + 1 :]:
            wow_delta = wow_rank[left] - wow_rank[right]
            relation, basis = _trinity_priority_relation(
                trinity_first[left], trinity_first[right]
            )
            if relation is None:
                uncertain_pairs.append(
                    {
                        "spell_a": left,
                        "spell_b": right,
                        "wowsims_order": [wow_rank[left], wow_rank[right]],
                        "reason": basis,
                    }
                )
                continue
            trinity_delta = relation
            if wow_delta * trinity_delta < 0:
                inversions.append(
                    {
                        "spell_a": left,
                        "spell_b": right,
                        "wowsims_order": [wow_rank[left], wow_rank[right]],
                        "trinity_order": [trinity_rank[left], trinity_rank[right]],
                        "trinity_order_basis": basis,
                    }
                )

    wow_families_by_spell: dict[int, set[str]] = {}
    for row in wow_combat:
        identity = row["identity"]
        if identity["kind"] == "spell" and isinstance(identity["id"], int):
            wow_families_by_spell.setdefault(identity["id"], set()).update(row["condition_families"])
    trinity_families_by_spell: dict[int, set[str]] = {}
    for row in trinity["actions"]:
        identity = row["identity"]
        if identity["kind"] == "spell" and isinstance(identity["id"], int):
            trinity_families_by_spell.setdefault(identity["id"], set()).update(row["gate_families"])

    condition_gaps: list[dict[str, Any]] = []
    for spell_id in shared:
        wow_families = wow_families_by_spell.get(spell_id, set()) - {"unmapped_expression"}
        trinity_families = trinity_families_by_spell.get(spell_id, set()) - {"unmapped_gate"}
        missing = sorted(wow_families - trinity_families)
        if missing:
            condition_gaps.append(
                {
                    "spell_id": spell_id,
                    "wowsims_condition_families": sorted(wow_families),
                    "trinity_gate_families": sorted(trinity_families),
                    "unrepresented_in_trinity": missing,
                }
            )

    action_links: list[dict[str, Any]] = []
    for spell_id in shared:
        action_links.append(
            {
                "spell_id": spell_id,
                "wowsims": [
                    {
                        "phase": row["phase"],
                        "priority_index": row["priority_index"],
                        "path": row["path"],
                        "condition_families": row["condition_families"],
                        "condition_expression": row["condition_expression"],
                        "condition_sha256": row["condition_sha256"],
                    }
                    for row in wowsims["actions"]
                    if row["identity"]["kind"] == "spell"
                    and row["identity"]["id"] == spell_id
                ],
                "trinity": [
                    {
                        "priority_bucket": row["priority_bucket"],
                        "score": row["score"],
                        "sort_order": row["sort_order"],
                        "category": row["category"],
                        "gate_families": row["gate_families"],
                        "gates": row["gates"],
                    }
                    for row in trinity["actions"]
                    if row["identity"]["kind"] == "spell"
                    and row["identity"]["id"] == spell_id
                ],
            }
        )

    return {
        "shared_spell_ids": shared,
        "wowsims_only_spell_ids": sorted(wow_set - trinity_set),
        "trinity_only_spell_ids": sorted(trinity_set - wow_set),
        "wowsims_prepull_only_spell_ids": sorted(set(wow_prepull_spells) - wow_set),
        "phase_mismatches": [
            {
                "spell_id": spell_id,
                "wowsims_phase": "prepull_only",
                "trinity_phase": "combat_profile",
                "wowsims_entries": [
                    {
                        "path": row["path"],
                        "schedule": row["schedule"],
                        "schedule_sha256": row["schedule_sha256"],
                    }
                    for row in wow_prepull
                    if row["identity"]["kind"] == "spell"
                    and row["identity"]["id"] == spell_id
                ],
            }
            for spell_id in sorted((set(wow_prepull_spells) - wow_set) & trinity_set)
        ],
        "tagged_wowsims_spell_variants": [
            {
                "spell_id": row["identity"]["id"],
                "tag": row["identity"]["tag"],
                "phase": row["phase"],
                "path": row["path"],
            }
            for row in wowsims["actions"]
            if row["identity"]["kind"] == "spell"
            and row["identity"]["tag"] is not None
        ],
        "unmapped_wowsims_nonspell_actions": [
            {
                "action_kind": row["action_kind"],
                "identity": row["identity"],
                "phase": row["phase"],
                "path": row["path"],
                "schedule": row["schedule"],
                "action_payload": row["action_payload"],
            }
            for row in wowsims["actions"]
            if row["identity"]["kind"] != "spell"
        ],
        "priority_inversions": inversions,
        "priority_uncertain_pairs": uncertain_pairs,
        "condition_family_gaps": condition_gaps,
        "action_links": action_links,
        "coverage": {
            "wowsims_spells": len(wow_set),
            "trinity_spells": len(trinity_set),
            "shared_spells": len(shared),
            "wowsims_spell_coverage_ratio": (
                len(shared) / len(wow_set) if wow_set else None
            ),
        },
        "interpretation": (
            "Spell coverage, order, and condition-family comparisons are review leads, "
            "not semantic-equivalence or DPS claims."
        ),
    }


def _iter_runtime_bots(document: dict[str, Any]) -> Iterator[dict[str, Any]]:
    seen: set[int] = set()
    roots: list[Any] = [document]
    calibration = document.get("combat_calibration")
    if isinstance(calibration, dict):
        completed = calibration.get("previous_window")
        roots.append(completed if isinstance(completed, dict) else calibration)
    for key in ("previous_window", "current_window", "calibration", "report"):
        value = document.get(key)
        if isinstance(value, dict):
            roots.append(value)
    for root in roots:
        for key in ("bots", "members"):
            for bot in root.get(key) or []:
                if isinstance(bot, dict) and id(bot) not in seen:
                    seen.add(id(bot))
                    yield bot


def normalize_runtime_report(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("runtime report must be a JSON object")
    attempts: Counter[int] = Counter()
    damage: Counter[int] = Counter()
    results: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    chosen: Counter[int] = Counter()
    pipeline_edges: Counter[str] = Counter()
    decision_actions: Counter[str] = Counter()
    decision_results: Counter[str] = Counter()
    decision_handlers: Counter[str] = Counter()
    diagnosis_codes: Counter[str] = Counter()
    route_progress_reasons: Counter[str] = Counter()
    movement_samples = 0
    moving_samples = 0
    movement_distance_total = 0.0
    movement_distance_max = 0.0
    calibration_windows: list[dict[str, Any]] = []

    trace_entries = ((document.get("trace") or {}).get("entries") or [])
    unique_attempts: set[tuple[int, int]] = set()
    for entry in trace_entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("action"):
            decision_actions[str(entry["action"])] += 1
        if entry.get("result"):
            decision_results[str(entry["result"])] += 1
        if entry.get("decision_handler"):
            decision_handlers[str(entry["decision_handler"])] += 1
        progress = entry.get("route_progress") or {}
        if isinstance(progress, dict):
            no_progress = progress.get("no_progress") or {}
            if isinstance(no_progress, dict) and no_progress.get("reason"):
                route_progress_reasons[str(no_progress["reason"])] += 1
        combat = entry.get("combat_attempt") or {}
        if not isinstance(combat, dict):
            continue
        at_ms = int(combat.get("recorded_at_ms") or entry.get("timestamp_ms") or 0)
        bot_guid = int(entry.get("bot_guid") or 0)
        if not at_ms or (bot_guid, at_ms) in unique_attempts:
            continue
        unique_attempts.add((bot_guid, at_ms))
        action = combat.get("action") or {}
        failure = combat.get("failure") or {}
        spell_id = int(action.get("spell_id") or 0)
        result = str(failure.get("result") or "unknown")
        if spell_id:
            attempts[spell_id] += 1
            pipeline_edges["native_submission_observed"] += result == "ok"
        results[result] += 1
        reason = str(failure.get("reason") or "")
        if reason:
            rejection_reasons[reason] += 1

    for bot in _iter_runtime_bots(document):
        snapshot = bot.get("snapshot") if isinstance(bot.get("snapshot"), dict) else {}
        decision = snapshot.get("decision") if isinstance(snapshot.get("decision"), dict) else {}
        movement = snapshot.get("movement") if isinstance(snapshot.get("movement"), dict) else {}
        diagnosis = bot.get("diagnosis") if isinstance(bot.get("diagnosis"), dict) else {}
        if decision.get("action"):
            decision_actions[str(decision["action"])] += 1
        if decision.get("result"):
            decision_results[str(decision["result"])] += 1
        if decision.get("handler"):
            decision_handlers[str(decision["handler"])] += 1
        if diagnosis.get("diagnosis_code"):
            diagnosis_codes[str(diagnosis["diagnosis_code"])] += 1
        progress = diagnosis.get("route_progress") or snapshot.get("route_progress") or {}
        if isinstance(progress, dict):
            no_progress = progress.get("no_progress") or {}
            if isinstance(no_progress, dict) and no_progress.get("reason"):
                route_progress_reasons[str(no_progress["reason"])] += 1
        if movement:
            movement_samples += 1
            moving_samples += bool(movement.get("is_moving"))
            distance = float(movement.get("distance_moved_since_last_decision") or 0.0)
            movement_distance_total += distance
            movement_distance_max = max(movement_distance_max, distance)
        for action in bot.get("action_attempts") or []:
            if isinstance(action, dict):
                spell_id = int(action.get("spell_id") or 0)
                if spell_id:
                    attempts[spell_id] = max(attempts[spell_id], int(action.get("count") or 0))
        for spell in bot.get("spell_damage") or []:
            if isinstance(spell, dict):
                spell_id = int(spell.get("spell_id") or 0)
                if spell_id:
                    damage[spell_id] += int(spell.get("damage") or 0)
        aggregate_results = bot.get("result_counts")
        if isinstance(aggregate_results, dict):
            for result, count in aggregate_results.items():
                results[str(result)] += int(count or 0)
        if bot.get("elapsed_seconds") is not None:
            quality = bot.get("quality_metrics")
            calibration_windows.append(
                {
                    "guid": int(bot.get("guid") or 0),
                    "elapsed_seconds": float(bot.get("elapsed_seconds") or 0.0),
                    "damage": int(bot.get("damage") or 0),
                    "dps": float(bot.get("dps") or 0.0),
                    "pet_damage": int(bot.get("pet_damage") or 0),
                    "quality_metrics": quality if isinstance(quality, dict) else {},
                }
            )
        last = bot.get("last_chosen_action")
        if isinstance(last, dict):
            spell_id = int(last.get("spell_id") or 0)
            if spell_id:
                chosen[spell_id] += 1
                pipeline_edges["action_selected_observed"] += 1
        rejects = bot.get("last_action_rejections")
        if isinstance(rejects, list):
            for reject in rejects:
                if isinstance(reject, dict) and reject.get("reason"):
                    rejection_reasons[str(reject["reason"])] += 1

    return {
        "schema": "rotation_review_runtime_observation_v1",
        "attempt_counts_by_spell": {str(key): value for key, value in sorted(attempts.items())},
        "damage_by_spell": {str(key): value for key, value in sorted(damage.items())},
        "chosen_counts_by_spell": {str(key): value for key, value in sorted(chosen.items())},
        "result_counts": dict(sorted(results.items())),
        "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
        "pipeline_edges": dict(sorted(pipeline_edges.items())),
        "calibration_windows": calibration_windows,
        "decision_observation": {
            "action_counts": dict(sorted(decision_actions.items())),
            "result_counts": dict(sorted(decision_results.items())),
            "handler_counts": dict(sorted(decision_handlers.items())),
            "diagnosis_code_counts": dict(sorted(diagnosis_codes.items())),
            "route_progress_reason_counts": dict(sorted(route_progress_reasons.items())),
        },
        "movement_observation": {
            "sample_count": movement_samples,
            "moving_sample_count": moving_samples,
            "moving_sample_ratio": moving_samples / movement_samples if movement_samples else None,
            "distance_moved_since_last_decision_total": movement_distance_total,
            "distance_moved_since_last_decision_max": movement_distance_max,
        },
    }


def normalize_route_manifest(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("route manifest must be a JSON object")
    routes = document.get("routes")
    if not isinstance(routes, list):
        raise ValueError("route manifest has no routes array")
    nodes: list[dict[str, Any]] = []
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            continue
        obligations: list[dict[str, Any]] = []
        for key in (
            "pull_contract",
            "tank_positioning",
            "healer_assignments",
            "target_priority",
            "interrupt_assignments",
            "regrouping",
            "recovery",
            "instance_reset",
        ):
            contract = route.get(key)
            if isinstance(contract, dict):
                obligations.append(
                    {
                        "kind": key,
                        "required": bool(contract.get("required")),
                        "actions": sorted(str(item) for item in (contract.get("actions") or [])),
                    }
                )
        mechanic_contract = route.get("mechanic_contract")
        if isinstance(mechanic_contract, dict):
            obligations.append(
                {
                    "kind": "mechanic_contract",
                    "required": True,
                    "fields": sorted(mechanic_contract),
                    "sha256": canonical_sha256(mechanic_contract),
                }
            )
        nodes.append(
            {
                "index": index,
                "step": route.get("step"),
                "node_id": route.get("route_node_id"),
                "label": route.get("label"),
                "node_kind": route.get("node_kind", route.get("kind")),
                "mechanic_profile": route.get("mechanic_profile"),
                "mechanic_families": sorted(route.get("mechanic_families") or []),
                "completion_policy": route.get("completion_policy"),
                "descent_action": route.get("descent_action") or "",
                "coordinates": {
                    "map_id": route.get("map_id"),
                    "destination": {
                        "x": route.get("x"),
                        "y": route.get("y"),
                        "z": route.get("z"),
                        "o": route.get("o"),
                    },
                    "navigation_anchor": {
                        "x": route.get("navigation_anchor_x"),
                        "y": route.get("navigation_anchor_y"),
                        "z": route.get("navigation_anchor_z"),
                        "o": route.get("navigation_anchor_o"),
                    },
                    "bot_start": {
                        "map_id": route.get("bot_start_map_id"),
                        "x": route.get("bot_start_x"),
                        "y": route.get("bot_start_y"),
                        "z": route.get("bot_start_z"),
                        "o": route.get("bot_start_o"),
                    },
                    "valid": route.get("coordinates_valid"),
                    "missing_reason": route.get("coordinate_missing_reason") or "",
                },
                "expected_membership": {
                    "expected_bot_count": route.get("expected_bot_count"),
                    "expected_alive_count": route.get("expected_alive_count"),
                    "expected_alive_count_semantics": route.get(
                        "expected_alive_count_semantics"
                    ),
                    "roster_identity": route.get("roster_identity") or [],
                },
                "required_evidence": sorted(route.get("required_evidence") or []),
                "evidence_contract": route.get("evidence_contract") or [],
                "hazard_contract": {
                    "source_entry": route.get("hazard_source_entry"),
                    "detection_spell_id": route.get("hazard_detection_spell_id"),
                    "damage_spell_id": route.get("hazard_damage_spell_id"),
                    "shape": route.get("hazard_shape") or "",
                    "radius_yards": route.get("hazard_radius_yards"),
                    "safety_margin_yards": route.get("hazard_safety_margin_yards"),
                },
                "route_source": {
                    "runtime_profile_id": route.get("runtime_profile_id"),
                    "source_table": route.get("source_table"),
                    "source_sql": route.get("source_sql"),
                    "source_guid": route.get("source_guid"),
                },
                "source_entry": route.get("source_entry"),
                "target_entries": sorted(
                    set(route.get("pack_target_entries") or [])
                    | set(route.get("alternate_target_entries") or [])
                    | ({route.get("source_entry")} if route.get("source_entry") else set())
                ),
                "obligations": obligations,
            }
        )
    return {
        "schema": "rotation_review_route_mechanics_v1",
        "scenario_id": document.get("scenario_id"),
        "route_count": len(nodes),
        "nodes": nodes,
    }


def load_route_document(path: Path, scenario_id: str | None = None) -> dict[str, Any]:
    """Load either a generated route manifest or the canonical routes JSONL."""
    try:
        document = _load_json(path)
    except ValueError as json_error:
        rows: list[Any] = []
        try:
            for line_number, line in enumerate(path.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"route JSONL row {line_number} is not an object")
                rows.append(row)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"cannot load route JSON/JSONL from {path}: {exc}") from json_error
        document = rows

    if isinstance(document, dict) and isinstance(document.get("routes"), list):
        declared = str(document.get("scenario_id") or "")
        if scenario_id and declared and declared != scenario_id:
            raise ValueError(
                f"route scenario mismatch: requested {scenario_id}, document declares {declared}"
            )
        return document

    rows = document if isinstance(document, list) else []
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("route input is neither a manifest nor an object-per-line route list")
    scenario_ids = sorted({str(row.get("scenario_id") or "") for row in rows})
    if scenario_id:
        rows = [row for row in rows if str(row.get("scenario_id") or "") == scenario_id]
        if not rows:
            raise ValueError(f"route scenario {scenario_id} has no rows in {path}")
        selected_scenario = scenario_id
    elif len(scenario_ids) == 1 and scenario_ids[0]:
        selected_scenario = scenario_ids[0]
    else:
        raise ValueError(
            "route JSONL contains multiple scenarios; pass --route-scenario-id"
        )
    rows.sort(key=lambda row: (int(row.get("step") or 0), str(row.get("route_node_id") or "")))
    return {"scenario_id": selected_scenario, "routes": rows}


def compare_apl_to_simulated_actions(
    wowsims: dict[str, Any], wowsims_result: dict[str, Any]
) -> dict[str, Any]:
    apl_spells = set(_ordered_unique_spell_ids(wowsims["actions"]))
    simulated_player_spells: set[int] = set()
    simulated_passive_player_spells: set[int] = set()
    simulated_pet_spells: set[int] = set()
    simulated_player_rows: dict[int, list[dict[str, Any]]] = {}
    for row in wowsims_result["action_metrics"]:
        identity = row["identity"]
        spell_id = identity.get("id") if identity.get("kind") == "spell" else None
        if not isinstance(spell_id, int):
            continue
        casts = float(row["per_iteration_target_metric_sums"].get("casts") or 0.0)
        if casts <= 0:
            continue
        if row["source"]["kind"] == "pet":
            simulated_pet_spells.add(spell_id)
        elif row["is_passive"]:
            simulated_passive_player_spells.add(spell_id)
        else:
            simulated_player_spells.add(spell_id)
            simulated_player_rows.setdefault(spell_id, []).append(row)
    return {
        "apl_spell_ids_observed_as_player_actions": sorted(apl_spells & simulated_player_spells),
        "apl_spell_ids_not_observed_as_player_actions": sorted(apl_spells - simulated_player_spells),
        "simulated_player_spell_ids_absent_from_apl": sorted(simulated_player_spells - apl_spells),
        "simulated_passive_player_spell_ids": sorted(simulated_passive_player_spells),
        "simulated_pet_spell_ids": sorted(simulated_pet_spells),
        "observed_action_metrics_by_apl_spell": {
            str(spell_id): rows for spell_id, rows in sorted(simulated_player_rows.items())
            if spell_id in apl_spells
        },
        "interpretation": (
            "An APL spell can be absent because its condition never became true; a simulated "
            "action can be passive, pet-driven, proc-driven, or engine-managed. Inspect the "
            "timeline and original APL path before treating either set difference as a defect."
        ),
    }


def compare_simulated_to_trinity_runtime(
    wowsims_result: dict[str, Any], runtime: dict[str, Any]
) -> dict[str, Any]:
    sim_rows: dict[int, list[dict[str, Any]]] = {}
    for row in wowsims_result["action_metrics"]:
        identity = row["identity"]
        spell_id = identity.get("id") if identity.get("kind") == "spell" else None
        if not isinstance(spell_id, int) or row["source"]["kind"] != "player":
            continue
        sim_rows.setdefault(spell_id, []).append(row)
    trinity_attempts = {
        int(spell_id): count
        for spell_id, count in runtime["attempt_counts_by_spell"].items()
    }
    trinity_damage = {
        int(spell_id): count
        for spell_id, count in runtime["damage_by_spell"].items()
    }
    sim_spells = set(sim_rows)
    trinity_spells = set(trinity_attempts) | set(trinity_damage)
    links = []
    for spell_id in sorted(sim_spells | trinity_spells):
        links.append(
            {
                "spell_id": spell_id,
                "wowsims_action_metrics": sim_rows.get(spell_id, []),
                "trinity_attempt_count": trinity_attempts.get(spell_id, 0),
                "trinity_landed_damage": trinity_damage.get(spell_id, 0),
            }
        )
    return {
        "shared_observed_spell_ids": sorted(sim_spells & trinity_spells),
        "wowsims_only_observed_spell_ids": sorted(sim_spells - trinity_spells),
        "trinity_only_observed_spell_ids": sorted(trinity_spells - sim_spells),
        "action_links": links,
        "interpretation": (
            "WoWSims values are per-iteration aggregates while Trinity values describe the "
            "supplied native run. Compare action presence, cadence, resource/aura timing, and "
            "failure edges only after encounter/setup identities are compatible."
        ),
    }


def build_review(
    *,
    wowsims_apl: dict[str, Any] | None = None,
    wowsims_result: dict[str, Any] | None = None,
    wowsims_player_index: int = 0,
    trinity_profile: dict[str, Any] | None = None,
    runtime_report: dict[str, Any] | None = None,
    route_manifest: dict[str, Any] | None = None,
    sources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema": SCHEMA,
        "sources": sources or {},
        "wowsims": normalize_wowsims_apl(wowsims_apl) if wowsims_apl else None,
        "wowsims_result": (
            normalize_wowsims_result(wowsims_result, wowsims_player_index)
            if wowsims_result
            else None
        ),
        "trinity": normalize_trinity_profile(trinity_profile) if trinity_profile else None,
        "runtime": normalize_runtime_report(runtime_report) if runtime_report else None,
        "mechanics": normalize_route_manifest(route_manifest) if route_manifest else None,
    }
    review["comparison"] = (
        compare_rotations(review["wowsims"], review["trinity"])
        if review["wowsims"] and review["trinity"]
        else None
    )
    review["execution_comparison"] = {
        "apl_to_wowsims_result": (
            compare_apl_to_simulated_actions(review["wowsims"], review["wowsims_result"])
            if review["wowsims"] and review["wowsims_result"]
            else None
        ),
        "wowsims_result_to_trinity_runtime": (
            compare_simulated_to_trinity_runtime(review["wowsims_result"], review["runtime"])
            if review["wowsims_result"] and review["runtime"]
            else None
        ),
    }
    review["review_sha256"] = canonical_sha256(review)
    return review


def _source_record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": file_sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare WoWSims APL, Trinity profile, runtime trace, and route mechanics."
    )
    parser.add_argument("--wowsims-apl", type=Path)
    parser.add_argument("--wowsims-player-index", type=int, default=0)
    parser.add_argument("--wowsims-result", type=Path)
    parser.add_argument("--trinity-profile", type=Path)
    parser.add_argument("--trinity-worldserver-conf", type=Path)
    parser.add_argument("--trinity-class-id", type=int)
    parser.add_argument("--trinity-spec-tag")
    parser.add_argument("--trinity-role", default="dps")
    parser.add_argument("--runtime-report", type=Path)
    parser.add_argument("--route-manifest", type=Path)
    parser.add_argument("--route-scenario-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.trinity_profile and args.trinity_worldserver_conf:
        parser.error(
            "--trinity-profile and --trinity-worldserver-conf are mutually exclusive"
        )
    database_selector = (
        args.trinity_worldserver_conf,
        args.trinity_class_id,
        args.trinity_spec_tag,
    )
    if any(value is not None for value in database_selector) and not all(
        value is not None for value in database_selector
    ):
        parser.error(
            "database review requires --trinity-worldserver-conf, "
            "--trinity-class-id, and --trinity-spec-tag"
        )
    if not any((args.wowsims_apl, args.wowsims_result, args.trinity_profile, args.trinity_worldserver_conf, args.runtime_report, args.route_manifest)):
        parser.error("provide at least one review input")

    sources: dict[str, Any] = {}
    apl = None
    if args.wowsims_apl:
        raw = _load_json(args.wowsims_apl)
        apl = find_wowsims_apl(raw, args.wowsims_player_index)
        sources["wowsims_apl"] = _source_record(args.wowsims_apl)
    wowsims_result = _load_json(args.wowsims_result) if args.wowsims_result else None
    if args.wowsims_result:
        sources["wowsims_result"] = _source_record(args.wowsims_result)
    profile = _load_json(args.trinity_profile) if args.trinity_profile else None
    if args.trinity_profile:
        sources["trinity_profile"] = _source_record(args.trinity_profile)
    elif args.trinity_worldserver_conf:
        profile, profile_source = load_trinity_profile_from_world_database(
            args.trinity_worldserver_conf,
            args.trinity_class_id,
            args.trinity_spec_tag,
            args.trinity_role,
        )
        sources["trinity_profile"] = profile_source
    runtime = _load_json(args.runtime_report) if args.runtime_report else None
    if args.runtime_report:
        sources["runtime_report"] = _source_record(args.runtime_report)
    route = (
        load_route_document(args.route_manifest, args.route_scenario_id)
        if args.route_manifest
        else None
    )
    if args.route_manifest:
        sources["route_manifest"] = _source_record(args.route_manifest)

    review = build_review(
        wowsims_apl=apl,
        wowsims_result=wowsims_result,
        wowsims_player_index=args.wowsims_player_index,
        trinity_profile=profile,
        runtime_report=runtime,
        route_manifest=route,
        sources=sources,
    )
    rendered = json.dumps(review, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
