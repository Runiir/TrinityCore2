"""Encounter damage fidelity: DamageModifier preflight and per-run boss melee statistics.

Why. Upstream migration sql/updates/world/4.3.4/2025_06_18_06_world.sql set
creature_template.DamageModifier to 1 for every creature, pending
re-evaluation. That made Magmaw 10N melee about 16 times weaker than the
matched WCL sample, so the tank's Vengeance never built and healers idled.
Every other boss, add and trash template has the same problem until it is
calibrated. The calibration registry
(experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json)
records each checked template and how to calibrate the next one.

Two checks, written to report.json ``encounter_fidelity`` and mirrored in
combat_analysis.json ``encounter_fidelity``:

preflight
    A read-only SELECT of creature_template for every entry the validation
    route manifest can engage (boss nodes, trash packs, adds, alternates and
    mechanic targets), resolved to the difficulty template the map loads. Each
    entry is ``calibrated`` (the registry value equals the DB), ``mismatch``
    (the registry says X and the DB holds Y, e.g. the migration is not
    applied), ``uncalibrated`` (registry open or absent), ``not_applicable``,
    ``missing_template``, or ``unverified`` (registry calibrated, DB not read).
    The worldserver applies world updates at startup, so the post-run read
    shows the templates the run loaded.
boss_melee
    Per boss entry, from the native melee_resolution events: swings by
    outcome, median swing gap vs BaseAttackTime, min/mean/max of every
    calculation stage the events carry, absorbed share, fully absorbed hits
    and tank damage taken per second over the boss window. When the registry
    or the encounter ledger has a WCL reference, the after-attacker stage
    (comparable to WCL "U") is compared at min/mean/max and flagged outside
    +-10%.

``blizzlike`` is False when a boss is uncalibrated, mismatched or missing, or
swung with a runtime DamageModifier other than the registry value. It is
True when every boss is calibrated or not_applicable, and None when it cannot
be told. All of this is information for the verdict and the scoreboard: it
never blocks a run and never changes acceptance or counting.

CLI:
  preflight --route-manifest PATH --config WORLDSERVER_CONF [--difficulty 10N]
  run-dir RUN_DIR [--config WORLDSERVER_CONF]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path("experiments/configs/encounter_fidelity/creature_damage_calibration_v1.json")
REGISTRY_SCHEMA = "creature_damage_calibration_v1"
FIDELITY_SCHEMA = "encounter_fidelity_v1"
PREFLIGHT_SCHEMA = "encounter_fidelity_preflight_v1"
BOSS_MELEE_SCHEMA = "encounter_fidelity_boss_melee_v1"
REGISTRY_STATUSES = ("calibrated", "open", "not_applicable")
CLOSED_STATUSES = ("calibrated", "not_applicable")
NOT_BLIZZLIKE = ("uncalibrated", "mismatch", "missing_template")
BOSS_RANK = 3
INSTANCE_BIND_FLAG = 0x1  # CREATURE_FLAG_EXTRA_INSTANCE_BIND marks encounter bosses
MODIFIER_TOLERANCE = 1e-3
WCL_RATIO_TOLERANCE = 0.10
WCL_STAGE = "after_attacker_bonus_amount"
# Computed before the outcome roll: every swing, avoided or not, is a roll sample.
PRE_OUTCOME_STAGES = ("weapon_roll_amount", "after_attacker_bonus_amount", "after_target_bonus_amount",
                      "after_script_hook_amount", "after_armor_amount")
POST_OUTCOME_STAGES = ("after_hit_outcome_amount", "after_resilience_amount", "blocked_amount",
                       "absorbed_amount", "resisted_amount", "resolved_damage_amount")
LANDED_OUTCOMES = frozenset({"normal", "critical", "block", "glancing", "crushing"})
OUTCOME_LABELS = {"normal": "hit", "critical": "crit"}
TEMPLATE_COLUMNS = ("entry", "name", "rank", "unit_class", "DamageModifier", "BaseAttackTime", "BaseVariance",
                    "flags_extra", "difficulty_entry_1", "difficulty_entry_2", "difficulty_entry_3")
RAID_SPAWN_MODES = {"10N": 0, "25N": 1, "10H": 2, "25H": 3}
DIFFICULTY_WORDS = {"normal_10man": "10N", "normal_25man": "25N", "heroic_10man": "10H", "heroic_25man": "25H"}
ENGAGED_NODE_KINDS = ("boss", "trash")
TARGET_LIST_FIELDS = ("pack_target_entries", "add_target_entries", "alternate_target_entries")

RowSource = Callable[[Sequence[int]], Mapping[int, Mapping[str, Any]]]


# --- registry -----------------------------------------------------------------------------------

def load_registry(root: Path = REPO_ROOT, path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else Path(root) / REGISTRY_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("schema") != REGISTRY_SCHEMA or not isinstance(data.get("creatures"), dict):
        raise ValueError(f"{target}: not a {REGISTRY_SCHEMA} registry")
    return data


def registry_row(registry: Mapping[str, Any] | None, entry: int) -> dict[str, Any] | None:
    row = ((registry or {}).get("creatures") or {}).get(str(int(entry)))
    return row if isinstance(row, dict) else None


def _registry_value(row: Mapping[str, Any] | None) -> float | None:
    value = (row or {}).get("damage_modifier")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def scenario_damage_fidelity(root: Path, encounter: Mapping[str, str]) -> dict[str, Any]:
    """Registry state of a scenario's boss entries; closable when each is calibrated or not_applicable."""
    try:
        registry = load_registry(root)
    except (OSError, ValueError) as error:
        return {"registry": REGISTRY_PATH.as_posix(), "boss_entries": {}, "closable": False,
                "reason": f"registry unavailable: {error}"}
    wanted = (encounter.get("raid"), encounter.get("boss"), encounter.get("mode"))
    bosses = {entry: row.get("status") for entry, row in sorted(registry["creatures"].items())
              if isinstance(row, dict) and row.get("role") == "boss"
              and (row.get("raid"), row.get("boss"), row.get("mode")) == wanted}
    if not bosses:
        reason = "no boss entry of this scenario is in the registry"
    else:
        blocking = sorted(entry for entry, status in bosses.items() if status not in CLOSED_STATUSES)
        reason = f"not calibrated or not_applicable: {', '.join(blocking)}" if blocking else None
    return {"registry": REGISTRY_PATH.as_posix(), "boss_entries": bosses, "closable": reason is None,
            "reason": reason}


def check_scenario_damage_fidelity(root: Path, encounter: Mapping[str, str]) -> None:
    """Raise ValueError unless the scenario's encounter_damage_fidelity requirement may close."""
    state = scenario_damage_fidelity(root, encounter)
    if not state["closable"]:
        raise ValueError("encounter_damage_fidelity: " + str(state["reason"]))


def _ledger_reference(root: Path, ledger: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        data = json.loads((Path(root) / str(ledger["path"])).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        return None
    for value in data.get("values") or []:
        if isinstance(value, dict) and value.get("key") == ledger.get("value_key"):
            samples = value.get(str(ledger.get("samples_field"))) or {}
            if samples.get("unmitigated_estimate_min") and samples.get("unmitigated_estimate_max"):
                return {"u_min": samples["unmitigated_estimate_min"], "u_max": samples["unmitigated_estimate_max"],
                        "u_mean": samples.get("unmitigated_estimate_mean"),
                        "landed_samples": samples.get("landed"), "source": f"ledger:{ledger['path']}"}
    return None


def wcl_reference(registry: Mapping[str, Any] | None, entry: int, root: Path = REPO_ROOT) -> dict[str, Any] | None:
    """WCL U reference for an entry: the registry first, then the encounter ledger it points at."""
    row = registry_row(registry, entry) or {}
    reference = row.get("wcl_melee_reference")
    if isinstance(reference, dict) and reference.get("u_min") and reference.get("u_max"):
        reference = dict(reference, source=f"registry:{REGISTRY_PATH.as_posix()}")
    elif isinstance(row.get("ledger"), dict):
        reference = _ledger_reference(root, row["ledger"])
    else:
        return None
    if not reference:
        return None
    u_min, u_max = float(reference["u_min"]), float(reference["u_max"])
    mean = reference.get("u_mean")
    return {"stage": WCL_STAGE, "u_min": u_min, "u_max": u_max,
            "u_mean": float(mean) if mean else round((u_min + u_max) / 2.0, 1),
            "mean_basis": "wcl_sample_mean" if mean else "wcl_envelope_midpoint",
            "landed_samples": reference.get("landed_samples"), "source": reference.get("source")}


# --- route manifest and difficulty ----------------------------------------------------------------

def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _mode_from_text(value: Any) -> tuple[str, int, bool] | None:
    text = str(value or "").lower()
    if not text:
        return None
    for word, mode in DIFFICULTY_WORDS.items():
        if word in text:
            return mode, RAID_SPAWN_MODES[mode], True
    tokens = set(re.split(r"[^0-9a-z]+", text))
    for token in tokens:
        match = re.fullmatch(r"(10|25)(n|h|hc)", token)
        if match:
            mode = match[1] + match[2][0].upper()
            return mode, RAID_SPAWN_MODES[mode], True
    if "heroic" in tokens:  # five-player dungeon heroic loads difficulty_entry_1
        return "5H", 1, False
    return None


def resolve_difficulty(route_manifest: Mapping[str, Any] | None, difficulty: str | None = None) -> dict[str, Any]:
    """Spawn mode of the run, from an explicit argument or the manifest's scenario identity."""
    manifest = route_manifest if isinstance(route_manifest, Mapping) else {}
    candidates: list[tuple[str, Any]] = [("argument", difficulty), ("route_manifest.scenario_id", manifest.get("scenario_id"))]
    for route in manifest.get("routes") or []:
        if isinstance(route, Mapping):
            for key in ("difficulty", "diagnostic_parent_scenario_id", "scenario_id", "runtime_profile_id"):
                candidates.append((f"route.{key}", route.get(key)))
    for source, value in candidates:
        found = _mode_from_text(value)
        if found:
            mode, spawn_mode, is_raid = found
            return {"mode": mode, "spawn_mode": spawn_mode, "is_raid": is_raid, "source": source}
    return {"mode": None, "spawn_mode": 0, "is_raid": False, "source": "assumed_base_template"}


def engaged_entries(route_manifest: Mapping[str, Any] | None) -> dict[int, dict[str, Any]]:
    """Creature entries the route can engage, with their nodes and whether a boss node names them."""
    found: dict[int, dict[str, Any]] = {}

    def add(value: Any, route: Mapping[str, Any], field: str, boss_node: bool = False) -> None:
        entry = _int(value)
        if entry <= 0:
            return
        row = found.setdefault(entry, {"route_nodes": [], "manifest_fields": [], "boss_node": False,
                                       "on_boss_node": False})
        node = str(route.get("route_node_id") or route.get("node_id") or "")
        if node and node not in row["route_nodes"]:
            row["route_nodes"].append(node)
        if field not in row["manifest_fields"]:
            row["manifest_fields"].append(field)
        row["boss_node"] = row["boss_node"] or boss_node
        row["on_boss_node"] = row["on_boss_node"] or str(route.get("kind") or route.get("node_kind") or "").lower() == "boss"

    manifest = route_manifest if isinstance(route_manifest, Mapping) else {}
    for route in manifest.get("routes") or []:
        if not isinstance(route, Mapping):
            continue
        kind = str(route.get("kind") or route.get("node_kind") or "").lower()
        if kind in ENGAGED_NODE_KINDS:
            add(route.get("source_entry"), route, "source_entry", boss_node=kind == "boss")
        for field in TARGET_LIST_FIELDS:
            for value in route.get(field) or []:
                add(value, route, field)
        add(route.get("opener_target_entry"), route, "opener_target_entry")
        priority = route.get("target_priority") if isinstance(route.get("target_priority"), Mapping) else {}
        for value in priority.get("alternate_target_entries") or []:
            add(value, route, "target_priority.alternate_target_entries")
        add(priority.get("opener_target_entry"), route, "target_priority.opener_target_entry")
        contract = route.get("mechanic_contract") if isinstance(route.get("mechanic_contract"), Mapping) else {}
        for value in contract.get("target_entries") or []:
            add(value, route, "mechanic_contract.target_entries")
    return found


# --- preflight ------------------------------------------------------------------------------------

def mysql_row_source(worldserver_conf: Path) -> RowSource:
    """creature_template rows through the harness's world DB connection; SELECT only, read-only session."""
    try:
        from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf
    except ImportError:  # pragma: no cover - script-style imports
        from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf
    url = database_url_from_worldserver_conf(Path(worldserver_conf), "WorldDatabaseInfo")

    def fetch(entries: Sequence[int]) -> dict[int, dict[str, Any]]:
        wanted = sorted({int(entry) for entry in entries if int(entry) > 0})
        if not wanted:
            return {}
        columns = ", ".join(f"`{column}`" for column in TEMPLATE_COLUMNS)
        conn = connect_mysql(url)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                cursor.execute("START TRANSACTION READ ONLY")
                cursor.execute(f"SELECT {columns} FROM `creature_template` WHERE `entry` IN "
                               f"({', '.join(['%s'] * len(wanted))})", wanted)
                rows = cursor.fetchall()
            conn.rollback()
        finally:
            conn.close()
        return {int(row["entry"]): dict(row) for row in rows}
    return fetch


def _template(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "damage_modifier": float(row["DamageModifier"]) if row.get("DamageModifier") is not None else None,
        "base_attack_time_ms": _int(row.get("BaseAttackTime")),
        "base_variance": float(row["BaseVariance"]) if row.get("BaseVariance") is not None else None,
        "rank": _int(row.get("rank")),
        "unit_class": _int(row.get("unit_class")),
        "flags_extra": _int(row.get("flags_extra")),
        "difficulty_entries": [_int(row.get(f"difficulty_entry_{index}")) for index in (1, 2, 3)],
    }


def effective_entry(base: int, templates: Mapping[int, Mapping[str, Any]], spawn_mode: int, is_raid: bool) -> int:
    """Template the map loads (Creature::InitEntry): raid heroic falls back to normal, others step down."""
    row = templates.get(base)
    diff = spawn_mode
    while row and diff > 0:
        candidate = row["difficulty_entries"][diff - 1] if diff <= 3 else 0
        if candidate and candidate in templates:
            return candidate
        diff = diff - 2 if diff >= 2 and is_raid else diff - 1
    return base


def classify(registry_entry: Mapping[str, Any] | None, db_modifier: float | None, db_read: bool) -> tuple[str, str]:
    status = (registry_entry or {}).get("status")
    expected = _registry_value(registry_entry)
    if status == "not_applicable":
        return "not_applicable", str((registry_entry or {}).get("reason") or "registry: no melee or weapon damage")
    if db_read and db_modifier is None:
        return "missing_template", "creature_template row not found"
    if status == "calibrated" and expected is not None:
        if not db_read:
            return "unverified", f"registry DamageModifier {expected:g}; DB not read"
        if abs(db_modifier - expected) <= MODIFIER_TOLERANCE:
            return "calibrated", f"DamageModifier {db_modifier:g} matches the registry"
        return "mismatch", f"registry DamageModifier {expected:g}, DB {db_modifier:g}"
    detail = "registry open" if status == "open" else "not in registry"
    if db_modifier is not None:
        detail += f"; DB DamageModifier {db_modifier:g}"
        if abs(db_modifier - 1.0) > MODIFIER_TOLERANCE:
            detail += " without registry evidence"
    return "uncalibrated", detail


def preflight(route_manifest: Mapping[str, Any] | None, registry: Mapping[str, Any] | None,
              fetch_rows: RowSource | None, *, difficulty: str | None = None) -> dict[str, Any]:
    """Classify every engageable creature entry; never raises on DB trouble."""
    engaged = engaged_entries(route_manifest)
    resolved = resolve_difficulty(route_manifest, difficulty)
    templates: dict[int, dict[str, Any]] = {}
    error = None
    if engaged and fetch_rows is not None:
        try:
            templates = {int(entry): _template(row) for entry, row in fetch_rows(sorted(engaged)).items()}
            extra = sorted({entry for row in templates.values() for entry in row["difficulty_entries"]
                            if entry and entry not in templates})
            if extra and resolved["spawn_mode"] > 0:
                templates.update({int(entry): _template(row) for entry, row in fetch_rows(extra).items()})
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # SystemExit from the connection helpers included
            error, templates = f"{type(exc).__name__}: {exc}", {}
    db_read = bool(engaged) and fetch_rows is not None and error is None
    rows = []
    for base in sorted(engaged):
        effective = effective_entry(base, templates, resolved["spawn_mode"], resolved["is_raid"])
        template = templates.get(effective)
        base_template = templates.get(base) or {}
        registered = registry_row(registry, effective)
        boss_basis = [basis for basis, hit in (
            ("boss_route_node", engaged[base]["boss_node"]),
            ("rank_3", BOSS_RANK in (base_template.get("rank"), (template or {}).get("rank"))),
            ("instance_bind", bool((base_template.get("flags_extra") or 0) & INSTANCE_BIND_FLAG)),
            ("registry_role_boss", (registered or registry_row(registry, base) or {}).get("role") == "boss"),
        ) if hit]
        classification, detail = classify(registered, (template or {}).get("damage_modifier"), db_read)
        rows.append({
            "entry": base, "effective_entry": effective,
            "name": (template or {}).get("name") or (registered or {}).get("name"),
            "role": "boss" if boss_basis else "add" if engaged[base]["on_boss_node"] else "trash",
            "boss_basis": boss_basis,
            **engaged[base],
            "db": template,
            "registry": {"status": registered.get("status"), "damage_modifier": _registry_value(registered)}
            if registered else None,
            "classification": classification, "detail": detail,
        })
    counts = Counter(row["classification"] for row in rows)
    status = ("no_engaged_entries" if not engaged else "db_unavailable" if error
              else "db_not_read" if fetch_rows is None else "ok")
    return {
        "schema": PREFLIGHT_SCHEMA,
        "status": status,
        "db_error": error, "difficulty": resolved, "entries": rows, "counts": dict(sorted(counts.items())),
        "boss_entries": [row["entry"] for row in rows if row["role"] == "boss"],
        "not_blizzlike_entries": [row["entry"] for row in rows if row["classification"] in NOT_BLIZZLIKE],
    }


# --- per-run melee --------------------------------------------------------------------------------

def _stats(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "mean": None, "max": None}
    return {"count": len(values), "min": round(min(values), 1), "mean": round(sum(values) / len(values), 1),
            "max": round(max(values), 1)}


def _ratio(native: float | None, reference: float | None) -> float | None:
    return round(native / reference, 4) if native is not None and reference else None


def _stage_keys(swings: Iterable[Mapping[str, Any]]) -> list[str]:
    seen = {key for event in swings for key, value in event["melee_resolution"].items()
            if key.endswith("_amount") and isinstance(value, (int, float))}
    known = [key for key in (*PRE_OUTCOME_STAGES, *POST_OUTCOME_STAGES) if key in seen]
    return known + sorted(seen - set(known))


def _window(swings: Sequence[Mapping[str, Any]], nodes: Iterable[str],
            combat_analysis: Mapping[str, Any] | None) -> dict[str, Any] | None:
    wanted = set(nodes) | {str(event.get("route_node_id") or "") for event in swings}
    wanted.discard("")
    for encounter in (combat_analysis or {}).get("encounters") or []:
        if isinstance(encounter, Mapping) and str(encounter.get("route_node_id") or "") in wanted:
            first, last = _int(encounter.get("first_at_ms")), _int(encounter.get("last_at_ms"))
            if first > 0 and last > first:
                return {"route_node_id": encounter.get("route_node_id"), "first_at_ms": first, "last_at_ms": last,
                        "duration_sec": round((last - first) / 1000.0, 3), "basis": "combat_analysis_encounter"}
    stamps = [_int(event.get("timestamp_ms")) for event in swings]
    if len(stamps) >= 2 and max(stamps) > min(stamps):
        return {"route_node_id": None, "first_at_ms": min(stamps), "last_at_ms": max(stamps),
                "duration_sec": round((max(stamps) - min(stamps)) / 1000.0, 3), "basis": "first_to_last_swing"}
    return None


def _swing_gaps(swings: Sequence[Mapping[str, Any]]) -> list[int]:
    lanes: dict[tuple[int, Any], list[int]] = {}
    for event in swings:
        lane = (_int(event.get("source_guid")), event["melee_resolution"].get("attack_type"))
        lanes.setdefault(lane, []).append(_int(event.get("timestamp_ms")))
    gaps = []
    for stamps in lanes.values():
        stamps.sort()
        gaps += [later - earlier for earlier, later in zip(stamps, stamps[1:]) if later > earlier]
    return gaps


def _mode_value(values: Iterable[Any]) -> Any:
    counted = Counter(value for value in values if value is not None)
    return counted.most_common(1)[0][0] if counted else None


def _index(combat_log: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]],
                                                   dict[int, Mapping[str, Any]], set[int]]:
    events = [event for event in combat_log.get("recent_events") or [] if isinstance(event, Mapping)]
    melee = [event for event in events if event.get("kind") == "melee_resolution"
             and isinstance(event.get("melee_resolution"), Mapping) and not event.get("source_is_pet")
             and _int(event.get("source_entry")) > 0]
    linked = {_int(event.get("related_event_sequence")): event for event in events
              if event.get("kind") == "damage" and event.get("related_event_sequence") is not None
              and _int(event.get("spell_id")) == 0}
    tanks = {_int(event.get("actor_guid")) for event in events if event.get("actor_role") == "tank"}
    tanks.discard(0)
    return events, melee, linked, tanks


def melee_stats(entry: int, swings: Sequence[Mapping[str, Any]], *, events: Sequence[Mapping[str, Any]],
                linked: Mapping[int, Mapping[str, Any]], tanks: set[int], registry: Mapping[str, Any] | None,
                effective: int | None = None, template: Mapping[str, Any] | None = None,
                route_nodes: Iterable[str] = (), combat_analysis: Mapping[str, Any] | None = None,
                root: Path = REPO_ROOT) -> dict[str, Any]:
    swings = sorted(swings, key=lambda event: (_int(event.get("timestamp_ms")), _int(event.get("event_sequence"))))
    resolution = [event["melee_resolution"] for event in swings]
    outcomes = Counter(OUTCOME_LABELS.get(str(row.get("hit_outcome_name")), str(row.get("hit_outcome_name")))
                       for row in resolution)
    landed = [event for event in swings if event["melee_resolution"].get("hit_outcome_name") in LANDED_OUTCOMES]
    stages = {}
    for key in _stage_keys(swings):
        population = swings if key in PRE_OUTCOME_STAGES else landed
        values = [float(event["melee_resolution"][key]) for event in population
                  if isinstance(event["melee_resolution"].get(key), (int, float))]
        stages[key] = {"population": "all_swings" if key in PRE_OUTCOME_STAGES else "landed", **_stats(values)}

    def health(event: Mapping[str, Any]) -> float:
        damage = linked.get(_int(event.get("melee_resolution_sequence") or event.get("event_sequence")))
        if damage is not None:
            return float(damage.get("amount") or 0)
        return float(event["melee_resolution"].get("resolved_damage_amount") or 0)

    stages["health_damage"] = {"population": "landed", "basis": "linked_damage_event_amount",
                               **_stats([health(event) for event in landed])}
    pre_absorb = sum(float(event["melee_resolution"].get("after_resilience_amount")
                           or event["melee_resolution"].get("after_hit_outcome_amount") or 0) for event in landed)
    absorbed = sum(float(event["melee_resolution"].get("absorbed_amount") or 0) for event in landed)
    fully_absorbed = sum(1 for event in landed if float(event["melee_resolution"].get("absorbed_amount") or 0) > 0
                         and not float(event["melee_resolution"].get("resolved_damage_amount") or 0))
    gaps = _swing_gaps(swings)
    base_time = (template or {}).get("base_attack_time_ms") or _mode_value(
        row.get("attacker_base_attack_time_ms") for row in resolution)
    median_gap = statistics.median(gaps) if gaps else None
    window = _window(swings, route_nodes, combat_analysis)
    tank_rate = None
    if window and window["duration_sec"] > 0:
        first, last, seconds = window["first_at_ms"], window["last_at_ms"], window["duration_sec"]
        taken = sum(float(event.get("amount") or 0) for event in events
                    if event.get("kind") == "damage" and _int(event.get("target_guid")) in tanks
                    and first <= _int(event.get("timestamp_ms")) <= last)
        from_boss = sum(health(event) for event in landed if _int(event.get("target_guid")) in tanks
                        and first <= _int(event.get("timestamp_ms")) <= last)
        tank_rate = {"all_sources": round(taken / seconds, 1), "this_creature_melee": round(from_boss / seconds, 1)}
    runtime_modifier = _mode_value(row.get("attacker_template_damage_modifier") for row in resolution)
    entry_for_registry = effective or entry
    registered = registry_row(registry, entry_for_registry)
    result = {
        "schema": BOSS_MELEE_SCHEMA, "entry": entry, "effective_entry": entry_for_registry,
        "name": _mode_value(event.get("source_name") for event in swings) or (registered or {}).get("name"),
        "swings": len(swings), "landed": len(landed), "outcomes": dict(sorted(outcomes.items())),
        "tank_target_share": round(sum(_int(event.get("target_guid")) in tanks for event in swings) / len(swings), 3)
        if swings else None,
        "swing_gap_ms": {"count": len(gaps), "median": median_gap, "base_attack_time_ms": base_time,
                         "median_over_base": _ratio(median_gap, base_time)},
        "runtime_template": {
            "damage_modifier": runtime_modifier,
            "damage_modifiers_seen": sorted({row.get("attacker_template_damage_modifier") for row in resolution
                                             if row.get("attacker_template_damage_modifier") is not None}),
            "base_attack_time_ms": _mode_value(row.get("attacker_base_attack_time_ms") for row in resolution),
            "published_min_damage": _mode_value(row.get("attacker_published_min_damage") for row in resolution),
            "published_max_damage": _mode_value(row.get("attacker_published_max_damage") for row in resolution),
            "level": _mode_value(row.get("attacker_level") for row in resolution),
        },
        "registry": {"status": registered.get("status"), "damage_modifier": _registry_value(registered)}
        if registered else None,
        "stages": stages,
        "absorbed": {"pre_absorb_total": round(pre_absorb, 1), "absorbed_total": round(absorbed, 1),
                     "absorbed_share": round(absorbed / pre_absorb, 4) if pre_absorb else None,
                     "fully_absorbed_hits": fully_absorbed},
        "boss_window": window,
        "tank_damage_taken_per_sec": tank_rate,
    }
    result["wcl_comparison"] = wcl_comparison(stages.get(WCL_STAGE), wcl_reference(registry, entry_for_registry, root),
                                              runtime_modifier)
    return result


def wcl_comparison(native: Mapping[str, Any] | None, reference: Mapping[str, Any] | None,
                   runtime_modifier: float | None) -> dict[str, Any] | None:
    """Native after-attacker stage vs WCL U at min/mean/max, flagged outside +-10%."""
    if not reference:
        return None
    native = native or {}
    ratios = {"min": _ratio(native.get("min"), reference["u_min"]),
              "mean": _ratio(native.get("mean"), reference["u_mean"]),
              "max": _ratio(native.get("max"), reference["u_max"])}
    flags = [f"{key}_outside_{int(WCL_RATIO_TOLERANCE * 100)}pct" for key, ratio in ratios.items()
             if ratio is not None and abs(ratio - 1.0) > WCL_RATIO_TOLERANCE]
    implied = (round(float(runtime_modifier) / ratios["mean"], 2)
               if runtime_modifier and ratios["mean"] else None)
    return {**reference, "native_stage": WCL_STAGE, "native_count": native.get("count", 0), "ratios": ratios,
            "flags": flags, "within_tolerance": not flags if native.get("count") else None,
            "implied_damage_modifier_from_mean": implied}


def boss_melee(combat_log: Mapping[str, Any] | None, bosses: Mapping[int, Mapping[str, Any]],
               registry: Mapping[str, Any] | None, *, combat_analysis: Mapping[str, Any] | None = None,
               root: Path = REPO_ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    """(boss_melee, creature_melee): full stats per boss entry, a compact row per other melee source.

    Bosses come from the preflight; any melee source whose runtime template is rank 3 is added.
    """
    if not isinstance(combat_log, Mapping):
        return {}, {}
    events, melee, linked, tanks = _index(combat_log)
    by_entry: dict[int, list[Mapping[str, Any]]] = {}
    for event in melee:
        by_entry.setdefault(_int(event.get("source_entry")), []).append(event)
    wanted = {int(entry): dict(row) for entry, row in bosses.items()}
    for entry, swings in by_entry.items():
        if entry not in wanted and any(_int(e["melee_resolution"].get("attacker_rank")) == BOSS_RANK for e in swings):
            wanted[entry] = {}
    result = {}
    for entry, row in sorted(wanted.items()):
        result[str(entry)] = melee_stats(
            entry, by_entry.get(entry, []), events=events, linked=linked, tanks=tanks, registry=registry,
            effective=row.get("effective_entry"), template=row.get("db"), route_nodes=row.get("route_nodes") or (),
            combat_analysis=combat_analysis, root=root)
    others = {}
    for entry, swings in sorted(by_entry.items()):
        if entry in wanted:
            continue
        landed = [e for e in swings if e["melee_resolution"].get("hit_outcome_name") in LANDED_OUTCOMES]
        registered = registry_row(registry, entry)
        others[str(entry)] = {
            "name": _mode_value(e.get("source_name") for e in swings), "swings": len(swings), "landed": len(landed),
            "after_attacker_mean": _stats([float(e["melee_resolution"][WCL_STAGE]) for e in swings
                                           if isinstance(e["melee_resolution"].get(WCL_STAGE), (int, float))])["mean"],
            "runtime_damage_modifier": _mode_value(e["melee_resolution"].get("attacker_template_damage_modifier")
                                                   for e in swings),
            "registry_status": (registered or {}).get("status"),
        }
    return result, others


# --- verdict and hook -----------------------------------------------------------------------------

def fidelity_verdict(pre: Mapping[str, Any], melee: Mapping[str, Mapping[str, Any]]) -> tuple[bool | None, list[str]]:
    """Preflight classification of every boss, then the DamageModifier the bosses actually swung with."""
    reasons: list[str] = []
    bosses = [row for row in pre.get("entries") or [] if row.get("role") == "boss"]
    flagged = set()
    for row in bosses:
        if row["classification"] in NOT_BLIZZLIKE:
            label = f"boss {row['entry']}" + (f"/{row['effective_entry']}" if row["effective_entry"] != row["entry"] else "")
            name = row.get("name") or (melee.get(str(row["entry"])) or {}).get("name")
            reasons.append(f"{label} {name}: {row['classification']} ({row['detail']})")
            flagged.add(row["entry"])
    confirmed = set()
    for key, stats in sorted(melee.items(), key=lambda item: int(item[0])):
        registered = stats.get("registry") or {}
        expected = registered.get("damage_modifier")
        seen = (stats.get("runtime_template") or {}).get("damage_modifier")
        name = stats.get("name")
        if registered.get("status") == "calibrated" and expected is not None and seen is not None:
            if abs(float(seen) - float(expected)) > MODIFIER_TOLERANCE:
                reasons.append(f"boss {key} {name}: runtime DamageModifier {float(seen):g} != registry {float(expected):g}")
            else:
                confirmed.add(int(key))
        elif registered.get("status") not in CLOSED_STATUSES and stats.get("swings") and int(key) not in flagged:
            shown = "unknown" if seen is None else format(float(seen), "g")
            reasons.append(f"boss {key} {name}: swung without registry calibration (runtime DamageModifier {shown})")
    if reasons:
        return False, reasons
    if not bosses and not melee:
        return None, ["no boss entry in the route manifest or combat log"]
    unknown = [row["entry"] for row in bosses if row["classification"] == "unverified" and row["entry"] not in confirmed]
    if unknown:
        return None, [f"boss {entry}: registry calibrated, but neither the DB nor runtime swings confirm it"
                      for entry in unknown]
    return True, []


def encounter_fidelity(route_manifest: Mapping[str, Any] | None, registry: Mapping[str, Any] | None,
                       fetch_rows: RowSource | None, *, combat_log: Mapping[str, Any] | None = None,
                       combat_analysis: Mapping[str, Any] | None = None, difficulty: str | None = None,
                       root: Path = REPO_ROOT, basis: str = "harness") -> dict[str, Any]:
    pre = preflight(route_manifest, registry, fetch_rows, difficulty=difficulty)
    bosses = {row["entry"]: row for row in pre["entries"] if row["role"] == "boss"}
    melee, others = boss_melee(combat_log, bosses, registry, combat_analysis=combat_analysis, root=root)
    blizzlike, reasons = fidelity_verdict(pre, melee)
    return {"schema": FIDELITY_SCHEMA, "informational": True, "basis": basis, "registry": REGISTRY_PATH.as_posix(),
            "blizzlike": blizzlike, "reasons": reasons, "preflight": pre, "boss_melee": melee,
            "creature_melee": others}


def attach_encounter_fidelity(report: dict[str, Any], route_manifest: Mapping[str, Any] | None,
                              worldserver_conf: Path | str | None, *, root: Path = REPO_ROOT,
                              fetch_rows: RowSource | None = None, difficulty: str | None = None) -> dict[str, Any]:
    """Harness hook: report["encounter_fidelity"] and combat_analysis["encounter_fidelity"]. Never raises."""
    try:
        try:
            registry: Mapping[str, Any] = load_registry(root)
            registry_error = None
        except (OSError, ValueError) as error:
            registry, registry_error = {"creatures": {}}, f"{type(error).__name__}: {error}"
        source_error = None
        if fetch_rows is None and worldserver_conf and engaged_entries(route_manifest):
            try:
                fetch_rows = mysql_row_source(Path(worldserver_conf))
            except KeyboardInterrupt:
                raise
            except BaseException as error:  # a missing config key raises SystemExit
                source_error = f"{type(error).__name__}: {error}"
        combat_log = report.get("combat_log") if isinstance(report.get("combat_log"), Mapping) else None
        analysis = report.get("combat_analysis") if isinstance(report.get("combat_analysis"), Mapping) else None
        result = encounter_fidelity(route_manifest, registry, fetch_rows, combat_log=combat_log,
                                    combat_analysis=analysis, difficulty=difficulty, root=root)
        if source_error:
            result["preflight"].update(status="db_unavailable", db_error=source_error)
        if registry_error:
            result["registry_error"] = registry_error
    except KeyboardInterrupt:
        raise
    except BaseException as error:  # informational: a bug here must not cost the run its report
        result = {"schema": FIDELITY_SCHEMA, "informational": True, "status": "error",
                  "error": f"{type(error).__name__}: {error}", "blizzlike": None, "reasons": []}
    report["encounter_fidelity"] = result
    if isinstance(report.get("combat_analysis"), dict) and report["combat_analysis"]:
        report["combat_analysis"]["encounter_fidelity"] = {
            key: result[key] for key in ("schema", "informational", "blizzlike", "reasons", "boss_melee",
                                         "creature_melee") if key in result}
    return result


# --- scoreboard helpers ---------------------------------------------------------------------------

def scoreboard_summary(fidelity: Mapping[str, Any] | None, basis: str | None = None) -> dict[str, Any] | None:
    """Compact per-kill fidelity status: blizzlike, reasons and each boss's after-attacker mean vs WCL."""
    if not isinstance(fidelity, Mapping) or fidelity.get("schema") != FIDELITY_SCHEMA:
        return None
    bosses = {}
    for entry, stats in (fidelity.get("boss_melee") or {}).items():
        wcl = stats.get("wcl_comparison") or {}
        bosses[str(entry)] = {
            "name": stats.get("name"), "swings": stats.get("swings"),
            "after_attacker_mean": ((stats.get("stages") or {}).get(WCL_STAGE) or {}).get("mean"),
            "wcl_mean": wcl.get("u_mean"), "wcl_mean_basis": wcl.get("mean_basis"),
            "mean_ratio": (wcl.get("ratios") or {}).get("mean"), "wcl_flags": wcl.get("flags"),
            "runtime_damage_modifier": (stats.get("runtime_template") or {}).get("damage_modifier"),
            "registry_damage_modifier": (stats.get("registry") or {}).get("damage_modifier"),
        }
    return {"blizzlike": fidelity.get("blizzlike"), "reasons": list(fidelity.get("reasons") or []),
            "basis": basis or fidelity.get("basis"), "bosses": bosses}


def fidelity_from_run_dir(run_dir: Path, *, report: Mapping[str, Any] | None = None, root: Path = REPO_ROOT,
                          fetch_rows: RowSource | None = None) -> dict[str, Any] | None:
    """The harness block when the report has one; otherwise recomputed from combat_log.json (no DB)."""
    run_dir = Path(run_dir)
    if report is None:
        report = json.loads((run_dir / "report.json").read_text())
    if isinstance(report.get("encounter_fidelity"), Mapping) and report["encounter_fidelity"].get("schema") == FIDELITY_SCHEMA:
        return dict(report["encounter_fidelity"])
    log_path = run_dir / "combat_log.json"
    if not log_path.exists():
        return None
    manifest = report.get("validation_route_manifest")
    if not manifest and (run_dir / "validation_route_manifest.json").exists():
        manifest = json.loads((run_dir / "validation_route_manifest.json").read_text())
    analysis_path = run_dir / "combat_analysis.json"
    analysis = json.loads(analysis_path.read_text()) if analysis_path.exists() else report.get("combat_analysis")
    return encounter_fidelity(manifest, load_registry(root), fetch_rows, combat_log=json.loads(log_path.read_text()),
                              combat_analysis=analysis, root=root,
                              basis="combat_log_recomputed" + ("" if fetch_rows else "_without_db"))


# --- CLI ------------------------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight", help="classify a route manifest's creature entries (read-only DB)")
    pre.add_argument("--route-manifest", type=Path, required=True)
    pre.add_argument("--config", type=Path, required=True, help="worldserver config with WorldDatabaseInfo")
    pre.add_argument("--difficulty", help="10N, 25N, 10H or 25H; default from the manifest")
    run = sub.add_parser("run-dir", help="recompute encounter_fidelity for a closed run directory")
    run.add_argument("run_dir", type=Path)
    run.add_argument("--config", type=Path, help="also read creature_template (read-only)")
    args = parser.parse_args(argv)
    if args.command == "preflight":
        manifest = json.loads(args.route_manifest.read_text())
        result = preflight(manifest, load_registry(REPO_ROOT), mysql_row_source(args.config), difficulty=args.difficulty)
    else:
        result = fidelity_from_run_dir(args.run_dir, fetch_rows=mysql_row_source(args.config) if args.config else None)
    json.dump(result, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
