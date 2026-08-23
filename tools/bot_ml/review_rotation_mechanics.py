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
from typing import Any, Iterable, Iterator, Mapping

from .wowsims_gear_binding import canonical_wowsims_manifest


SCHEMA = "trinity_wowsims_rotation_mechanics_review_v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
GEAR_PROFILES = REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


_NON_BLOCKING_MOVEMENT_RESULTS = {
    "native_movement_submitted",
    "higher_priority_movement_active",
    "grounded_landing_and_onward_path_proven",
}
_EXPLICIT_MOVEMENT_BLOCKER_MARKERS = (
    "reject",
    "stuck",
    "no_progress",
    "no-progress",
    "stall",
    "repeated",
    "unreachable",
    "invalid_",
    "_invalid",
    "unsafe_native_path",
    "no_fallback",
)


def _is_pre_scoring_blocker_result(result: str) -> bool:
    """Keep successful movement evidence out of the warmup blocker ledger."""
    normalized = result.strip().lower()
    if not normalized:
        return False
    if normalized.startswith("persistent_setup_"):
        return True
    if normalized in _NON_BLOCKING_MOVEMENT_RESULTS:
        return False
    return any(marker in normalized for marker in _EXPLICIT_MOVEMENT_BLOCKER_MARKERS)

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
    "min_hostile_target_health_pct",
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


def _embedded_wowsims_request(document: Any) -> dict[str, Any] | None:
    """Return a canonical embedded RaidSimRequest, when one is present."""
    normalized_document = _camelize_json_keys(document)
    if isinstance(normalized_document, dict) and isinstance(
        normalized_document.get("raid"), dict
    ):
        return normalized_document
    return None


def _admit_wowsims_request(
    *,
    embedded_request: dict[str, Any] | None,
    explicit_request: Any | None,
    explicit_path: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Admit one canonical request and its optional source provenance."""
    canonical_explicit = (
        _camelize_json_keys(explicit_request)
        if explicit_path is not None
        else None
    )
    if canonical_explicit is not None and not isinstance(canonical_explicit, dict):
        raise ValueError("--wowsims-request must contain a JSON object")
    if canonical_explicit is not None and not isinstance(
        canonical_explicit.get("raid"), dict
    ):
        raise ValueError("--wowsims-request must contain a raid object")

    if (
        embedded_request is not None
        and canonical_explicit is not None
        and canonical_sha256(embedded_request) != canonical_sha256(canonical_explicit)
    ):
        raise ValueError(
            "embedded WoWSims request in --wowsims-apl conflicts with "
            "--wowsims-request"
        )

    request = canonical_explicit or embedded_request
    source = None
    if request is not None and explicit_path is not None:
        source = _source_record(explicit_path)
        source["canonical_sha256"] = canonical_sha256(request)
    return request, source


def normalize_wowsims_gear(
    document: Any, player_index: int = 0
) -> dict[str, Any] | None:
    normalized = _camelize_json_keys(document)
    raid = normalized.get("raid") if isinstance(normalized, dict) else None
    if not isinstance(raid, dict):
        return None
    players: list[Any] = []
    for party in raid.get("parties") or []:
        if isinstance(party, dict):
            players.extend(party.get("players") or [])
    if not 0 <= player_index < len(players) or not isinstance(
        players[player_index], dict
    ):
        raise ValueError("WoWSims request player index is outside the raid")
    equipment = players[player_index].get("equipment")
    if not isinstance(equipment, dict):
        raise ValueError("WoWSims request player equipment is missing")
    gear_profile_bytes = GEAR_PROFILES.read_bytes()
    gear_profiles = json.loads(gear_profile_bytes)
    slot_map = gear_profiles.get("slot_map")
    if not isinstance(slot_map, list) or not slot_map:
        raise ValueError("WoWSims gear slot map is missing")
    manifest = canonical_wowsims_manifest(
        equipment, [int(value) for value in slot_map]
    )
    return {
        "schema": "rotation_review_wowsims_gear_identity_v1",
        "player_index": player_index,
        "manifest": manifest,
        "manifest_sha256": canonical_sha256(manifest),
        "slot_map_path": str(GEAR_PROFILES.relative_to(REPO_ROOT)),
        "slot_map_file_sha256": hashlib.sha256(gear_profile_bytes).hexdigest(),
    }


def normalize_wowsims_consumables(
    document: Any, player_index: int = 0
) -> dict[str, Any] | None:
    normalized = _camelize_json_keys(document)
    raid = normalized.get("raid") if isinstance(normalized, dict) else None
    if not isinstance(raid, dict):
        return None
    players: list[Any] = []
    for party in raid.get("parties") or []:
        if isinstance(party, dict):
            players.extend(party.get("players") or [])
    if not 0 <= player_index < len(players) or not isinstance(
        players[player_index], dict
    ):
        raise ValueError("WoWSims request player index is outside the raid")
    consumes = players[player_index].get("consumes") or players[player_index].get(
        "consumables"
    )
    if not isinstance(consumes, dict):
        return None
    return {
        "schema": "rotation_review_wowsims_consumables_v1",
        "player_index": player_index,
        "flask": {"item_id": int(consumes.get("flaskId") or 0)},
        "food": {"item_id": int(consumes.get("foodId") or 0)},
        "prepot": {"item_id": int(consumes.get("prepotId") or 0)},
        "combat_potion": {"item_id": int(consumes.get("potId") or 0)},
    }


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
    if " Pet inherited stats: " in line:
        return "pet_inherited_stats"
    if " Pet stats: " in line:
        return "pet_stats"
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
        pet_stats_match = re.search(
            r" (?:Pet inherited stats|Pet stats): (?P<stats>\{.*\})$", raw
        )
        if pet_stats_match:
            try:
                raw_pet_stats = json.loads(
                    re.sub(r",\s*}", "}", pet_stats_match.group("stats"))
                )
            except json.JSONDecodeError:
                raw_pet_stats = {}
            event["stat_vector"] = {
                re.sub(r"(?<!^)(?=[A-Z])", "_", str(key)).lower(): float(value)
                for key, value in raw_pet_stats.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
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
        "pet_stat_references": [
            {
                "line_index": event["line_index"],
                "timestamp_seconds": event["timestamp_seconds"],
                "kind": event["kind"],
                "source_entity": event["source_entity"],
                "stat_vector": event.get("stat_vector") or {},
            }
            for event in events
            if event["kind"] in {"pet_stats", "pet_inherited_stats"}
        ],
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


def _wowsims_unit_stat_vector(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("WoWSims UnitStats is missing")
    stats = value.get("stats") or []
    pseudo = value.get("pseudoStats") or value.get("pseudo_stats") or []
    if len(stats) < 27 or len(pseudo) < 16:
        raise ValueError("WoWSims UnitStats arrays are incomplete")
    return {
        "api_version": int(value.get("apiVersion") or value.get("api_version") or 0),
        "stats": {
            "strength": float(stats[0]),
            "agility": float(stats[1]),
            "stamina": float(stats[2]),
            "intellect": float(stats[3]),
            "spirit": float(stats[4]),
            "hit_rating": float(stats[5]),
            "crit_rating": float(stats[6]),
            "haste_rating": float(stats[7]),
            "expertise_rating": float(stats[8]),
            "dodge_rating": float(stats[9]),
            "parry_rating": float(stats[10]),
            "mastery_rating": float(stats[11]),
            "attack_power": float(stats[12]),
            "ranged_attack_power": float(stats[13]),
            "spell_power": float(stats[14]),
            "armor": float(stats[22]),
            "bonus_armor": float(stats[23]),
            "health": float(stats[24]),
            "mana": float(stats[25]),
        },
        "pseudo_stats": {
            "melee_speed_multiplier": float(pseudo[6]),
            "ranged_speed_multiplier": float(pseudo[7]),
            "cast_speed_multiplier": float(pseudo[8]),
            "melee_haste_pct": float(pseudo[9]),
            "ranged_haste_pct": float(pseudo[10]),
            "spell_haste_pct": float(pseudo[11]),
            "physical_hit_pct": float(pseudo[12]),
            "spell_hit_pct": float(pseudo[13]),
            "physical_crit_pct": float(pseudo[14]),
            "spell_crit_pct": float(pseudo[15]),
        },
    }


def normalize_wowsims_compute_stats(
    document: Any, player_index: int = 0
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("WoWSims ComputeStats result must be a JSON object")
    raid_stats = _get(document, "raidStats", "raid_stats", default={}) or {}
    players: list[dict[str, Any]] = []
    for party in _get(raid_stats, "parties", default=[]) or []:
        if isinstance(party, dict):
            players.extend(_get(party, "players", default=[]) or [])
    if not 0 <= player_index < len(players):
        raise ValueError(
            f"WoWSims ComputeStats player index {player_index} is outside {len(players)} players"
        )
    player = players[player_index]
    stages: dict[str, Any] = {}
    for stage, camel, snake in (
        ("base", "baseStats", "base_stats"),
        ("gear", "gearStats", "gear_stats"),
        ("talents", "talentsStats", "talents_stats"),
        ("buffs", "buffsStats", "buffs_stats"),
        ("consumes", "consumesStats", "consumes_stats"),
        ("final", "finalStats", "final_stats"),
    ):
        stages[stage] = _wowsims_unit_stat_vector(_get(player, camel, snake))
    final = stages["final"]
    primary_stat = max(
        ("strength", "agility", "intellect"),
        key=lambda key: final["stats"][key],
    )
    if primary_stat == "intellect":
        archetype = "spell"
    elif final["stats"]["ranged_attack_power"] > final["stats"]["attack_power"]:
        archetype = "ranged"
    else:
        archetype = "melee"
    normalized = {
        "schema": "rotation_review_wowsims_effective_stats_v1",
        "player_index": player_index,
        "primary_stat": primary_stat,
        "archetype": archetype,
        "stage": "final_stats_before_dynamic_combat_procs",
        "stages": stages,
    }
    normalized["content_sha256"] = canonical_sha256(normalized)
    return normalized


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
        "critBlocks",
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
                # Zero is a valid highest-priority bucket; do not coerce it
                # to the missing-value sentinel.
                "priority_bucket": int(
                    row["priority_bucket"]
                    if row.get("priority_bucket") is not None
                    else 255
                ),
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


def _spec_identity(trinity: dict[str, Any] | None) -> dict[str, Any]:
    """Return the review scope without treating a profile as live evidence."""
    profile = (trinity or {}).get("profile") or {}
    return {
        "class_id": profile.get("class_id"),
        "spec_tag": profile.get("spec_tag"),
        "role": profile.get("role"),
    }


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
        "spec_identity": _spec_identity(trinity),
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
        "mismatch_summary": {
            "spec_identity": _spec_identity(trinity),
            "priority_inversion_count": len(inversions),
            "priority_uncertain_pair_count": len(uncertain_pairs),
            "condition_family_gap_count": len(condition_gaps),
            "wowsims_only_spell_count": len(wow_set - trinity_set),
            "trinity_only_spell_count": len(trinity_set - wow_set),
            "phase_mismatch_count": len(
                (set(wow_prepull_spells) - wow_set) & trinity_set
            ),
            "unmapped_nonspell_action_count": sum(
                row["identity"]["kind"] != "spell" for row in wowsims["actions"]
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


def _canonical_runtime_gear(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("Trinity scoring-window gear observation is missing")
    manifest: list[dict[str, Any]] = []
    slots: set[int] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("Trinity scoring-window gear item is invalid")
        slot = int(raw.get("slot", -1))
        item_id = int(raw.get("item_id") or 0)
        if slot < 0 or slot in slots or item_id <= 0:
            raise ValueError("Trinity scoring-window gear identity is invalid")
        slots.add(slot)
        gems = [int(value or 0) for value in raw.get("gem_item_ids") or []]
        while gems and gems[-1] == 0:
            gems.pop()
        manifest.append(
            {
                "slot": slot,
                "item_id": item_id,
                "enchant_id": int(raw.get("enchant_id") or 0),
                "reforge_id": int(raw.get("reforge_id") or 0),
                "gem_item_ids": gems,
            }
        )
    return sorted(manifest, key=lambda row: row["slot"])


def normalize_runtime_report(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("runtime report must be a JSON object")
    calibration = document.get("combat_calibration")
    calibration_complete = bool(
        isinstance(calibration, dict)
        and (
            str(calibration.get("phase") or "").lower() == "complete"
            or bool(calibration.get("window_complete"))
        )
    )
    attempts: Counter[int] = Counter()
    damage: Counter[int] = Counter()
    damage_events: Counter[int] = Counter()
    pet_damage: Counter[int] = Counter()
    pet_damage_events: Counter[int] = Counter()
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
    scoring_start_stats: list[dict[str, Any]] = []
    gear_identities: list[dict[str, Any]] = []
    pet_execution_observations: list[dict[str, Any]] = []
    consumable_execution_observations: list[dict[str, Any]] = []
    initial_resource_failures: list[dict[str, Any]] = []
    pre_scoring_blockers: list[dict[str, Any]] = []
    decision_timeline: list[dict[str, Any]] = []
    off_target_damage_events: list[dict[str, Any]] = []
    primary_pet_shadow_bite_events: list[dict[str, Any]] = []
    dragonwrath_copy_proc_observations: list[dict[str, Any]] = []
    will_of_unbinding_observations: list[dict[str, Any]] = []

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
        bot_guid = int(bot.get("guid") or 0)
        initial_resources = (
            bot.get("initial_resources")
            if isinstance(bot.get("initial_resources"), dict)
            else {}
        )
        if (
            initial_resources.get("matches_contract") is False
            and int(initial_resources.get("observed_at_ms") or 0) > 0
        ):
            mismatches = [
                dict(row)
                for row in initial_resources.get("powers") or []
                if isinstance(row, dict) and row.get("matches_contract") is False
            ]
            persistent_setup = (
                bot.get("persistent_setup")
                if isinstance(bot.get("persistent_setup"), dict)
                else {}
            )
            initial_resource_failures.append(
                {
                    "bot_guid": bot_guid,
                    "observed_at_ms": int(
                        initial_resources.get("observed_at_ms") or 0
                    ),
                    "power_mismatches": mismatches,
                    "pet_pre_score_resummon": dict(
                        persistent_setup.get("pet_pre_score_resummon") or {}
                    )
                    if isinstance(
                        persistent_setup.get("pet_pre_score_resummon"), dict
                    )
                    else {},
                }
            )
        gear_observation = bot.get("gear_profile_observation")
        if isinstance(gear_observation, dict):
            manifest = _canonical_runtime_gear(gear_observation.get("items"))
            gear_identities.append(
                {
                    "bot_guid": bot_guid,
                    "manifest": manifest,
                    "manifest_sha256": canonical_sha256(manifest),
                }
            )
        start_stats = bot.get("scoring_start_stats")
        if isinstance(start_stats, dict):
            scoring_start_stats.append(
                {
                    "bot_guid": bot_guid,
                    "schema": str(start_stats.get("schema") or ""),
                    "player": dict(start_stats.get("player") or {})
                    if isinstance(start_stats.get("player"), dict)
                    else {},
                    "pet": dict(start_stats.get("pet") or {})
                    if isinstance(start_stats.get("pet"), dict)
                    else {},
                }
            )
        snapshot = bot.get("snapshot") if isinstance(bot.get("snapshot"), dict) else {}
        decision = snapshot.get("decision") if isinstance(snapshot.get("decision"), dict) else {}
        movement = snapshot.get("movement") if isinstance(snapshot.get("movement"), dict) else {}
        movement_diagnostic = (
            bot.get("movement_diagnostic")
            if isinstance(bot.get("movement_diagnostic"), dict)
            else {}
        )
        recovery_result = str(movement_diagnostic.get("last_recovery_result") or "")
        if not calibration_complete and _is_pre_scoring_blocker_result(recovery_result):
            persistent_setup = (
                bot.get("persistent_setup")
                if isinstance(bot.get("persistent_setup"), dict)
                else {}
            )
            pre_scoring_blockers.append(
                {
                    "bot_guid": bot_guid,
                    "reason": recovery_result,
                    "attempts": int(bot.get("attempts") or 0),
                    "pet_present": bool(persistent_setup.get("pet_present")),
                    "pet_spellbook_sha256": str(
                        persistent_setup.get("pet_spellbook_sha256") or ""
                    ),
                    "pet_admission_spellbook_sha256": str(
                        persistent_setup.get("pet_admission_spellbook_sha256") or ""
                    ),
                }
            )
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
                    damage_events[spell_id] += int(spell.get("event_count") or 0)
        for spell in bot.get("primary_pet_spell_damage") or []:
            if isinstance(spell, dict):
                spell_id = int(spell.get("spell_id") or 0)
                # Spell id 0 is the native melee bucket. Keep it when the
                # simulator/native report carries an actual damage event so
                # pet melee is not silently dropped from attribution.
                if spell_id or spell.get("damage") or spell.get("event_count"):
                    pet_damage[spell_id] += int(spell.get("damage") or 0)
                    pet_damage_events[spell_id] += int(spell.get("event_count") or 0)
        for event in bot.get("primary_pet_shadow_bite_events") or []:
            if not isinstance(event, dict):
                continue
            aura_spell_ids = sorted(
                int(spell_id or 0)
                for spell_id in event.get(
                    "owner_cast_warlock_periodic_damage_aura_spell_ids"
                )
                or []
            )
            aura_count = (
                int(event["owner_cast_warlock_periodic_damage_aura_count"])
                if "owner_cast_warlock_periodic_damage_aura_count" in event
                else len(aura_spell_ids)
            )
            primary_pet_shadow_bite_events.append(
                {
                    "bot_guid": bot_guid,
                    "elapsed_ms": int(event.get("elapsed_ms") or 0),
                    "measured_damage": int(event.get("measured_damage") or 0),
                    "unmitigated_damage": int(
                        event.get("unmitigated_damage") or 0
                    ),
                    "pet_spell_power": int(event.get("pet_spell_power") or 0),
                    "pet_spell_crit_pct": float(
                        event.get("pet_spell_crit_pct") or 0.0
                    ),
                    "owner_cast_warlock_periodic_damage_aura_spell_ids": aura_spell_ids,
                    "owner_cast_warlock_periodic_damage_aura_count": aura_count,
                }
            )
        dragonwrath = bot.get("dragonwrath_copy_proc")
        if isinstance(dragonwrath, dict):
            dragonwrath_copy_proc_observations.append(
                {
                    "bot_guid": bot_guid,
                    "aura_spell_id": int(dragonwrath.get("aura_spell_id") or 0),
                    "copy_spell_id_semantics": str(
                        dragonwrath.get("copy_spell_id_semantics") or ""
                    ),
                    "periodic_copy_spell_id": int(
                        dragonwrath.get("periodic_copy_spell_id") or 0
                    ),
                    "landed_damage_attribution_available": bool(
                        dragonwrath.get("landed_damage_attribution_available", False)
                    ),
                    "landed_damage_attribution_limitation": str(
                        dragonwrath.get("landed_damage_attribution_limitation") or ""
                    ),
                    "attempts": [
                        {
                            "original_spell_id": int(row.get("original_spell_id") or 0),
                            "attempt_count": int(row.get("attempt_count") or 0),
                            "accepted_count": int(row.get("accepted_count") or 0),
                            "rejected_count": int(row.get("rejected_count") or 0),
                            "last_cast_result": int(row.get("last_cast_result") or 0),
                        }
                        for row in dragonwrath.get("attempts") or []
                        if isinstance(row, dict)
                    ],
                }
            )
        will_of_unbinding = bot.get("will_of_unbinding")
        if isinstance(will_of_unbinding, dict):
            will_of_unbinding_observations.append(
                {
                    "bot_guid": bot_guid,
                    "schema": str(will_of_unbinding.get("schema") or ""),
                    "stack_aura_spell_id": int(
                        will_of_unbinding.get("stack_aura_spell_id") or 0
                    ),
                    "proc_aura_spell_id": int(
                        will_of_unbinding.get("proc_aura_spell_id") or 0
                    ),
                    "observation_sample_count": int(
                        will_of_unbinding.get("observation_sample_count") or 0
                    ),
                    "stack_transition_count": int(
                        will_of_unbinding.get("stack_transition_count") or 0
                    ),
                    "stack_increase_count": int(
                        will_of_unbinding.get("stack_increase_count") or 0
                    ),
                    "stack_decrease_count": int(
                        will_of_unbinding.get("stack_decrease_count") or 0
                    ),
                    "proc_attempt_observation_available": bool(
                        will_of_unbinding.get(
                            "proc_attempt_observation_available", False
                        )
                    ),
                    "proc_acceptance_observation_available": bool(
                        will_of_unbinding.get(
                            "proc_acceptance_observation_available", False
                        )
                    ),
                    "proc_attempt_count": int(
                        will_of_unbinding.get("proc_attempt_count") or 0
                    ),
                    "proc_accepted_count": int(
                        will_of_unbinding.get("proc_accepted_count") or 0
                    ),
                    "proc_observation_basis": str(
                        will_of_unbinding.get("proc_observation_basis") or ""
                    ),
                    "initial_stacks": int(
                        will_of_unbinding.get("initial_stacks") or 0
                    ),
                    "last_observed_stacks": int(
                        will_of_unbinding.get("last_observed_stacks") or 0
                    ),
                    "last_observed_at_ms": int(
                        will_of_unbinding.get("last_observed_at_ms") or 0
                    ),
                    "scoring_start_effective_intellect": float(
                        will_of_unbinding.get(
                            "scoring_start_effective_intellect", 0.0
                        )
                        or 0.0
                    ),
                    "scoring_start_effective_spell_power": int(
                        will_of_unbinding.get(
                            "scoring_start_effective_spell_power", 0
                        )
                        or 0
                    ),
                    "stack_transitions": [
                        {
                            "elapsed_ms": int(row.get("elapsed_ms") or 0),
                            "previous_stacks": int(
                                row.get("previous_stacks") or 0
                            ),
                            "current_stacks": int(
                                row.get("current_stacks") or 0
                            ),
                            "effective_intellect": float(
                                row.get("effective_intellect", 0.0) or 0.0
                            ),
                            "effective_spell_power": int(
                                row.get("effective_spell_power") or 0
                            ),
                        }
                        for row in will_of_unbinding.get("stack_transitions") or []
                        if isinstance(row, dict)
                    ],
                }
            )
        aggregate_results = bot.get("result_counts")
        if isinstance(aggregate_results, dict):
            for result, count in aggregate_results.items():
                results[str(result)] += int(count or 0)
        persistent_setup = (
            bot.get("persistent_setup")
            if isinstance(bot.get("persistent_setup"), dict)
            else {}
        )
        pet_execution = bot.get("pet_execution_observation")
        if not isinstance(pet_execution, dict):
            pet_execution = persistent_setup.get("pet_execution_observation")
        if isinstance(pet_execution, dict):
            pet_execution_observations.append(
                {
                    "bot_guid": bot_guid,
                    **{
                        str(key): value
                        for key, value in pet_execution.items()
                        if isinstance(key, str)
                    },
                }
            )
        consumable_execution = bot.get("consumable_execution_observation")
        if isinstance(consumable_execution, dict):
            consumable_execution_observations.append(
                {"bot_guid": bot_guid, **dict(consumable_execution)}
            )
        else:
            legacy_conditions = bot.get("reference_condition_observation")
            if isinstance(legacy_conditions, dict):
                configured = legacy_conditions.get("configured") or {}
                dynamic = legacy_conditions.get("dynamic_disabled") or {}
                consumable_execution_observations.append(
                    {
                        "bot_guid": bot_guid,
                        "schema": "legacy_static_reference_conditions_v1",
                        "inventory_backed": False,
                        "flask": {
                            "item_id": int(configured.get("flask_item_id") or 0),
                            "native_use_count": 0,
                        },
                        "food": {
                            "item_id": int(configured.get("food_item_id") or 0),
                            "native_use_count": 0,
                        },
                        "prepot": {
                            "item_id": int(dynamic.get("prepot_item_id") or 0),
                            "native_use_count": int(
                                dynamic.get("prepot_use_count") or 0
                            ),
                        },
                        "combat_potion": {
                            "item_id": int(
                                dynamic.get("combat_potion_item_id") or 0
                            ),
                            "native_use_count": int(
                                dynamic.get("combat_potion_use_count") or 0
                            ),
                        },
                    }
                )
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
        for event in bot.get("decision_timeline") or []:
            if not isinstance(event, dict):
                continue
            normalized_event = {
                "bot_guid": bot_guid,
                "elapsed_ms": int(event.get("elapsed_ms") or 0),
                "spell_id": int(event.get("spell_id") or 0),
                "result": str(event.get("result") or ""),
                "health": int(event.get("health") or 0),
                "max_health": int(event.get("max_health") or 0),
                "mana": int(event.get("mana") or 0),
                "max_mana": int(event.get("max_mana") or 0),
                "current_generic_spell_id": int(event.get("current_generic_spell_id") or 0),
                "current_channeled_spell_id": int(event.get("current_channeled_spell_id") or 0),
                "pet_health": int(event.get("pet_health") or 0),
                "pet_max_health": int(event.get("pet_max_health") or 0),
                "pet_alive": bool(event.get("pet_alive", False)),
                "pet_victim_guid": int(event.get("pet_victim_guid") or 0),
                "pet_attacking": bool(event.get("pet_attacking", False)),
                "pet_command_state": int(event.get("pet_command_state") or 0),
                "pet_command_attack": bool(event.get("pet_command_attack", False)),
                "pet_current_generic_spell_id": int(
                    event.get("pet_current_generic_spell_id") or 0
                ),
                "pet_current_channeled_spell_id": int(
                    event.get("pet_current_channeled_spell_id") or 0
                ),
                "pet_current_autorepeat_spell_id": int(
                    event.get("pet_current_autorepeat_spell_id") or 0
                ),
                "target_distance": float(event.get("target_distance") or 0.0),
                # Older reports do not carry this observation. Treat absence
                # as unknown/non-death rather than fabricating a dead sample.
                "alive": bool(event.get("alive", True)),
            }
            decision_timeline.append(normalized_event)
        for event in bot.get("off_target_damage_events") or []:
            if not isinstance(event, dict):
                continue
            off_target_damage_events.append(
                {
                    "bot_guid": bot_guid,
                    "elapsed_ms": int(event.get("elapsed_ms") or 0),
                    "attacker_guid": int(event.get("attacker_guid") or 0),
                    "victim_guid": int(event.get("victim_guid") or 0),
                    "victim_entry": int(event.get("victim_entry") or 0),
                    "victim_type_id": int(event.get("victim_type_id") or 0),
                    "victim_is_owner": bool(event.get("victim_is_owner")),
                    "spell_id": int(event.get("spell_id") or 0),
                    "current_generic_spell_id": int(event.get("current_generic_spell_id") or 0),
                    "current_channeled_spell_id": int(event.get("current_channeled_spell_id") or 0),
                    "damage": int(event.get("damage") or 0),
                    "periodic_health_aura_candidates": [
                        {
                            "spell_id": int(candidate.get("spell_id") or 0),
                            "holder_guid": int(candidate.get("holder_guid") or 0),
                            "caster_guid": int(candidate.get("caster_guid") or 0),
                            "effect_index": int(candidate.get("effect_index") or 0),
                            "aura_type": int(candidate.get("aura_type") or 0),
                        }
                        for candidate in event.get("periodic_health_aura_candidates") or []
                        if isinstance(candidate, dict)
                    ],
                }
            )

    decision_timeline.sort(key=lambda event: (event["bot_guid"], event["elapsed_ms"]))
    off_target_damage_events.sort(
        key=lambda event: (event["bot_guid"], event["elapsed_ms"], event["victim_guid"])
    )
    primary_pet_shadow_bite_events.sort(
        key=lambda event: (event["bot_guid"], event["elapsed_ms"])
    )
    for observation in will_of_unbinding_observations:
        observation["stack_transitions"].sort(
            key=lambda event: (
                event["elapsed_ms"],
                event["previous_stacks"],
                event["current_stacks"],
            )
        )
    will_of_unbinding_observations.sort(key=lambda row: row["bot_guid"])
    health_ratios = [
        event["health"] / event["max_health"]
        for event in decision_timeline
        if event["max_health"] > 0
    ]
    first_death = next(
        (event for event in decision_timeline if event["result"] == "dead" or not event["alive"]),
        None,
    )

    return {
        "schema": "rotation_review_runtime_observation_v1",
        "calibration_phase": str(
            calibration.get("phase") or ""
        ) if isinstance(calibration, dict) else "",
        "calibration_complete": calibration_complete,
        "calibration_target_spec": str(
            (calibration or {}).get("target_spec")
            or document.get("target_spec")
            or ""
        ) if isinstance(calibration, dict) else str(document.get("target_spec") or ""),
        "calibration_terminal": {
            "reason": str((calibration or {}).get("failure_reason") or ""),
            "initial_resource_failures": initial_resource_failures,
        }
        if isinstance(calibration, dict) and calibration.get("failure_reason")
        else None,
        "calibration_target_guid": int(
            (calibration or {}).get("target_guid") or document.get("target_guid") or 0
        ) if isinstance(calibration, dict) else int(document.get("target_guid") or 0),
        "decision_timeline_basis": (
            "completed_combat_calibration"
            if calibration_complete
            else "completed_combat_calibration_not_observed"
        ),
        "attempt_counts_by_spell": {str(key): value for key, value in sorted(attempts.items())},
        "damage_by_spell": {str(key): value for key, value in sorted(damage.items())},
        "damage_event_counts_by_spell": {
            str(key): value for key, value in sorted(damage_events.items())
        },
        "primary_pet_damage_by_spell": {
            str(key): value for key, value in sorted(pet_damage.items())
        },
        "primary_pet_damage_event_counts_by_spell": {
            str(key): value for key, value in sorted(pet_damage_events.items())
        },
        "chosen_counts_by_spell": {str(key): value for key, value in sorted(chosen.items())},
        "result_counts": dict(sorted(results.items())),
        "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
        "pipeline_edges": dict(sorted(pipeline_edges.items())),
        "calibration_windows": calibration_windows,
        "gear_identities": gear_identities,
        "scoring_start_stats": scoring_start_stats,
        "pet_execution_observations": pet_execution_observations,
        "consumable_execution_observations": consumable_execution_observations,
        "pre_scoring_blockers": sorted(
            pre_scoring_blockers,
            key=lambda row: (row["bot_guid"], row["reason"]),
        ),
        "decision_timeline": decision_timeline,
        "off_target_damage_events": off_target_damage_events,
        "primary_pet_shadow_bite_events": primary_pet_shadow_bite_events,
        "dragonwrath_copy_proc_observations": dragonwrath_copy_proc_observations,
        "will_of_unbinding_observations": will_of_unbinding_observations,
        "timeline_summary": {
            "sample_count": len(decision_timeline),
            "first_death_elapsed_ms": first_death["elapsed_ms"] if first_death else None,
            "minimum_observed_health_ratio": min(health_ratios) if health_ratios else None,
            "movement_range_events": sum(
                event["result"] == "movement_range" for event in decision_timeline
            ),
            "off_target_event_count": len(off_target_damage_events),
            "off_target_damage": sum(event["damage"] for event in off_target_damage_events),
        },
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


def _metric_per_iteration(rows: Iterable[dict[str, Any]], key: str) -> float:
    return sum(
        float(row.get("per_iteration_target_metric_sums", {}).get(key) or 0.0)
        for row in rows
    )


def _positive_duration(value: Any) -> float | None:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _timeline_spell_evidence(
    timeline: dict[str, Any] | None,
) -> dict[int, dict[str, Any]]:
    """Aggregate first-iteration timeline facts by spell, preserving line order."""
    evidence: dict[int, dict[str, Any]] = {}
    for event in (timeline or {}).get("events") or []:
        if not isinstance(event, dict):
            continue
        identity = event.get("identity") or {}
        spell_id = identity.get("id") if identity.get("kind") == "spell" else None
        if not isinstance(spell_id, int):
            continue
        row = evidence.setdefault(
            spell_id,
            {
                "event_kind_counts": Counter(),
                "line_indices": [],
                "timestamps_seconds": [],
            },
        )
        row["event_kind_counts"][str(event.get("kind") or "other")] += 1
        if isinstance(event.get("line_index"), int):
            row["line_indices"].append(event["line_index"])
        timestamp = event.get("timestamp_seconds")
        if isinstance(timestamp, (int, float)):
            row["timestamps_seconds"].append(float(timestamp))
    normalized: dict[int, dict[str, Any]] = {}
    for spell_id, row in evidence.items():
        timestamps = row["timestamps_seconds"]
        normalized[spell_id] = {
            "event_kind_counts": dict(sorted(row["event_kind_counts"].items())),
            "first_line_index": min(row["line_indices"]) if row["line_indices"] else None,
            "last_line_index": max(row["line_indices"]) if row["line_indices"] else None,
            "first_at_seconds": min(timestamps) if timestamps else None,
            "last_at_seconds": max(timestamps) if timestamps else None,
        }
    return normalized


def _runtime_window_duration(runtime: dict[str, Any]) -> float | None:
    """Return one calibration-window duration for the supplied spec review.

    ``normalize_runtime_report`` intentionally keeps one aggregate action map;
    using the longest window prevents duplicate bot rows from multiplying the
    denominator.  Multi-bot scope is still reported to the reviewer.
    """
    durations = [
        duration
        for duration in (
            _positive_duration(window.get("elapsed_seconds"))
            for window in runtime.get("calibration_windows") or []
            if isinstance(window, dict)
        )
        if duration is not None
    ]
    return max(durations) if durations else None


def _cast_mix_identity_matches_apl(
    identity: dict[str, Any], apl_identities: Iterable[dict[str, Any]]
) -> bool:
    """Match a result ActionID to an APL root while retaining result tags.

    WoWSims emits an omitted APL tag as ``0`` in aggregate metrics/logs, while
    an exported APL commonly represents it as ``None``.  Only that untagged
    equivalence is allowed; nonzero tags must match exactly so generated child
    actions cannot be folded into their parent spell.
    """
    if identity.get("kind") != "spell" or not isinstance(identity.get("id"), int):
        return False
    for apl_identity in apl_identities:
        if (
            apl_identity.get("kind") != identity.get("kind")
            or apl_identity.get("id") != identity.get("id")
        ):
            continue
        apl_tag = apl_identity.get("tag")
        result_tag = identity.get("tag")
        if apl_tag == result_tag or (apl_tag is None and result_tag in (None, 0)):
            return True
    return False


def _stable_cast_mix_float(value: float) -> float:
    """Keep emitted share arithmetic stable across equivalent JSON inputs."""
    return round(float(value), 12)


def _insufficient_cast_mix(
    *, reason: str, basis: dict[str, str], detail: str | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "insufficient_data",
        "reason": reason,
        "basis": basis,
        "share_delta_direction": "trinity_share_minus_wowsims_share",
        "wowsims_total_casts": 0.0,
        "trinity_total_casts": 0,
        "per_spell": [],
        "shared_spell_ids": [],
        "wowsims_only_spell_ids": [],
        "trinity_only_spell_ids": [],
        "cast_mix_overlap": None,
        "total_variation_distance": None,
        "maximum_absolute_share_delta": None,
        "maximum_absolute_share_delta_spell_ids": [],
        "cast_cadence": {
            "status": "insufficient_duration_data",
            "wowsims_duration_seconds": None,
            "trinity_duration_seconds": None,
            "wowsims_casts_per_second": None,
            "trinity_casts_per_second": None,
            "trinity_to_wowsims_cadence_ratio": None,
            "trinity_minus_wowsims_casts_per_second": None,
        },
        "cast_cadence_components": _empty_cast_cadence_components(),
        "cast_cadence_limitations": [
            "The legacy aggregate cadence is unavailable for this input.",
            "Use typed cast_cadence_components when ordinary casts, channels, or special actions matter.",
        ],
        "timeline_reconciliation": {
            "status": "not_evaluated",
            "cast_started_count": 0,
            "counts_by_spell": {},
        },
        "interpretation": (
            "Cast-mix comparison requires APL-matched WoWSims player root spell casts "
            "and successful native actions from a completed calibration decision_timeline."
        ),
    }
    if detail:
        result["detail"] = detail
    return result


def _cast_cadence(
    *,
    wowsims_result: dict[str, Any],
    runtime: dict[str, Any],
    wowsims_casts: float,
    trinity_casts: int,
) -> dict[str, Any]:
    """Report cast throughput without substituting timeline timestamps for durations."""
    wowsims_duration = next(
        (
            duration
            for duration in (
                _positive_duration(wowsims_result.get("first_iteration_duration_seconds")),
                _positive_duration(wowsims_result.get("avg_iteration_duration_seconds")),
            )
            if duration is not None
        ),
        None,
    )
    trinity_duration = _runtime_window_duration(runtime)
    wowsims_rate = (
        _stable_cast_mix_float(wowsims_casts / wowsims_duration)
        if wowsims_duration is not None
        else None
    )
    trinity_rate = (
        _stable_cast_mix_float(trinity_casts / trinity_duration)
        if trinity_duration is not None
        else None
    )
    return {
        "status": (
            "available"
            if wowsims_duration is not None and trinity_duration is not None
            else "insufficient_duration_data"
        ),
        "wowsims_duration_seconds": wowsims_duration,
        "trinity_duration_seconds": trinity_duration,
        "wowsims_casts_per_second": wowsims_rate,
        "trinity_casts_per_second": trinity_rate,
        "trinity_to_wowsims_cadence_ratio": (
            _stable_cast_mix_float(trinity_rate / wowsims_rate)
            if wowsims_rate is not None and trinity_rate is not None and wowsims_rate > 0
            else None
        ),
        "trinity_minus_wowsims_casts_per_second": (
            _stable_cast_mix_float(trinity_rate - wowsims_rate)
            if wowsims_rate is not None and trinity_rate is not None
            else None
        ),
    }


def _cadence_component(
    *,
    wowsims_count: float | None,
    trinity_count: int | None,
    wowsims_duration: float | None,
    trinity_duration: float | None,
    wowsims_count_label: str,
    trinity_count_label: str,
) -> dict[str, Any]:
    """Describe one comparable event stream without renaming its evidence.

    A channel start and a channel damage event are different observations.  The
    labels are therefore carried in the component rather than silently calling
    every event a ``cast`` or a ``tick``.
    """
    wowsims_rate = (
        _stable_cast_mix_float(wowsims_count / wowsims_duration)
        if wowsims_count is not None and wowsims_duration is not None
        else None
    )
    trinity_rate = (
        _stable_cast_mix_float(trinity_count / trinity_duration)
        if trinity_count is not None and trinity_duration is not None
        else None
    )
    if wowsims_count is None:
        status = "wowsims_observation_unavailable"
    elif trinity_count is None:
        status = "trinity_observation_unavailable"
    elif wowsims_duration is None or trinity_duration is None:
        status = "insufficient_duration_data"
    else:
        status = "available"
    return {
        "status": status,
        "wowsims_count_label": wowsims_count_label,
        "trinity_count_label": trinity_count_label,
        "wowsims_count": (
            _stable_cast_mix_float(wowsims_count) if wowsims_count is not None else None
        ),
        "trinity_count": trinity_count,
        "wowsims_duration_seconds": wowsims_duration,
        "trinity_duration_seconds": trinity_duration,
        "wowsims_per_second": wowsims_rate,
        "trinity_per_second": trinity_rate,
        "trinity_to_wowsims_ratio": (
            _stable_cast_mix_float(trinity_rate / wowsims_rate)
            if wowsims_rate is not None and trinity_rate is not None and wowsims_rate > 0
            else None
        ),
        "trinity_minus_wowsims_per_second": (
            _stable_cast_mix_float(trinity_rate - wowsims_rate)
            if wowsims_rate is not None and trinity_rate is not None
            else None
        ),
    }


def _empty_cast_cadence_components() -> dict[str, Any]:
    """Return the typed cadence shape when a cast mix cannot be computed."""
    unavailable = _cadence_component(
        wowsims_count=None,
        trinity_count=None,
        wowsims_duration=None,
        trinity_duration=None,
        wowsims_count_label="unavailable",
        trinity_count_label="unavailable",
    )
    return {
        "status": "insufficient_data",
        "ordinary_cast_starts": unavailable,
        "channel_starts": unavailable,
        "channel_landed_events": unavailable,
        "channel_ticks": unavailable,
        "classification": {
            "ordinary_cast_spell_ids": [],
            "channel_spell_ids": [],
            "ambiguous_spell_ids": [],
            "non_comparable_apl_action_kinds": [],
        },
        "non_comparable_actions": {
            "status": "not_evaluated",
            "used_for_cadence": False,
            "apl_action_kinds": [],
            "apl_action_count": 0,
            "reason": "cast mix was not available",
        },
        "interpretation": (
            "Typed cadence components are unavailable; do not infer ordinary casts, "
            "channel uptime, or special-action equivalence from the aggregate field."
        ),
    }


def _cast_cadence_components(
    *,
    wowsims: dict[str, Any],
    wowsims_result: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Separate ordinary starts, channel starts/events, and special actions.

    The old aggregate cadence remains useful as a coarse scheduler signal, but
    it is not an ordinary-cast rate when a channel is present.  Only exact APL
    root identities are counted here; IDs appearing as both cast and channel
    roots are excluded from both streams instead of being guessed.  WoWSims
    channel landed events are the sum of noncritical ``ticks`` and critical
    ``critTicks`` metrics.
    """
    combat_rows = [row for row in wowsims.get("actions") or [] if row.get("phase") == "combat"]
    ordinary_rows = [row for row in combat_rows if row.get("action_kind") == "castSpell"]
    channel_rows = [row for row in combat_rows if row.get("action_kind") == "channelSpell"]
    special_rows = [
        row
        for row in combat_rows
        if row.get("action_kind") not in {"castSpell", "channelSpell"}
    ]

    ordinary_ids = {
        int(row["identity"]["id"])
        for row in ordinary_rows
        if (row.get("identity") or {}).get("kind") == "spell"
        and isinstance((row.get("identity") or {}).get("id"), int)
    }
    channel_ids = {
        int(row["identity"]["id"])
        for row in channel_rows
        if (row.get("identity") or {}).get("kind") == "spell"
        and isinstance((row.get("identity") or {}).get("id"), int)
    }
    ambiguous_ids = ordinary_ids & channel_ids
    ordinary_ids -= ambiguous_ids
    channel_ids -= ambiguous_ids

    ordinary_counts: Counter[int] = Counter()
    channel_counts: Counter[int] = Counter()
    channel_landed_event_counts: Counter[int] = Counter()
    channel_ticks: Counter[int] = Counter()
    channel_crit_ticks: Counter[int] = Counter()
    for row in wowsims_result.get("action_metrics") or []:
        if not isinstance(row, dict):
            continue
        if (row.get("source") or {}).get("kind") != "player" or bool(row.get("is_passive")):
            continue
        identity = row.get("identity") or {}
        spell_id = identity.get("id")
        if not isinstance(spell_id, int):
            continue
        casts = float((row.get("per_iteration_target_metric_sums") or {}).get("casts") or 0.0)
        ticks = float((row.get("per_iteration_target_metric_sums") or {}).get("ticks") or 0.0)
        crit_ticks = float(
            (row.get("per_iteration_target_metric_sums") or {}).get("crit_ticks") or 0.0
        )
        if spell_id in ordinary_ids and casts > 0 and _cast_mix_identity_matches_apl(
            identity,
            [item["identity"] for item in ordinary_rows],
        ):
            ordinary_counts[spell_id] += casts
        if (
            spell_id in channel_ids
            and (casts > 0 or ticks > 0 or crit_ticks > 0)
            and _cast_mix_identity_matches_apl(
                identity,
                [item["identity"] for item in channel_rows],
            )
        ):
            channel_counts[spell_id] += casts
            channel_ticks[spell_id] += ticks
            channel_crit_ticks[spell_id] += crit_ticks
            channel_landed_event_counts[spell_id] += ticks + crit_ticks

    trinity_ordinary: Counter[int] = Counter()
    trinity_channels: Counter[int] = Counter()
    for event in runtime.get("decision_timeline") or []:
        if not isinstance(event, dict) or str(event.get("result") or "") != "ok":
            continue
        spell_id = int(event.get("spell_id") or 0)
        if spell_id in ordinary_ids:
            trinity_ordinary[spell_id] += 1
        elif spell_id in channel_ids:
            trinity_channels[spell_id] += 1

    event_counts = runtime.get("damage_event_counts_by_spell") or {}
    trinity_channel_events: Counter[int] = Counter()
    event_counts_available = False
    for spell_id in channel_ids:
        raw_count = event_counts.get(str(spell_id), event_counts.get(spell_id))
        if raw_count is None:
            continue
        event_counts_available = True
        trinity_channel_events[spell_id] += int(raw_count or 0)

    wowsims_duration = next(
        (
            duration
            for duration in (
                _positive_duration(wowsims_result.get("first_iteration_duration_seconds")),
                _positive_duration(wowsims_result.get("avg_iteration_duration_seconds")),
            )
            if duration is not None
        ),
        None,
    )
    trinity_duration = _runtime_window_duration(runtime)
    ordinary_wowsims = sum(ordinary_counts.values())
    channel_wowsims = sum(channel_counts.values())
    channel_wowsims_landed_events = sum(channel_landed_event_counts.values())
    ordinary_trinity = sum(trinity_ordinary.values())
    channel_trinity = sum(trinity_channels.values())
    channel_trinity_events = sum(trinity_channel_events.values()) if event_counts_available else None

    channel_landed_events = _cadence_component(
        wowsims_count=channel_wowsims_landed_events,
        trinity_count=channel_trinity_events,
        wowsims_duration=wowsims_duration,
        trinity_duration=trinity_duration,
        wowsims_count_label="aggregate_per_iteration_channel_landed_events_ticks_plus_crit_ticks",
        trinity_count_label="runtime_spell_damage_event_count_not_proven_tick_equivalent",
    ) | {
        "wowsims_counts_by_spell": {
            str(spell_id): _stable_cast_mix_float(count)
            for spell_id, count in sorted(channel_landed_event_counts.items())
        },
        "wowsims_ticks_by_spell": {
            str(spell_id): _stable_cast_mix_float(count)
            for spell_id, count in sorted(channel_ticks.items())
        },
        "wowsims_crit_ticks_by_spell": {
            str(spell_id): _stable_cast_mix_float(count)
            for spell_id, count in sorted(channel_crit_ticks.items())
        },
        "trinity_counts_by_spell": {
            str(spell_id): int(count)
            for spell_id, count in sorted(trinity_channel_events.items())
        },
        "trinity_event_count_observed": event_counts_available,
    }

    return {
        "status": "available",
        "ordinary_cast_starts": _cadence_component(
            wowsims_count=ordinary_wowsims,
            trinity_count=ordinary_trinity,
            wowsims_duration=wowsims_duration,
            trinity_duration=trinity_duration,
            wowsims_count_label="aggregate_per_iteration_castSpell_root_starts",
            trinity_count_label="successful_decision_timeline_castSpell_root_starts",
        ) | {
            "wowsims_counts_by_spell": {
                str(spell_id): _stable_cast_mix_float(count)
                for spell_id, count in sorted(ordinary_counts.items())
            },
            "trinity_counts_by_spell": {
                str(spell_id): int(count) for spell_id, count in sorted(trinity_ordinary.items())
            },
        },
        "channel_starts": _cadence_component(
            wowsims_count=channel_wowsims,
            trinity_count=channel_trinity,
            wowsims_duration=wowsims_duration,
            trinity_duration=trinity_duration,
            wowsims_count_label="aggregate_per_iteration_channelSpell_root_starts",
            trinity_count_label="successful_decision_timeline_channelSpell_root_starts",
        ) | {
            "wowsims_counts_by_spell": {
                str(spell_id): _stable_cast_mix_float(count)
                for spell_id, count in sorted(channel_counts.items())
            },
            "trinity_counts_by_spell": {
                str(spell_id): int(count) for spell_id, count in sorted(trinity_channels.items())
            },
        },
        "channel_landed_events": channel_landed_events,
        "channel_ticks": channel_landed_events,
        "classification": {
            "ordinary_cast_spell_ids": sorted(ordinary_ids),
            "channel_spell_ids": sorted(channel_ids),
            "ambiguous_spell_ids": sorted(ambiguous_ids),
            "non_comparable_apl_action_kinds": sorted(
                {str(row.get("action_kind") or "unknown") for row in special_rows}
            ),
        },
        "non_comparable_actions": {
            "status": "excluded_from_cadence",
            "used_for_cadence": False,
            "apl_action_kinds": sorted(
                {str(row.get("action_kind") or "unknown") for row in special_rows}
            ),
            "apl_action_count": len(special_rows),
            "apl_paths": sorted(str(row.get("path") or "") for row in special_rows),
            "reason": (
                "WoWSims special/off-GCD/structural actions have no native cast-start "
                "or landed-event identity in this comparison."
            ),
        },
        "interpretation": (
            "Ordinary cast starts and channel starts are separate streams. Channel landed "
            "events (WoWSims ticks plus critical ticks) are reported beside starts; runtime "
            "spell-damage event counts are not declared tick-equivalent, and special/off-GCD "
            "actions remain excluded."
        ),
    }


def compare_cast_mix(
    wowsims: dict[str, Any] | None,
    wowsims_result: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare WoWSims player-root cast shares with Trinity native successes.

    WoWSims counts come only from aggregate per-iteration action metrics.  The
    first-iteration ``cast_started`` log is retained as reconciliation evidence
    and never contributes to either share vector.  Trinity counts come only
    from successful, nonzero-spell entries in a completed calibration timeline;
    action-attempt aggregates are intentionally not a fallback.
    """
    basis = {
        "wowsims_counts": "aggregate_per_iteration_player_root_spell_casts_matching_combat_apl",
        "wowsims_timeline": "first_iteration_cast_started_reconciliation_only",
        "trinity_counts": "completed_calibration_decision_timeline_result_ok_nonzero_spell_id",
        "action_attempts": "excluded_from_cast_mix",
    }
    if not wowsims:
        return _insufficient_cast_mix(
            reason="missing_combat_apl", basis=basis, detail="normalized WoWSims APL is absent"
        )
    if not wowsims_result:
        return _insufficient_cast_mix(
            reason="missing_wowsims_result",
            basis=basis,
            detail="normalized WoWSims result is absent",
        )
    if not runtime:
        return _insufficient_cast_mix(
            reason="missing_runtime_report",
            basis=basis,
            detail="normalized Trinity runtime report is absent",
        )

    apl_identities = [
        row["identity"]
        for row in wowsims.get("actions") or []
        if row.get("phase") == "combat"
        and (row.get("identity") or {}).get("kind") == "spell"
        and isinstance((row.get("identity") or {}).get("id"), int)
    ]
    if not apl_identities:
        return _insufficient_cast_mix(
            reason="missing_combat_apl_spell_identities",
            basis=basis,
            detail="combat APL contains no spell identities",
        )

    # Aggregate by spell ID for the comparison while retaining every exact
    # WoWSims identity (including tag) in the emitted row metadata.
    wowsims_counts: Counter[int] = Counter()
    wowsims_identities: dict[int, list[dict[str, Any]]] = {}
    for row in wowsims_result.get("action_metrics") or []:
        if not isinstance(row, dict):
            continue
        identity = row.get("identity") or {}
        source = row.get("source") or {}
        if source.get("kind") != "player":
            continue
        if bool(row.get("is_passive")):
            continue
        if not _cast_mix_identity_matches_apl(identity, apl_identities):
            continue
        casts = float((row.get("per_iteration_target_metric_sums") or {}).get("casts") or 0.0)
        if casts <= 0:
            continue
        spell_id = int(identity["id"])
        wowsims_counts[spell_id] += casts
        wowsims_identities.setdefault(spell_id, []).append(
            {
                "kind": identity.get("kind"),
                "id": spell_id,
                "tag": identity.get("tag"),
            }
        )

    wowsims_total = sum(wowsims_counts.values())
    if wowsims_total <= 0:
        return _insufficient_cast_mix(
            reason="missing_apl_matched_wowsims_casts",
            basis=basis,
            detail="no positive aggregate player-root casts matched combat APL identities",
        )

    if not bool(runtime.get("calibration_complete")):
        return _insufficient_cast_mix(
            reason="completed_calibration_missing",
            basis=basis,
            detail="runtime decision_timeline is not bound to a completed calibration window",
        )

    trinity_counts: Counter[int] = Counter()
    for event in runtime.get("decision_timeline") or []:
        if not isinstance(event, dict):
            continue
        spell_id = int(event.get("spell_id") or 0)
        if str(event.get("result") or "") == "ok" and spell_id:
            trinity_counts[spell_id] += 1
    trinity_total = sum(trinity_counts.values())
    if trinity_total <= 0:
        return _insufficient_cast_mix(
            reason="missing_successful_trinity_timeline",
            basis=basis,
            detail="completed calibration has no successful nonzero-spell decision_timeline entries",
        )

    spell_ids = sorted(set(wowsims_counts) | set(trinity_counts))
    rows: list[dict[str, Any]] = []
    wowsims_shares: dict[int, float] = {}
    trinity_shares: dict[int, float] = {}
    for spell_id in spell_ids:
        wowsims_count = _stable_cast_mix_float(wowsims_counts.get(spell_id, 0.0))
        trinity_count = int(trinity_counts.get(spell_id, 0))
        wowsims_share = _stable_cast_mix_float(wowsims_count / wowsims_total)
        trinity_share = _stable_cast_mix_float(trinity_count / trinity_total)
        delta = _stable_cast_mix_float(trinity_share - wowsims_share)
        absolute_delta = _stable_cast_mix_float(abs(delta))
        wowsims_shares[spell_id] = wowsims_share
        trinity_shares[spell_id] = trinity_share
        identities = sorted(
            wowsims_identities.get(spell_id, []),
            key=lambda identity: (
                identity.get("kind") or "",
                int(identity.get("id") or 0),
                -1 if identity.get("tag") is None else int(identity["tag"]),
            ),
        )
        rows.append(
            {
                "spell_id": spell_id,
                "identity": identities[0]
                if len(identities) == 1
                else {"kind": "spell", "id": spell_id, "tag": None},
                "wowsims_identities": identities,
                "trinity_identity": {"kind": "spell", "id": spell_id, "tag": None},
                "wowsims_count": wowsims_count,
                "wowsims_share": wowsims_share,
                "trinity_count": trinity_count,
                "trinity_share": trinity_share,
                "share_delta_direction": "trinity_share_minus_wowsims_share",
                "share_delta_percentage_points": _stable_cast_mix_float(delta * 100.0),
                "absolute_delta": absolute_delta,
                "absolute_delta_percentage_points": _stable_cast_mix_float(
                    absolute_delta * 100.0
                ),
            }
        )

    timeline_counts: Counter[int] = Counter()
    timeline_line_indices: dict[int, list[int]] = {}
    timeline = wowsims_result.get("timeline") or {}
    for event in timeline.get("events") or []:
        if not isinstance(event, dict) or event.get("kind") != "cast_started":
            continue
        source_entity = event.get("source_entity")
        if isinstance(source_entity, str) and " - " in source_entity:
            continue
        identity = event.get("identity") or {}
        if not _cast_mix_identity_matches_apl(identity, apl_identities):
            continue
        spell_id = int(identity["id"])
        timeline_counts[spell_id] += 1
        line_index = event.get("line_index")
        if isinstance(line_index, int):
            timeline_line_indices.setdefault(spell_id, []).append(line_index)
    timeline_reconciliation = {
        "status": "available" if timeline_counts else "absent_or_no_matching_cast_started",
        "cast_started_count": sum(timeline_counts.values()),
        "counts_by_spell": {
            str(spell_id): int(count) for spell_id, count in sorted(timeline_counts.items())
        },
        "line_indices_by_spell": {
            str(spell_id): sorted(indices)
            for spell_id, indices in sorted(timeline_line_indices.items())
        },
        "used_for_share_vectors": False,
    }

    shared = sorted(set(wowsims_counts) & set(trinity_counts))
    wowsims_only = sorted(set(wowsims_counts) - set(trinity_counts))
    trinity_only = sorted(set(trinity_counts) - set(wowsims_counts))
    deltas = {
        spell_id: _stable_cast_mix_float(trinity_shares.get(spell_id, 0.0) - wowsims_shares.get(spell_id, 0.0))
        for spell_id in spell_ids
    }
    overlap = _stable_cast_mix_float(
        sum(
            min(wowsims_shares.get(spell_id, 0.0), trinity_shares.get(spell_id, 0.0))
            for spell_id in spell_ids
        )
    )
    total_variation = _stable_cast_mix_float(0.5 * sum(abs(delta) for delta in deltas.values()))
    maximum_delta = _stable_cast_mix_float(max((abs(delta) for delta in deltas.values()), default=0.0))
    maximum_delta_spell_ids = sorted(
        spell_id for spell_id, delta in deltas.items() if abs(delta) == maximum_delta
    )
    cadence_components = _cast_cadence_components(
        wowsims=wowsims,
        wowsims_result=wowsims_result,
        runtime=runtime,
    )
    return {
        "status": "ok",
        "basis": basis,
        "share_delta_direction": "trinity_share_minus_wowsims_share",
        "wowsims_total_casts": _stable_cast_mix_float(wowsims_total),
        "trinity_total_casts": int(trinity_total),
        "per_spell": rows,
        "shared_spell_ids": shared,
        "wowsims_only_spell_ids": wowsims_only,
        "trinity_only_spell_ids": trinity_only,
        "cast_mix_overlap": overlap,
        "total_variation_distance": total_variation,
        "maximum_absolute_share_delta": maximum_delta,
        "maximum_absolute_share_delta_spell_ids": maximum_delta_spell_ids,
        "cast_cadence": _cast_cadence(
            wowsims_result=wowsims_result,
            runtime=runtime,
            wowsims_casts=wowsims_total,
            trinity_casts=trinity_total,
        ),
        "cast_cadence_components": cadence_components,
        "cast_cadence_limitations": [
            "The legacy aggregate cadence combines ordinary castSpell starts and channelSpell starts.",
            "Channel starts are not channel ticks or uptime; inspect cast_cadence_components.",
            "Special, off-GCD, pet, passive, and tagged child actions are excluded when they lack an exact root event stream.",
        ],
        "timeline_reconciliation": timeline_reconciliation,
        "interpretation": (
            "This measures action-mix alignment from attributable cast counts; it is not "
            "damage equivalence or semantic equivalence."
        ),
    }


def compare_simulated_to_trinity_runtime(
    wowsims_result: dict[str, Any],
    runtime: dict[str, Any],
    *,
    wowsims: dict[str, Any] | None = None,
    trinity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Link sim aggregates and first-iteration events to native runtime facts.

    The ``rough_dps_impact`` block is intentionally an attribution aid.  It
    estimates action-level throughput using WoWSims damage-per-cast and the
    observed native cadence; it is not a semantic-equivalence claim or a
    denominator-derived tuning instruction.
    """
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
    apl_rows_by_spell: dict[int, list[dict[str, Any]]] = {}
    for row in (wowsims or {}).get("actions") or []:
        identity = row.get("identity") or {}
        spell_id = identity.get("id") if identity.get("kind") == "spell" else None
        if isinstance(spell_id, int):
            apl_rows_by_spell.setdefault(spell_id, []).append(row)
    trinity_rows_by_spell: dict[int, list[dict[str, Any]]] = {}
    for row in (trinity or {}).get("actions") or []:
        identity = row.get("identity") or {}
        spell_id = identity.get("id") if identity.get("kind") == "spell" else None
        if isinstance(spell_id, int):
            trinity_rows_by_spell.setdefault(spell_id, []).append(row)

    sim_duration = next(
        (
            duration
            for duration in (
                _positive_duration(wowsims_result.get("first_iteration_duration_seconds")),
                _positive_duration(wowsims_result.get("avg_iteration_duration_seconds")),
            )
            if duration is not None
        ),
        None,
    )
    runtime_duration = _runtime_window_duration(runtime)
    timeline_evidence = _timeline_spell_evidence(wowsims_result.get("timeline"))
    rough_impacts: list[dict[str, Any]] = []
    mismatch_counts: Counter[str] = Counter()
    links = []
    for spell_id in sorted(
        sim_spells
        | trinity_spells
        | set(apl_rows_by_spell)
        | set(trinity_attempts)
        | set(trinity_damage)
    ):
        apl_rows = apl_rows_by_spell.get(spell_id, [])
        profile_rows = trinity_rows_by_spell.get(spell_id, [])
        sim_action_rows = sim_rows.get(spell_id, [])
        sim_casts = _metric_per_iteration(sim_action_rows, "casts")
        sim_damage = _metric_per_iteration(sim_action_rows, "damage")
        runtime_attempt_count = int(trinity_attempts.get(spell_id, 0) or 0)
        runtime_landed_damage = int(trinity_damage.get(spell_id, 0) or 0)
        sim_damage_per_cast = sim_damage / sim_casts if sim_casts > 0 else None
        sim_dps = sim_damage / sim_duration if sim_duration else None
        runtime_dps = (
            runtime_landed_damage / runtime_duration if runtime_duration else None
        )
        expected_runtime_damage = (
            sim_damage_per_cast * runtime_attempt_count
            if sim_damage_per_cast is not None
            else None
        )
        projected_runtime_cadence_dps = (
            expected_runtime_damage / runtime_duration
            if expected_runtime_damage is not None and runtime_duration
            else None
        )
        sim_rate = sim_casts / sim_duration if sim_duration else None
        runtime_rate = (
            runtime_attempt_count / runtime_duration if runtime_duration else None
        )
        cadence_dps_loss = (
            (sim_rate - runtime_rate) * sim_damage_per_cast
            if sim_rate is not None and runtime_rate is not None and sim_damage_per_cast is not None
            else None
        )
        damage_model_dps_delta = (
            projected_runtime_cadence_dps - runtime_dps
            if projected_runtime_cadence_dps is not None and runtime_dps is not None
            else None
        )
        sim_minus_runtime_dps = (
            sim_dps - runtime_dps
            if sim_dps is not None and runtime_dps is not None
            else None
        )
        reasons: list[str] = []
        sim_observed = sim_casts > 0 or abs(sim_damage) > 0
        runtime_observed = runtime_attempt_count > 0 or runtime_landed_damage > 0
        if apl_rows and not sim_observed:
            reasons.append("apl_action_not_observed_in_wowsims_result")
        if sim_observed and not apl_rows:
            reasons.append("simulated_action_absent_from_apl")
        if profile_rows and not runtime_observed:
            reasons.append("profile_action_not_observed_in_runtime")
        if runtime_observed and not profile_rows:
            reasons.append("runtime_action_absent_from_profile")
        if sim_casts > 0 and runtime_attempt_count == 0:
            reasons.append("sim_action_missing_at_runtime")
        elif sim_casts == 0 and runtime_attempt_count > 0:
            reasons.append("runtime_action_not_observed_in_wowsims")
        if cadence_dps_loss is not None:
            if cadence_dps_loss > 1e-9:
                reasons.append("runtime_cadence_below_wowsims")
            elif cadence_dps_loss < -1e-9:
                reasons.append("runtime_cadence_above_wowsims")
        if damage_model_dps_delta is not None and damage_model_dps_delta > 1e-9:
            reasons.append("runtime_damage_below_wowsims_per_cast_model")
        for reason in reasons:
            mismatch_counts[reason] += 1
        timeline = timeline_evidence.get(
            spell_id,
            {
                "event_kind_counts": {},
                "first_line_index": None,
                "last_line_index": None,
                "first_at_seconds": None,
                "last_at_seconds": None,
            },
        )
        rough_impacts.append(
            {
                "spell_id": spell_id,
                "apl_paths": sorted({str(row["path"]) for row in apl_rows}),
                "apl_condition_families": sorted(
                    {
                        family
                        for row in apl_rows
                        for family in row.get("condition_families") or []
                    }
                ),
                "trinity_profile_actions": [
                    {
                        "priority_bucket": row.get("priority_bucket"),
                        "sort_order": row.get("sort_order"),
                        "category": row.get("category"),
                        "gate_families": row.get("gate_families") or [],
                        "movement_directive": row.get("movement_directive"),
                        "gates": row.get("gates") or {},
                    }
                    for row in profile_rows
                ],
                "wowsims_timeline": timeline,
                "wowsims_per_iteration_casts": sim_casts,
                "wowsims_per_iteration_damage": sim_damage,
                "wowsims_damage_per_cast": sim_damage_per_cast,
                "wowsims_dps_contribution": sim_dps,
                "trinity_attempt_count": runtime_attempt_count,
                "trinity_landed_damage": runtime_landed_damage,
                "trinity_dps_contribution": runtime_dps,
                "expected_damage_at_trinity_cadence": expected_runtime_damage,
                "projected_dps_at_trinity_cadence": projected_runtime_cadence_dps,
                "rough_cadence_dps_loss": cadence_dps_loss,
                "rough_damage_model_dps_delta": damage_model_dps_delta,
                "rough_dps_delta_sim_minus_runtime": sim_minus_runtime_dps,
                "mismatch_reasons": reasons,
            }
        )
        links.append(
            {
                "spell_id": spell_id,
                "wowsims_action_metrics": sim_rows.get(spell_id, []),
                "trinity_attempt_count": trinity_attempts.get(spell_id, 0),
                "trinity_landed_damage": trinity_damage.get(spell_id, 0),
            }
        )
    sim_action_dps = [
        row["wowsims_dps_contribution"]
        for row in rough_impacts
        if isinstance(row["wowsims_dps_contribution"], (int, float))
    ]
    runtime_action_dps = [
        row["trinity_dps_contribution"]
        for row in rough_impacts
        if isinstance(row["trinity_dps_contribution"], (int, float))
    ]
    action_dps_deltas = [
        row["rough_dps_delta_sim_minus_runtime"]
        for row in rough_impacts
        if isinstance(row["rough_dps_delta_sim_minus_runtime"], (int, float))
    ]
    cadence_dps_losses = [
        row["rough_cadence_dps_loss"]
        for row in rough_impacts
        if isinstance(row["rough_cadence_dps_loss"], (int, float))
    ]
    return {
        "spec_identity": _spec_identity(trinity),
        "cast_mix": compare_cast_mix(wowsims, wowsims_result, runtime),
        "shared_observed_spell_ids": sorted(sim_spells & trinity_spells),
        "wowsims_only_observed_spell_ids": sorted(sim_spells - trinity_spells),
        "trinity_only_observed_spell_ids": sorted(trinity_spells - sim_spells),
        "action_links": links,
        "rough_dps_impact": {
            "status": (
                "estimated"
                if sim_duration is not None and runtime_duration is not None
                else "insufficient_duration_data"
            ),
            "spec_identity": _spec_identity(trinity),
            "wowsims_duration_seconds": sim_duration,
            "trinity_runtime_duration_seconds": runtime_duration,
            "trinity_runtime_window_count": len(runtime.get("calibration_windows") or []),
            "wowsims_total_action_dps": sum(sim_action_dps) if sim_action_dps else None,
            "trinity_total_action_dps": sum(runtime_action_dps) if runtime_action_dps else None,
            "rough_total_dps_delta_sim_minus_runtime": (
                sum(sim_action_dps) - sum(runtime_action_dps)
                if sim_action_dps and runtime_action_dps
                else None
            ),
            "rough_positive_action_shortfall_dps": (
                sum(delta for delta in action_dps_deltas if delta > 0)
                if action_dps_deltas
                else None
            ),
            "rough_positive_cadence_loss_dps": (
                sum(loss for loss in cadence_dps_losses if loss > 0)
                if cadence_dps_losses
                else None
            ),
            "mismatch_counts": dict(sorted(mismatch_counts.items())),
            "action_impacts": rough_impacts,
            "interpretation": (
                "Action-level arithmetic only: WoWSims damage-per-cast is applied to the "
                "observed Trinity attempt cadence. Buff, target, proc, periodic, pet, and "
                "setup differences can overlap, so these are review leads rather than a "
                "tuning denominator or semantic-equivalence claim."
            ),
        },
        "interpretation": (
            "WoWSims values are per-iteration aggregates while Trinity values describe the "
            "supplied native run. Compare action presence, cadence, resource/aura timing, and "
            "failure edges only after encounter/setup identities are compatible."
        ),
    }


def _stat_check(
    name: str,
    expected: Any,
    observed: Any,
    *,
    absolute_tolerance: float,
    relative_tolerance: float = 0.0,
    allow_favorable_above: bool = False,
) -> dict[str, Any]:
    try:
        expected_value = float(expected)
        observed_value = float(observed)
    except (TypeError, ValueError):
        return {
            "stat": name,
            "status": "missing",
            "expected": expected,
            "observed": observed,
            "absolute_tolerance": absolute_tolerance,
            "relative_tolerance": relative_tolerance,
        }
    delta = observed_value - expected_value
    allowed = max(absolute_tolerance, abs(expected_value) * relative_tolerance)
    within_tolerance = abs(delta) <= allowed
    favorable = allow_favorable_above and delta > allowed
    return {
        "stat": name,
        "status": "favorable" if favorable else "match" if within_tolerance else "mismatch",
        "expected": expected_value,
        "observed": observed_value,
        "delta": delta,
        "absolute_delta": abs(delta),
        "allowed_delta": allowed,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "allow_favorable_above": allow_favorable_above,
    }


def compare_gear_identity(
    wowsims_gear: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
) -> dict[str, Any]:
    if not wowsims_gear:
        return {
            "status": "insufficient_data",
            "reason": "missing_wowsims_request_gear",
            "first_broken_edge": "wowsims_request_gear_identity",
        }
    if not runtime:
        return {
            "status": "insufficient_data",
            "reason": "missing_trinity_runtime",
            "first_broken_edge": "trinity_runtime_gear_observation",
        }
    target_guid = int(runtime.get("calibration_target_guid") or 0)
    candidates = [
        row
        for row in runtime.get("gear_identities") or []
        if isinstance(row, dict)
        and (not target_guid or int(row.get("bot_guid") or 0) == target_guid)
    ]
    if not candidates:
        return {
            "status": "insufficient_data",
            "reason": "missing_trinity_scoring_window_gear",
            "first_broken_edge": "trinity_scoring_window_gear_observation",
            "wowsims_manifest_sha256": wowsims_gear.get("manifest_sha256"),
        }
    observed = candidates[0]
    expected_manifest = wowsims_gear.get("manifest") or []
    observed_manifest = observed.get("manifest") or []
    if len(expected_manifest) < 16 or len(observed_manifest) < 16:
        return {
            "status": "insufficient_data",
            "reason": "incomplete_equipment_manifest",
            "first_broken_edge": "complete_gear_identity_before_stat_comparison",
            "wowsims_manifest_sha256": wowsims_gear.get("manifest_sha256"),
            "trinity_manifest_sha256": observed.get("manifest_sha256"),
            "wowsims_item_count": len(expected_manifest),
            "trinity_item_count": len(observed_manifest),
        }
    return {
        "status": "match" if expected_manifest == observed_manifest else "mismatch",
        "wowsims_manifest_sha256": wowsims_gear.get("manifest_sha256"),
        "trinity_manifest_sha256": observed.get("manifest_sha256"),
        "wowsims_item_count": len(expected_manifest),
        "trinity_item_count": len(observed_manifest),
        "first_broken_edge": (
            None
            if expected_manifest == observed_manifest
            else "gear_identity_before_effective_stat_application"
        ),
    }


def compare_consumable_execution(
    wowsims_consumables: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
) -> dict[str, Any]:
    if not wowsims_consumables:
        return {
            "status": "not_applicable",
            "reason": "wowsims_request_has_no_consumable_contract",
        }
    if not runtime:
        return {
            "status": "insufficient_data",
            "reason": "missing_trinity_runtime",
            "first_broken_edge": "consumable_runtime_observation",
        }
    target_guid = int(runtime.get("calibration_target_guid") or 0)
    observations = [
        row
        for row in runtime.get("consumable_execution_observations") or []
        if isinstance(row, dict)
        and (not target_guid or int(row.get("bot_guid") or 0) == target_guid)
    ]
    if not observations:
        return {
            "status": "insufficient_data",
            "reason": "missing_consumable_execution_observation",
            "first_broken_edge": "consumable_runtime_observation",
        }
    observed = observations[0]
    inventory_backed = observed.get("inventory_backed") is True
    checks: list[dict[str, Any]] = []
    first_broken_edge: str | None = None
    missing = False
    mismatch = False
    target_spec = str(runtime.get("calibration_target_spec") or "")
    for kind in ("flask", "food", "prepot", "combat_potion"):
        expected_item = int(
            ((wowsims_consumables.get(kind) or {}).get("item_id")) or 0
        )
        observed_kind = observed.get(kind) or {}
        observed_item = int(observed_kind.get("item_id") or 0)
        use_count = observed_kind.get("native_use_count")
        inventory_before = observed_kind.get("inventory_count_before")
        inventory_after = observed_kind.get("inventory_count_after")
        aura_observed = observed_kind.get("expected_aura_observed")
        if expected_item == 0:
            status = (
                "match"
                if observed_item == 0 and int(use_count or 0) == 0
                else "mismatch"
            )
        elif not inventory_backed or observed_item != expected_item:
            status = "mismatch"
            first_broken_edge = first_broken_edge or f"consumable_inventory_{kind}"
        elif use_count is None or inventory_before is None or inventory_after is None:
            status = "missing"
            first_broken_edge = first_broken_edge or f"{kind}_inventory_receipt"
        elif int(use_count) != 1 or int(inventory_after) >= int(inventory_before):
            status = "mismatch"
            first_broken_edge = first_broken_edge or f"{kind}_native_execution"
        elif aura_observed is not True:
            status = "missing" if aura_observed is None else "mismatch"
            first_broken_edge = first_broken_edge or f"{kind}_aura_outcome"
        else:
            status = "match"
        mismatch = mismatch or status == "mismatch"
        missing = missing or status == "missing"
        checks.append(
            {
                "kind": kind,
                "status": status,
                "expected_item_id": expected_item,
                "observed_item_id": observed_item,
                "native_use_count": use_count,
                "inventory_count_before": inventory_before,
                "inventory_count_after": inventory_after,
                "expected_aura_observed": aura_observed,
            }
        )
    if target_spec == "affliction_warlock" and int(
        ((wowsims_consumables.get("combat_potion") or {}).get("item_id")) or 0
    ) > 0:
        combat_potion = observed.get("combat_potion") or {}
        timing = combat_potion.get("timing_gate")
        timing_status = "match"
        timing_reason: str | None = None
        if not isinstance(timing, Mapping):
            timing_status = "missing"
            timing_reason = "combat_potion_timing_gate_observation"
        else:
            policy = str(timing.get("policy") or "")
            scoring_started = int(timing.get("scoring_started_at_ms") or 0)
            submitted_at = int(combat_potion.get("submitted_at_ms") or 0)
            finished_at = int(combat_potion.get("finished_at_ms") or 0)
            first_eligible = int(timing.get("first_eligible_at_ms") or 0)
            target_health_pct = _numeric_value(
                timing.get("target_health_pct_at_submission")
            )
            remaining_ms = _numeric_value(timing.get("remaining_ms_at_submission"))
            gate_passed = timing.get("gate_passed") is True
            prepot_active = timing.get("prepot_aura_active_at_submission")
            condition_observed = (
                target_health_pct is not None
                and remaining_ms is not None
                and (
                    target_health_pct <= 25.0
                    or remaining_ms <= 26_000.0
                )
            )
            timing_status = (
                "match"
                if policy == "execute_e25_or_remaining_le_26s_no_prepot_overlap"
                and scoring_started > 0
                and submitted_at >= scoring_started
                and finished_at >= submitted_at
                and first_eligible >= scoring_started
                and gate_passed
                and prepot_active is False
                and condition_observed
                else "mismatch"
            )
            if timing_status != "match":
                timing_reason = "combat_potion_timing_gate"
        mismatch = mismatch or timing_status == "mismatch"
        missing = missing or timing_status == "missing"
        if timing_reason and first_broken_edge is None:
            first_broken_edge = timing_reason
        checks.append(
            {
                "kind": "combat_potion_timing",
                "status": timing_status,
                "policy": (
                    "execute_e25_or_remaining_le_26s_no_prepot_overlap"
                ),
                "observed": timing if isinstance(timing, Mapping) else None,
            }
        )
    status = "mismatch" if mismatch else "insufficient_data" if missing else "match"
    return {
        "status": status,
        "inventory_backed": inventory_backed,
        "checks": checks,
        "first_broken_edge": first_broken_edge,
        "interpretation": (
            "A fixture-added aura is not a native item-use receipt. Each configured "
            "item requires inventory provisioning, one native use in its phase, an "
            "item-count decrease, and the expected aura outcome."
        ),
    }


def compare_effective_stats(
    wowsims_compute_stats: dict[str, Any] | None,
    wowsims_debug_result: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
    *,
    reference_class: str | None = None,
) -> dict[str, Any]:
    basis = {
        "wowsims_owner": "ComputeStats.finalStats before dynamic combat procs",
        "wowsims_pet": "first timestamp-zero debug-log Pet stats and Pet inherited stats",
        "trinity": (
            "immutable scoring_start_stats captured at the published calibration t=0 edge; "
            "spell_power is the maximum effective single-school value, not a combined school mask"
        ),
    }
    if not wowsims_compute_stats:
        return {
            "status": "insufficient_data",
            "reason": "missing_wowsims_compute_stats",
            "first_broken_edge": "wowsims_compute_stats_reference",
            "basis": basis,
            "tuning_admitted": False,
        }
    if not runtime:
        return {
            "status": "insufficient_data",
            "reason": "missing_trinity_runtime",
            "first_broken_edge": "trinity_runtime_effective_stat_observation",
            "basis": basis,
            "tuning_admitted": False,
        }
    target_guid = int(runtime.get("calibration_target_guid") or 0)
    runtime_rows = runtime.get("scoring_start_stats") or []
    runtime_row = next(
        (
            row
            for row in runtime_rows
            if isinstance(row, dict)
            and (not target_guid or int(row.get("bot_guid") or 0) == target_guid)
        ),
        None,
    )
    if not isinstance(runtime_row, dict):
        return {
            "status": "insufficient_data",
            "reason": "missing_trinity_scoring_start_stats",
            "first_broken_edge": "trinity_scoring_start_stat_observation",
            "basis": basis,
            "tuning_admitted": False,
        }
    if runtime_row.get("schema") != "trinity_scoring_start_effective_stats_v1":
        return {
            "status": "insufficient_data",
            "reason": "unexpected_trinity_scoring_start_stats_schema",
            "first_broken_edge": "trinity_scoring_start_stat_schema",
            "basis": basis,
            "tuning_admitted": False,
        }
    observed_player = runtime_row.get("player") or {}
    if observed_player.get("observed") is not True:
        return {
            "status": "insufficient_data",
            "reason": "trinity_player_stats_not_observed_at_scoring_start",
            "first_broken_edge": "trinity_scoring_start_player_stat_observation",
            "basis": basis,
            "tuning_admitted": False,
        }
    final = (wowsims_compute_stats.get("stages") or {}).get("final") or {}
    expected_stats = final.get("stats") or {}
    expected_pseudo = final.get("pseudo_stats") or {}
    archetype = str(wowsims_compute_stats.get("archetype") or "")
    primary_stat = str(wowsims_compute_stats.get("primary_stat") or "")
    one_sided_baseline = reference_class == "self_provided_baseline"
    owner_specs: list[tuple[str, Any, Any, float, float]] = [
        (primary_stat, expected_stats.get(primary_stat), observed_player.get(primary_stat), 1.1, 0.001),
        ("hit_rating", expected_stats.get("hit_rating"), observed_player.get("hit_rating"), 0.51, 0.0),
        ("crit_rating", expected_stats.get("crit_rating"), observed_player.get("crit_rating"), 0.51, 0.0),
        ("haste_rating", expected_stats.get("haste_rating"), observed_player.get("haste_rating"), 0.51, 0.0),
        ("mastery_rating", expected_stats.get("mastery_rating"), observed_player.get("mastery_rating"), 0.51, 0.0),
    ]
    if archetype == "spell":
        owner_specs.extend(
            (
                ("spell_power", expected_stats.get("spell_power"), observed_player.get("spell_power"), 5.0, 0.01),
                ("spell_hit_pct", expected_pseudo.get("spell_hit_pct"), observed_player.get("spell_hit_pct"), 0.05, 0.0),
                ("spell_crit_pct", expected_pseudo.get("spell_crit_pct"), observed_player.get("spell_crit_pct"), 0.05, 0.0),
                (
                    "spell_speed_multiplier",
                    float(expected_pseudo.get("cast_speed_multiplier") or 1.0)
                    * (1.0 + float(expected_pseudo.get("spell_haste_pct") or 0.0) / 100.0),
                    observed_player.get("spell_speed_multiplier"),
                    0.002,
                    0.0,
                ),
            )
        )
    elif archetype == "ranged":
        owner_specs.extend(
            (
                ("ranged_attack_power", expected_stats.get("ranged_attack_power"), observed_player.get("ranged_attack_power"), 5.0, 0.01),
                ("physical_hit_pct", expected_pseudo.get("physical_hit_pct"), observed_player.get("physical_hit_pct"), 0.05, 0.0),
                ("ranged_crit_pct", expected_pseudo.get("physical_crit_pct"), observed_player.get("ranged_crit_pct"), 0.05, 0.0),
                (
                    "ranged_speed_multiplier",
                    float(expected_pseudo.get("ranged_speed_multiplier") or 1.0)
                    * (1.0 + float(expected_pseudo.get("ranged_haste_pct") or 0.0) / 100.0),
                    observed_player.get("ranged_speed_multiplier"),
                    0.002,
                    0.0,
                ),
            )
        )
    else:
        owner_specs.extend(
            (
                ("attack_power", expected_stats.get("attack_power"), observed_player.get("attack_power"), 5.0, 0.01),
                ("expertise_rating", expected_stats.get("expertise_rating"), observed_player.get("expertise_rating"), 0.51, 0.0),
                ("physical_hit_pct", expected_pseudo.get("physical_hit_pct"), observed_player.get("physical_hit_pct"), 0.05, 0.0),
                ("melee_crit_pct", expected_pseudo.get("physical_crit_pct"), observed_player.get("melee_crit_pct"), 0.05, 0.0),
                (
                    "melee_speed_multiplier",
                    float(expected_pseudo.get("melee_speed_multiplier") or 1.0)
                    * (1.0 + float(expected_pseudo.get("melee_haste_pct") or 0.0) / 100.0),
                    observed_player.get("melee_speed_multiplier"),
                    0.002,
                    0.0,
                ),
            )
        )
    owner_checks = [
        _stat_check(
            name,
            expected,
            observed,
            absolute_tolerance=absolute,
            relative_tolerance=relative,
            allow_favorable_above=(
                one_sided_baseline
                and name
                in {
                    primary_stat,
                    "spell_power",
                    "spell_crit_pct",
                    "spell_speed_multiplier",
                    "ranged_attack_power",
                    "ranged_crit_pct",
                    "ranged_speed_multiplier",
                    "attack_power",
                    "melee_crit_pct",
                    "melee_speed_multiplier",
                }
            ),
        )
        for name, expected, observed, absolute, relative in owner_specs
        if name
    ]
    owner_status = (
        "match"
        if owner_checks
        and all(row["status"] in {"match", "favorable"} for row in owner_checks)
        else "mismatch"
    )

    observed_pet = runtime_row.get("pet") or {}
    pet_references = ((wowsims_debug_result or {}).get("timeline") or {}).get(
        "pet_stat_references"
    ) or []
    initial_pet_stats = next(
        (
            row
            for row in pet_references
            if row.get("kind") == "pet_stats"
            and float(row.get("timestamp_seconds") or 0.0) == 0.0
        ),
        None,
    )
    initial_pet_inherited = next(
        (
            row
            for row in pet_references
            if row.get("kind") == "pet_inherited_stats"
            and float(row.get("timestamp_seconds") or 0.0) == 0.0
        ),
        None,
    )
    if observed_pet.get("observed") is not True and initial_pet_stats is None:
        pet_comparison = {"status": "not_applicable", "checks": []}
    elif observed_pet.get("observed") is not True:
        pet_comparison = {
            "status": "mismatch",
            "reason": "wowsims_pet_present_but_trinity_pet_missing_at_scoring_start",
            "checks": [],
        }
    elif initial_pet_stats is None:
        pet_comparison = {
            "status": "insufficient_data",
            "reason": "trinity_pet_present_but_wowsims_debug_pet_stats_missing",
            "checks": [],
        }
    else:
        expected_pet = initial_pet_stats.get("stat_vector") or {}
        pet_stat_pairs = (
            ("strength", "strength", 2.0, 0.01),
            ("agility", "agility", 2.0, 0.01),
            ("stamina", "stamina", 2.0, 0.01),
            ("intellect", "intellect", 2.0, 0.01),
            ("spirit", "spirit", 2.0, 0.01),
            ("attack_power", "attack_power", 5.0, 0.01),
            ("spell_power", "spell_power", 5.0, 0.01),
            ("armor", "armor", 2.0, 0.01),
            ("physical_hit_percent", "physical_hit_pct", 0.6, 0.0),
            ("spell_hit_percent", "spell_hit_pct", 0.6, 0.0),
            ("physical_crit_percent", "melee_crit_pct", 1.1, 0.0),
        )
        pet_checks = [
            _stat_check(
                expected_key,
                expected_pet.get(expected_key),
                observed_pet.get(observed_key),
                absolute_tolerance=absolute,
                relative_tolerance=relative,
                allow_favorable_above=(
                    one_sided_baseline
                    and expected_key
                    in {
                        "strength",
                        "agility",
                        "intellect",
                        "attack_power",
                        "spell_power",
                        "armor",
                        "physical_hit_percent",
                        "spell_hit_percent",
                        "physical_crit_percent",
                    }
                ),
            )
            for expected_key, observed_key, absolute, relative in pet_stat_pairs
            if expected_key in expected_pet
        ]
        pet_comparison = {
            "status": (
                "match"
                if pet_checks
                and all(row["status"] in {"match", "favorable"} for row in pet_checks)
                else "mismatch"
            ),
            "source_entity": initial_pet_stats.get("source_entity"),
            "checks": pet_checks,
        }
    pet_comparison["wowsims_inherited_reference"] = initial_pet_inherited
    overall_status = (
        "match"
        if owner_status == "match"
        and pet_comparison["status"] in {"match", "not_applicable"}
        else (
            "insufficient_data"
            if owner_status == "match"
            and pet_comparison["status"] == "insufficient_data"
            else "mismatch"
        )
    )
    if overall_status == "match":
        first_broken_edge = None
    elif owner_status != "match":
        first_broken_edge = "owner_effective_stat_application_before_rotation_execution"
    elif pet_comparison["status"] == "insufficient_data":
        first_broken_edge = "wowsims_debug_pet_stat_reference"
    elif pet_comparison["status"] == "mismatch":
        first_broken_edge = "pet_stat_inheritance_before_rotation_execution"
    else:
        first_broken_edge = "effective_stat_application_before_rotation_execution"
    return {
        "status": overall_status,
        "tuning_admitted": overall_status == "match",
        "basis": basis,
        "comparison_mode": (
            "one_sided_minimum_for_monotonic_throughput_stats"
            if one_sided_baseline
            else "exact_parity"
        ),
        "archetype": archetype,
        "primary_stat": primary_stat,
        "owner": {"status": owner_status, "checks": owner_checks},
        "pet": pet_comparison,
        "first_broken_edge": first_broken_edge,
        "interpretation": (
            "Do not tune action priority or damage coefficients to hide a mismatch here. "
            "Repair setup, stat application, or pet inheritance first, then recapture."
        ),
    }


def build_review(
    *,
    wowsims_apl: dict[str, Any] | None = None,
    wowsims_request: dict[str, Any] | None = None,
    wowsims_result: dict[str, Any] | None = None,
    wowsims_debug_result: dict[str, Any] | None = None,
    wowsims_compute_stats: dict[str, Any] | None = None,
    wowsims_player_index: int = 0,
    trinity_profile: dict[str, Any] | None = None,
    runtime_report: dict[str, Any] | None = None,
    route_manifest: dict[str, Any] | None = None,
    sources: dict[str, Any] | None = None,
    reference_class: str | None = None,
) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema": SCHEMA,
        "reference_class": reference_class,
        "sources": sources or {},
        "wowsims": normalize_wowsims_apl(wowsims_apl) if wowsims_apl else None,
        "wowsims_gear": (
            normalize_wowsims_gear(wowsims_request, wowsims_player_index)
            if wowsims_request
            else None
        ),
        "wowsims_consumables": (
            normalize_wowsims_consumables(wowsims_request, wowsims_player_index)
            if wowsims_request
            else None
        ),
        "wowsims_result": (
            normalize_wowsims_result(wowsims_result, wowsims_player_index)
            if wowsims_result
            else None
        ),
        "wowsims_debug_result": (
            normalize_wowsims_result(wowsims_debug_result, wowsims_player_index)
            if wowsims_debug_result
            else None
        ),
        "wowsims_compute_stats": (
            normalize_wowsims_compute_stats(wowsims_compute_stats, wowsims_player_index)
            if wowsims_compute_stats
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
    runtime_comparison = (
        compare_simulated_to_trinity_runtime(
            review["wowsims_result"],
            review["runtime"],
            wowsims=review["wowsims"],
            trinity=review["trinity"],
        )
        if review["wowsims_result"] and review["runtime"]
        else None
    )
    review["execution_comparison"] = {
        "apl_to_wowsims_result": (
            compare_apl_to_simulated_actions(review["wowsims"], review["wowsims_result"])
            if review["wowsims"] and review["wowsims_result"]
            else None
        ),
        "wowsims_result_to_trinity_runtime": runtime_comparison,
        "cast_mix": (
            runtime_comparison["cast_mix"]
            if runtime_comparison is not None
            else compare_cast_mix(review["wowsims"], review["wowsims_result"], review["runtime"])
        ),
    }
    review["effective_stat_parity"] = compare_effective_stats(
        review["wowsims_compute_stats"],
        review["wowsims_debug_result"] or review["wowsims_result"],
        review["runtime"],
        reference_class=reference_class,
    )
    review["gear_parity"] = compare_gear_identity(
        review["wowsims_gear"], review["runtime"]
    )
    review["consumable_parity"] = compare_consumable_execution(
        review["wowsims_consumables"], review["runtime"]
    )
    gate_statuses = {
        review["gear_parity"]["status"],
        review["effective_stat_parity"]["status"],
    }
    overall_status = (
        "match"
        if gate_statuses == {"match"}
        else "mismatch"
        if "mismatch" in gate_statuses
        else "insufficient_data"
    )
    review["dps_tuning_gate"] = {
        "status": overall_status,
        "tuning_admitted": overall_status == "match",
        "required": [
            "gear_parity.status=match",
            "effective_stat_parity.status=match",
        ],
        "first_broken_edge": (
            review["gear_parity"].get("first_broken_edge")
            if review["gear_parity"]["status"] != "match"
            else review["effective_stat_parity"].get("first_broken_edge")
        ),
    }
    consumable_required = review["consumable_parity"]["status"] != "not_applicable"
    total_statuses = set(gate_statuses)
    if consumable_required:
        total_statuses.add(review["consumable_parity"]["status"])
    total_status = (
        "match"
        if total_statuses == {"match"}
        else "mismatch"
        if "mismatch" in total_statuses
        else "insufficient_data"
    )
    review["total_dps_comparison_gate"] = {
        "status": total_status,
        "comparison_admitted": total_status == "match",
        "required": review["dps_tuning_gate"]["required"]
        + (["consumable_parity.status=match"] if consumable_required else []),
        "first_broken_edge": (
            review["dps_tuning_gate"].get("first_broken_edge")
            if review["dps_tuning_gate"]["status"] != "match"
            else review["consumable_parity"].get("first_broken_edge")
            if consumable_required
            else None
        ),
        "trace_only_signals_remain_usable": True,
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
    parser.add_argument("--wowsims-request", type=Path)
    parser.add_argument("--wowsims-player-index", type=int, default=0)
    parser.add_argument("--reference-class")
    parser.add_argument("--wowsims-result", type=Path)
    parser.add_argument("--wowsims-debug-result", type=Path)
    parser.add_argument("--wowsims-compute-stats", type=Path)
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
    if not any((args.wowsims_apl, args.wowsims_request, args.wowsims_result, args.wowsims_debug_result, args.wowsims_compute_stats, args.trinity_profile, args.trinity_worldserver_conf, args.runtime_report, args.route_manifest)):
        parser.error("provide at least one review input")

    sources: dict[str, Any] = {}
    apl = None
    embedded_request = None
    if args.wowsims_apl:
        raw = _load_json(args.wowsims_apl)
        apl = find_wowsims_apl(raw, args.wowsims_player_index)
        embedded_request = _embedded_wowsims_request(raw)
        sources["wowsims_apl"] = _source_record(args.wowsims_apl)
    explicit_request = (
        _load_json(args.wowsims_request) if args.wowsims_request else None
    )
    try:
        wowsims_request, request_source = _admit_wowsims_request(
            embedded_request=embedded_request,
            explicit_request=explicit_request,
            explicit_path=args.wowsims_request,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if request_source is not None:
        sources["wowsims_request"] = request_source
    wowsims_result = _load_json(args.wowsims_result) if args.wowsims_result else None
    if args.wowsims_result:
        sources["wowsims_result"] = _source_record(args.wowsims_result)
    wowsims_debug_result = (
        _load_json(args.wowsims_debug_result) if args.wowsims_debug_result else None
    )
    if args.wowsims_debug_result:
        sources["wowsims_debug_result"] = _source_record(args.wowsims_debug_result)
    wowsims_compute_stats = (
        _load_json(args.wowsims_compute_stats)
        if args.wowsims_compute_stats
        else None
    )
    if args.wowsims_compute_stats:
        sources["wowsims_compute_stats"] = _source_record(
            args.wowsims_compute_stats
        )
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
        wowsims_request=wowsims_request,
        wowsims_result=wowsims_result,
        wowsims_debug_result=wowsims_debug_result,
        wowsims_compute_stats=wowsims_compute_stats,
        wowsims_player_index=args.wowsims_player_index,
        trinity_profile=profile,
        runtime_report=runtime,
        route_manifest=route,
        sources=sources,
        reference_class=args.reference_class,
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
