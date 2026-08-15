from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from math import hypot, isfinite
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
from typing import Any

try:
    from tools.raid_program.capture_no_bots_baseline import process_sample as _baseline_process_sample
except ModuleNotFoundError:
    # Direct execution places tools/raid_program, not the repository root, on
    # sys.path. Keep the CLI and imported test/module paths on the same sampler.
    from capture_no_bots_baseline import process_sample as _baseline_process_sample


ROOT = Path(__file__).resolve().parents[2]


def process_resource_sample(
    pid: int,
    *,
    sample_sequence: int,
    scenario_id: str,
    runtime_profile: str,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retain a compact, identity-bound worldserver resource sample.

    The baseline sampler is the source of truth for `/proc` parsing and CPU
    tick/RSS units.  Only those process fields are retained here; host load,
    memory pressure, and other baseline diagnostics are intentionally not
    copied into the raid telemetry stream.  Runtime identity is attached to
    every row so a later report cannot accidentally join samples from another
    cohort or attempt.
    """
    baseline = _baseline_process_sample(pid)
    runtime = status.get("raid_runtime") if isinstance(status, dict) else None
    runtime = runtime if isinstance(runtime, dict) else {}
    identity: dict[str, Any] = {
        "scenario_id": scenario_id,
        "runtime_profile": runtime_profile,
    }
    if isinstance(status, dict) and status.get("cohort_id") is not None:
        identity["cohort_id"] = status["cohort_id"]
    for field in (
        "server_epoch", "attempt_id", "profile_generation", "profile_content_hash",
        "assignment_generation", "group_guid", "leader_guid", "instance_id",
        "lockout_save_id",
    ):
        value = runtime.get(field)
        if value is not None:
            identity[field] = value
    return {
        "sample_sequence": sample_sequence,
        "process_pid": pid,
        "monotonic_sec": baseline["monotonic_sec"],
        "process_cpu_ticks": baseline["process_cpu_ticks"],
        "process_rss_bytes": baseline["process_rss_bytes"],
        "run_identity": identity,
    }


def summarize_process_resource_samples(
    samples: list[dict[str, Any]], *, tick_rate: int | None = None,
    sampling_errors: list[str] | None = None,
    sampling_error_count: int | None = None,
) -> dict[str, Any]:
    """Summarize retained process samples without copying them into telemetry.

    CPU percentage intentionally matches ``capture_no_bots_baseline``:
    process CPU time divided by wall time, expressed as a percentage of one
    logical core.  A mixed-PID sample set fails closed for CPU delta rather
    than attributing a reused PID to the raid.
    """
    errors = sampling_errors or []
    error_count = len(errors) if sampling_error_count is None else sampling_error_count
    if not samples:
        return {
            "sample_count": 0,
            "process_pid": None,
            "pid_consistent": False,
            "elapsed_seconds": 0.0,
            "cpu_ticks_delta": None,
            "tick_rate": tick_rate,
            "mean_cpu_percent_one_core": None,
            "maximum_rss_bytes": None,
            "minimum_rss_bytes": None,
            "sampling_error_count": error_count,
        }
    pids = [int(row["process_pid"]) for row in samples]
    pid_consistent = len(set(pids)) == 1
    first_time = float(samples[0]["monotonic_sec"])
    last_time = float(samples[-1]["monotonic_sec"])
    elapsed = max(0.0, last_time - first_time)
    ticks_delta = None
    mean_cpu = None
    if pid_consistent and len(samples) > 1:
        ticks_delta = int(samples[-1]["process_cpu_ticks"]) - int(samples[0]["process_cpu_ticks"])
        if tick_rate and tick_rate > 0 and elapsed > 0:
            mean_cpu = round((ticks_delta / tick_rate) / elapsed * 100, 3)
    rss_values = [int(row["process_rss_bytes"]) for row in samples]
    return {
        "sample_count": len(samples),
        "process_pid": pids[0] if pid_consistent else None,
        "pid_consistent": pid_consistent,
        "first_monotonic_sec": round(first_time, 6),
        "last_monotonic_sec": round(last_time, 6),
        "elapsed_seconds": round(elapsed, 3),
        "cpu_ticks_delta": ticks_delta,
        "tick_rate": tick_rate,
        "mean_cpu_percent_one_core": mean_cpu,
        "maximum_rss_bytes": max(rss_values),
        "minimum_rss_bytes": min(rss_values),
        "sampling_error_count": error_count,
    }


def _frozen_drudge_member_anchors(
    route_manifest: Path | None = None,
) -> dict[int, tuple[float, float, float]]:
    """Load reviewed per-slot Drudge geometry from a sealed route manifest.

    Production capture passes the exact generated manifest selected and hashed
    by ``validate_runtime_profile_assets``.  The default exists only for the
    pure verifier tests; live capture must never re-read the mutable controller
    checkout after binding a different worktree.
    """
    try:
        manifest = route_manifest or (
            ROOT / "dataset/validation_scenarios/validation_routes.jsonl"
        )
        rows = [
            json.loads(line)
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_scenario: list[dict[int, tuple[float, float, float]]] = []
        for scenario_id in (
            "blackwing_descent_10n",
            "blackwing_descent_10n_magmaw_diagnostic",
        ):
            node = next(
                row for row in rows
                if row.get("scenario_id") == scenario_id
                and row.get("mechanic_profile") == "trash_two_tank_charge_lanes"
            )
            anchors = {
                int(row["roster_slot"]): (
                    float(row["x"]), float(row["y"]), float(row["z"])
                )
                for row in node.get("split_member_anchors", [])
            }
            combat_tank_anchors = {
                int(row["roster_slot"]): (
                    float(row["x"]), float(row["y"]), float(row["z"])
                )
                for row in node.get("split_tank_combat_anchors", [])
            }
            navigation_tank_anchors = {
                int(row["roster_slot"]): (
                    float(row["x"]), float(row["y"]), float(row["z"])
                )
                for row in node.get("split_tank_navigation_anchors", [])
            }
            if (set(anchors) != set(range(1, 11)) or (
                node.get("boss_recovery_policy") != "native_full_wipe_only"
            ) or set(combat_tank_anchors) != {1, 2}
                    or set(navigation_tank_anchors) != {1, 2}):
                return {}
            # The contract anchors prove conservative native chase geometry;
            # the separately sealed navigation anchors are exact Detour
            # terminals and therefore own the live tank arrival evidence.
            anchors.update(navigation_tank_anchors)
            by_scenario.append(anchors)
        return by_scenario[0] if by_scenario[0] == by_scenario[1] else {}
    except (OSError, KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
        return {}

IDENTITY_FIELDS = (
    "group_guid",
    "leader_guid",
    "expected_size",
    "expected_difficulty",
    "group_difficulty",
    "map_difficulty",
    "map_id",
    "instance_id",
    "lockout_save_id",
    "server_epoch",
    "attempt_id",
    "profile_generation",
    "profile_content_hash",
    "assignment_generation",
)
STRATEGY_FIELD = "strategy_id"
ROSTER_ID_FIELDS = (
    "roster_slot_id", "lease_role_slot", "slot", "guid", "subgroup", "role",
    "class_id", "class_spec", "gear_identity", "active", "lease_owned",
    "account_id", "account", "name", "talents", "glyphs", "gear_identity_manifest",
)
# The roster's membership/assignment identity is immutable for a run, while
# ``active`` and ``lease_owned`` are live lifecycle state.  Deaths and native
# recovery legitimately change the latter in status/diagnose/trace envelopes;
# treating those flags as membership identity made telemetry from a partial
# wipe look like a cross-shard row.  Keep the full roster contract above for
# provisioning/acceptance, but demultiplex telemetry against this frozen
# membership projection and validate the lifecycle flags separately.
ROSTER_BINDING_ID_FIELDS = tuple(
    field for field in ROSTER_ID_FIELDS if field not in ("active", "lease_owned")
)
FORBIDDEN_ASSISTANCE_FIELDS = (
    "forbidden_completion_assists",
    "forbidden_assistance",
    "teacher_assisted",
    "encounter_state_injection",
    "forced_kill",
    "direct_resurrection",
    "combat_teleport",
    "door_unlock",
    "npc_spawn_assist",
    "direct_resurrect",
    "admin_resurrection",
    "forced_resurrection",
    "forced_teleport",
    "fallback_action",
    "fallback_result",
    "soap_command",
    "operator_command",
    "publisher_command",
    "dvc_push",
)

# These markers are forbidden even when they occur in an otherwise innocuous
# trace row.  A status field such as ``recovery_state`` is not a command/event
# marker and is therefore intentionally not included in this scan.
FORBIDDEN_MARKER_FIELDS = {
    "action", "event", "event_name", "result", "result_code", "command",
    "command_name", "failure_reason", "mode", "recovery_mode", "source",
    "operator", "publisher", "transport", "assistance_mode",
}
FORBIDDEN_MARKER_RE = re.compile(
    r"(?:direct[ _-]*resurrect|admin[ _-]*(?:resurrect|revive)|"
    r"forced[ _-]*(?:resurrect|revive|teleport|move|kill|wipe|reset)|"
    r"(?:^|[ _-])teleport(?:$|[ _-])|(?:^|[ _-])fallback(?:$|[ _-])|"
    r"(?:^|[ _-])(?:soap|console|operator|publisher)(?:$|[ _-])|"
    r"dvc[ _-]*push)",
    re.IGNORECASE,
)

EXPECTED_BWD_ROUTE_IDENTITY = (
    (1, "regroup", "BWD entrance junction regroup", 0, "blackwing_descent_10n.start_position"),
    (2, "trash", "Magmaw Chainwielder trash", 42649, "250050"),
    (3, "trash", "Magmaw Drudge pair", 42362, "250140"),
    (4, "boss", "Magmaw", 41570, "@CGUID+8"),
    (5, "trash", "Omnotron Golem Sentries", 42800, "250049"),
    (6, "boss", "Omnotron Defense System", 42166, "script_summoned"),
    (7, "trash", "laboratory trash", 42803, "250119"),
    (8, "boss", "Maloriak", 41378, "@CGUID+69"),
    (9, "boss", "Atramedes", 41442, "native_instance_unlock"),
    (10, "boss", "Chimaeron", 43296, "@CGUID+70"),
    (11, "boss", "Nefarian", 41376, "native_instance_unlock"),
)

# These are the generated partitions in validation_scenarios_cata_001.json.
# Keep the capture gate tied to the generator's shard shape so an accidentally
# truncated or cross-shard route cannot be accepted merely because its last
# row happens to be a boss.
EXPECTED_BWD_ROUTE_PARTITION_COUNTS = {
    "blackwing_descent_10n": (11, 6),
    "blackwing_descent_10n_magmaw_diagnostic": (4, 1),
    "blackwing_descent_10n_omnotron_diagnostic": (3, 1),
    "blackwing_descent_10n_maloriak_diagnostic": (3, 1),
    "blackwing_descent_10n_atramedes_diagnostic": (2, 1),
    "blackwing_descent_10n_chimaeron_diagnostic": (2, 1),
    "blackwing_descent_10n_nefarian_diagnostic": (3, 1),
}


def expected_bwd_10n_roster(
    profile_name: str = "blackwing_descent_10n",
) -> tuple[tuple[str, str, int, str], ...]:
    scenario = {"id": profile_name, "bots": _provisioned_bwd_bots(profile_name)}
    role_counts: Counter[str] = Counter()
    expected: list[tuple[str, str, int, str]] = []
    for bot in scenario["bots"]:
        role = str(bot["role"])
        role_counts[role] += 1
        expected.append(
            (
                f"raid_{role}_{role_counts[role]}",
                role,
                int(bot["class"]),
                str(bot["class_spec"]),
            )
        )
    if len(expected) != 10 or role_counts != Counter({"tank": 2, "healer": 3, "dps": 5}):
        raise ValueError("frozen BWD 10N provisioning roster is invalid")
    return tuple(expected)


def _provisioned_bwd_bots(profile_name: str = "blackwing_descent_10n") -> list[dict[str, Any]]:
    """Load the checked-in, post-normalization BWD provisioning roster.

    The capture verifier must not silently fall back to a partial roster when
    provisioning data is unavailable.  The builder's loader is used here so
    talent defaults and the checked-in gear profile overlay are represented by
    the same canonical values that generated the provisioning SQL.
    """

    try:
        from tools.bot_ml.build_validation_provisioning import (
            DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE,
            apply_gear_profiles,
            load_config_with_bwd_diagnostic_shards,
            load_gear_profiles,
        )

        config = load_config_with_bwd_diagnostic_shards(
            ROOT / "experiments/configs/validation_provisioning_cata_001.json",
            DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE,
        )
        config = apply_gear_profiles(
            config,
            load_gear_profiles(ROOT / "dataset/validation_gear_profiles/profiles.json"),
        )
        scenario = next(
            row for row in config["scenarios"] if row.get("id") == profile_name
        )
        bots = scenario.get("bots")
        if not isinstance(bots, list) or len(bots) != 10:
            raise ValueError(f"frozen BWD provisioning roster is missing for {profile_name}")
        return [row for row in bots if isinstance(row, dict)]
    except (ImportError, KeyError, OSError, StopIteration, TypeError, ValueError) as error:
        raise ValueError(f"frozen BWD identity manifest unavailable for {profile_name}: {error}") from error


def _provisioned_bwd_10n_bots() -> list[dict[str, Any]]:
    """Backward-compatible canonical-roster accessor for existing callers."""

    return _provisioned_bwd_bots("blackwing_descent_10n")


def _canonical_int_list(values: Any) -> tuple[int, ...] | None:
    if not isinstance(values, list):
        return None
    result: list[int] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("spell_id", value.get("id"))
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return None
        result.append(value)
    return tuple(result)


def _expected_identity_by_slot(
    profile_name: str = "blackwing_descent_10n",
) -> dict[str, dict[str, Any]]:
    from tools.bot_ml.build_validation_provisioning import normalized_glyph_slots

    result: dict[str, dict[str, Any]] = {}
    for bot in _provisioned_bwd_bots(profile_name):
        role = str(bot.get("role") or "")
        # Roster slot IDs are generated deterministically by the native plan.
        index = sum(1 for existing in result.values() if existing["role"] == role) + 1
        slot_id = str(bot.get("canonical_roster_slot_id") or f"raid_{role}_{index}")
        raw_talents = _canonical_int_list([row.get("spell_id") for row in bot.get("talents", [])])
        talents = tuple(sorted(raw_talents)) if raw_talents is not None else None
        glyphs = _canonical_int_list(
            [value for value in normalized_glyph_slots(bot) if int(value) > 0]
        )
        equipment = bot.get("equipment")
        if not isinstance(equipment, list) or not equipment:
            raise ValueError(f"frozen gear manifest missing for {slot_id}")
        expected_items = []
        for item in equipment:
            if not isinstance(item, dict) or int(item.get("slot", -1)) < 0 or int(item.get("item_id") or 0) <= 0:
                raise ValueError(f"frozen gear manifest invalid for {slot_id}")
            expected_items.append(
                {
                    "slot": int(item["slot"]),
                    "entry": int(item["item_id"]),
                    "enchant_id": int(item.get("enchant_id") or 0),
                    "gem_item_ids": tuple(int(value) for value in item.get("gem_item_ids", [])),
                    "reforge_id": int(item.get("reforge_id") or 0),
                }
            )
        if talents is None or glyphs is None:
            raise ValueError(f"frozen talent/glyph manifest missing for {slot_id}")
        result[slot_id] = {
            "account": str(bot.get("account") or "").upper(),
            "account_id": bot.get("expected_account_id", bot.get("account_id")),
            "character_guid": bot.get("expected_character_guid", bot.get("character_guid")),
            "name": str(bot.get("name") or ""),
            "role": role,
            "class_id": int(bot.get("class") or 0),
            "class_spec": str(bot.get("class_spec") or ""),
            "talents": talents,
            "glyphs": glyphs,
            "gear": tuple(sorted(expected_items, key=lambda row: row["slot"])),
        }
    return result


def _runtime_gear_manifest(row: dict[str, Any]) -> tuple[tuple[Any, ...], ...] | None:
    value = row.get("gear_identity_manifest")
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        return None
    items: list[tuple[Any, ...]] = []
    for item in value["items"]:
        if not isinstance(item, dict):
            return None
        guid = item.get("guid")
        entry = item.get("entry", item.get("item_entry"))
        if not _positive_int(guid) or not _positive_int(entry):
            return None
        gem_ids = item.get("gem_item_ids", [])
        if not isinstance(gem_ids, list) or any(not _nonnegative_int(gem) for gem in gem_ids):
            return None
        items.append(
            (
                int(item.get("slot", -1)), int(guid), int(entry),
                int(item.get("enchant_id") or 0), tuple(int(gem) for gem in gem_ids),
                int(item.get("reforge_id") or 0),
            )
        )
    if len({item[0] for item in items}) != len(items) or len({item[1] for item in items}) != len(items):
        return None
    return tuple(sorted(items))


def _identity_manifest_rejections(
    runtime: dict[str, Any],
    profile_name: str = "blackwing_descent_10n",
) -> list[str]:
    """Check all identity-bearing provisioning fields, fail-closed on omission."""

    try:
        expected_by_slot = _expected_identity_by_slot(profile_name)
    except ValueError:
        return ["frozen_identity_manifest_unavailable"]
    roster = runtime.get("roster")
    if not isinstance(roster, list):
        return ["frozen_identity_manifest_missing"]
    reasons: list[str] = []
    for row in roster:
        if not isinstance(row, dict):
            continue
        slot_id = str(row.get("roster_slot_id") or "")
        expected = expected_by_slot.get(slot_id)
        if expected is None:
            reasons.append("frozen_identity_unknown_roster_slot")
            continue
        for field in ("account", "name", "talents", "glyphs"):
            if field not in row:
                reasons.append(f"frozen_identity_{field}_missing")
        if not _positive_int(row.get("guid")):
            reasons.append("frozen_identity_guid_missing")
        if expected.get("character_guid") is not None and row.get("guid") != expected["character_guid"]:
            reasons.append("frozen_identity_character_guid_mismatch")
        if expected.get("account_id") is not None and row.get("account_id") != expected["account_id"]:
            reasons.append("frozen_identity_account_id_mismatch")
        if str(row.get("account") or "").upper() != expected["account"]:
            reasons.append("frozen_identity_account_mismatch")
        if row.get("name") != expected["name"]:
            reasons.append("frozen_identity_name_mismatch")
        actual_talents = _canonical_int_list(row.get("talents"))
        if actual_talents is None or tuple(sorted(actual_talents)) != expected["talents"]:
            reasons.append("frozen_identity_talents_mismatch")
        if _canonical_int_list(row.get("glyphs")) != expected["glyphs"]:
            reasons.append("frozen_identity_glyphs_mismatch")
        actual_gear = _runtime_gear_manifest(row)
        if actual_gear is None:
            reasons.append("frozen_identity_full_gear_manifest_missing")
        else:
            expected_gear = expected["gear"]
            actual_by_slot = {item[0]: item for item in actual_gear}
            if set(actual_by_slot) != {item["slot"] for item in expected_gear}:
                reasons.append("frozen_identity_full_gear_slots_mismatch")
            for item in expected_gear:
                actual = actual_by_slot.get(item["slot"])
                if actual is None:
                    continue
                if actual[2] != item["entry"]:
                    reasons.append("frozen_identity_gear_entry_mismatch")
                if actual[3] != item["enchant_id"] or actual[4] != item["gem_item_ids"] or actual[5] != item["reforge_id"]:
                    reasons.append("frozen_identity_gear_modifiers_mismatch")
    return list(dict.fromkeys(reasons))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_row_from_log_line(raw: bytes) -> dict[str, Any] | None:
    """Decode one complete worldserver log line when it contains JSON evidence."""

    start = raw.find(b"{")
    end = raw.rfind(b"}")
    if start < 0 or end < start:
        return None
    try:
        row = json.loads(raw[start : end + 1])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return row if isinstance(row, dict) else None


class JsonLogCursor:
    """Incrementally parse complete evidence lines from an append-only log.

    The canonical monitor used to reread and decode the complete growing log on
    every five-second probe.  That made parsing O(n^2) over a long uncapped
    run, while adding no evidence.  This cursor reads each byte once during
    monitoring and retains an incomplete final line until the next probe.  The
    final immutable artifact is still parsed from the complete log below, so
    this optimization cannot remove or rewrite a transition row.
    """

    def __init__(self, path: Path):
        self.path = path
        self.offset = 0
        self._partial = b""

    def read_new_rows(self) -> list[dict[str, Any]]:
        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            chunk = handle.read()
            self.offset = handle.tell()
        if not chunk:
            return []

        data = self._partial + chunk
        lines = data.splitlines(keepends=True)
        if lines and not lines[-1].endswith((b"\n", b"\r")):
            self._partial = lines.pop()
        else:
            self._partial = b""
        rows: list[dict[str, Any]] = []
        for raw in lines:
            row = _json_row_from_log_line(raw)
            if row is not None:
                rows.append(row)
        return rows


def json_actions(log_bytes: bytes, action: str) -> list[dict[str, Any]]:
    return [row for row in json_rows(log_bytes) if row.get("action") == action]


def json_rows(log_bytes: bytes) -> list[dict[str, Any]]:
    """Parse only complete JSON objects, retaining their log order."""

    rows: list[dict[str, Any]] = []
    for raw in log_bytes.splitlines():
        row = _json_row_from_log_line(raw)
        if row is not None:
            rows.append(row)
    return rows


def action_payloads(rows: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    """Project already-parsed normalized evidence without reparsing its log."""

    payloads: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, dict) and payload.get("action") == action:
            payloads.append(payload)
    return payloads


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _runtime_identity(runtime: dict[str, Any], *, include_strategy: bool = False) -> tuple[Any, ...] | None:
    fields = IDENTITY_FIELDS + ((STRATEGY_FIELD,) if include_strategy else ())
    if not all(field in runtime for field in fields):
        return None
    return tuple(runtime[field] for field in fields)


def _roster_identity(roster: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...] | None:
    if len(roster) != 10 or any(not isinstance(row, dict) for row in roster):
        return None
    rows: list[tuple[Any, ...]] = []
    for row in sorted(roster, key=lambda value: value.get("slot") if isinstance(value.get("slot"), int) else -1):
        if any(field not in row for field in ROSTER_ID_FIELDS):
            return None
        rows.append(tuple(row[field] for field in ROSTER_ID_FIELDS))
    return tuple(rows)


def _roster_binding_identity(roster: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...] | None:
    """Return immutable roster membership used to demultiplex live channels."""

    if len(roster) != 10 or any(not isinstance(row, dict) for row in roster):
        return None
    rows: list[tuple[Any, ...]] = []
    for row in sorted(roster, key=lambda value: value.get("slot") if isinstance(value.get("slot"), int) else -1):
        if any(field not in row for field in ROSTER_BINDING_ID_FIELDS):
            return None
        rows.append(tuple(row[field] for field in ROSTER_BINDING_ID_FIELDS))
    return tuple(rows)


def _roster_binding_lifecycle_rejections(roster: Any) -> list[str]:
    """Reject malformed lease/lifecycle claims without treating death as drift."""

    if not isinstance(roster, list) or len(roster) != 10:
        return ["roster_binding_shape_invalid"]
    rows = [row for row in roster if isinstance(row, dict)]
    reasons: list[str] = []
    if len(rows) != len(roster):
        return ["roster_binding_row_invalid"]
    # Producers may serialize the map-backed roster in GUID order rather than
    # slot order.  Membership identity is canonicalized by slot above, so the
    # lifecycle check must be order-independent as well.
    slots = sorted(row.get("slot") for row in rows)
    if slots != list(range(10)):
        reasons.append("roster_binding_slots_invalid")
    for row in rows:
        if not isinstance(row.get("active"), bool):
            reasons.append("roster_binding_active_invalid")
        if row.get("lease_owned") is not True:
            reasons.append("roster_binding_lease_invalid")
    return sorted(set(reasons))


def _roster_rejections(
    runtime: dict[str, Any],
    profile_name: str = "blackwing_descent_10n",
) -> list[str]:
    roster = runtime.get("roster")
    if not isinstance(roster, list):
        return ["roster_not_a_list"]
    reasons: list[str] = []
    if len(roster) != 10:
        reasons.append("exact_roster")
    rows = [row for row in roster if isinstance(row, dict)]
    if len(rows) != len(roster):
        reasons.append("roster_rows_are_not_objects")
    rows.sort(key=lambda row: row.get("slot") if isinstance(row.get("slot"), int) else -1)
    slots = [row.get("slot") for row in rows]
    if slots != list(range(10)):
        reasons.append("deterministic_slots")
    roster_ids = [row.get("roster_slot_id") for row in rows]
    if any(not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip() for value in roster_ids):
        reasons.append("stable_roster_slot_ids")
    if len(set(roster_ids)) != 10:
        reasons.append("unique_roster_slot_ids")
    if any(row.get("roster_slot_id") == row.get("guid") for row in rows):
        # A numeric GUID is not a roster slot identity.  Distinct identities
        # must be present even when a producer happens to serialize numbers.
        reasons.append("roster_slot_id_not_guid_identity")
    if any(row.get("lease_role_slot") != row.get("roster_slot_id") for row in rows):
        reasons.append("lease_role_slot_identity_mismatch")
    if any(not _positive_int(row.get("class_id")) for row in rows):
        reasons.append("class_identity_missing")
    if any(not isinstance(row.get("class_spec"), str) or not row["class_spec"].strip() for row in rows):
        reasons.append("class_spec_identity_missing")
    if any(not isinstance(row.get("gear_identity"), str) or not row["gear_identity"].strip() for row in rows):
        reasons.append("gear_identity_missing")
    if [row.get("subgroup") for row in rows] != [0] * 5 + [1] * 5:
        reasons.append("deterministic_subgroups")
    guids = [row.get("guid") for row in rows]
    if any(not _positive_int(guid) for guid in guids):
        reasons.append("positive_roster_guids")
    if len(set(guids)) != 10:
        reasons.append("unique_roster_guids")
    roles = Counter(row.get("role") for row in rows)
    if roles != Counter({"tank": 2, "healer": 3, "dps": 5}):
        reasons.append("exact_10n_role_composition")
    observed_roster = tuple(
        (
            str(row.get("roster_slot_id")), str(row.get("role")),
            row.get("class_id"), str(row.get("class_spec")),
        )
        for row in rows
    )
    if observed_roster != expected_bwd_10n_roster(profile_name):
        reasons.append("exact_frozen_bwd_10n_roster_identity")
    if not all(row.get("active") is True for row in rows):
        reasons.append("all_roster_active")
    if not all(row.get("lease_owned") is True for row in rows):
        reasons.append("all_roster_leases_owned")
    reasons.extend(_identity_manifest_rejections(runtime, profile_name))
    return reasons


def accepted_foundation_status(
    status: dict[str, Any],
    *,
    profile_name: str = "blackwing_descent_10n",
    route_partition: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    runtime = status.get("raid_runtime") or {}
    reasons: list[str] = []
    if not isinstance(runtime, dict):
        return False, ["raid_runtime_missing"]
    route_progress = runtime.get("route_progress")
    # Phase 1's canonical foundation gate stops at Magmaw. An explicit boss
    # shard instead targets the terminal node of its own generated partition.
    route_partition = route_partition or {}
    if profile_name == "blackwing_descent_10n":
        expected_route_generation = 4
        expected_route_index = 3
    else:
        expected_route_generation = int(route_partition.get("node_count") or 0)
        expected_route_index = int(route_partition.get("terminal_index") or 0)
    expected_strategy = profile_name
    checks = {
        "status_ok": status.get("ok") is True,
        "ten_bots": status.get("bots") == 10,
        "ten_leases": status.get("lease_count") == 10,
        "runtime_active": runtime.get("active") is True,
        "expected_size_10": runtime.get("expected_size") == 10,
        "active_size_10": runtime.get("active_size") == 10,
        "alive_size_10": runtime.get("alive_size") == 10,
        "roster_complete": runtime.get("roster_complete") is True,
        "difficulty_10n": runtime.get("expected_difficulty") == 0 and runtime.get("group_difficulty") == 0,
        "live_map_difficulty_10n": runtime.get("map_difficulty") == 0,
        "difficulty_matches": runtime.get("difficulty_matches") is True,
        "map_bwd": runtime.get("map_id") == 669,
        "instance_owned": _positive_int(runtime.get("instance_id")),
        "lockout_save_owned": _positive_int(runtime.get("lockout_save_id")),
        "lockout_save_matches_live_instance": runtime.get("lockout_save_id") == runtime.get("instance_id"),
        "group_owned": _positive_int(runtime.get("group_guid")),
        "leader_owned": _positive_int(runtime.get("leader_guid")),
        "server_epoch_owned": _positive_int(runtime.get("server_epoch")),
        "attempt_owned": _positive_int(runtime.get("attempt_id")),
        "profile_generation_owned": _positive_int(runtime.get("profile_generation")),
        "profile_content_hash_owned": isinstance(runtime.get("profile_content_hash"), str)
            and bool(runtime.get("profile_content_hash", "").strip()),
        "assignment_generation_owned": _positive_int(runtime.get("assignment_generation")),
        "strategy_owned": runtime.get("strategy_id") == expected_strategy,
        "boss_state_readback": len(runtime.get("boss_states") or []) == 6,
        "ready_check_satisfied": runtime.get("ready_check_satisfied") is True,
        "roster_composition_valid": runtime.get("roster_composition_valid") is True,
        "evidence_sequence_owned": _positive_int(runtime.get("evidence_sequence")),
        "unique_leases": runtime.get("unique_leases") is True,
        "selected_route_terminal_node": isinstance(route_progress, dict)
            and route_progress.get("generation") == expected_route_generation
            and route_progress.get("node_index") == expected_route_index,
    }
    reasons.extend(name for name, passed in checks.items() if not passed)
    reasons.extend(_roster_rejections(runtime, profile_name))
    roster = runtime.get("roster")
    roster_guids = {
        row.get("guid") for row in roster if isinstance(row, dict)
    } if isinstance(roster, list) else set()
    if runtime.get("leader_guid") not in roster_guids:
        reasons.append("leader_not_in_exact_roster")
    return not reasons, reasons


def terminal_runtime_failure_reason(
    status: dict[str, Any],
    *,
    profile_name: str = "blackwing_descent_10n",
) -> tuple[str | None, list[str]]:
    """Return an exact active-attempt failure without requiring success state.

    A terminal failure can legitimately have dead members, an incomplete
    route, and no ready check.  It must still be bound to the selected profile,
    exact leased roster, native group/instance, and active attempt before the
    capture controller is allowed to stop the shared worldserver.
    """

    runtime = status.get("raid_runtime")
    reason = status.get("failure_reason")
    rejections: list[str] = []
    if not isinstance(reason, str) or not reason.strip():
        return None, ["terminal_failure_reason_missing"]
    if not isinstance(runtime, dict):
        return None, ["terminal_failure_runtime_missing"]
    checks = {
        "terminal_failure_status_not_ok": status.get("ok") is True,
        "terminal_failure_action_mismatch": status.get("action") == "botauto_status",
        "terminal_failure_cohort_mismatch": status.get("cohort_id") == "default",
        "terminal_failure_profile_mismatch": status.get("active_profile") == profile_name,
        "terminal_failure_bot_count_mismatch": status.get("bots") == 10,
        "terminal_failure_lease_count_mismatch": status.get("lease_count") == 10,
        "terminal_failure_runtime_inactive": runtime.get("active") is True,
        "terminal_failure_expected_size_mismatch": runtime.get("expected_size") == 10,
        "terminal_failure_active_size_mismatch": runtime.get("active_size") == 10,
        "terminal_failure_roster_incomplete": runtime.get("roster_complete") is True,
        "terminal_failure_map_mismatch": runtime.get("map_id") == 669,
        "terminal_failure_instance_missing": _positive_int(runtime.get("instance_id")),
        "terminal_failure_group_missing": _positive_int(runtime.get("group_guid")),
        "terminal_failure_attempt_missing": _positive_int(runtime.get("attempt_id")),
        "terminal_failure_assignment_missing": _positive_int(runtime.get("assignment_generation")),
        "terminal_failure_unique_leases_missing": runtime.get("unique_leases") is True,
    }
    rejections.extend(name for name, passed in checks.items() if not passed)
    rejections.extend(
        f"terminal_failure_{item}" for item in _roster_rejections(runtime, profile_name)
    )
    return (reason.strip() if not rejections else None), list(dict.fromkeys(rejections))


def _route_advancement_marker(runtime: dict[str, Any]) -> int | None:
    """Return an explicit monotonic route-progress generation, if present."""

    candidates: list[Any] = [
        runtime.get("route_generation"),
        runtime.get("route_step"),
        runtime.get("route_node_index"),
        runtime.get("route_terminal_count"),
        runtime.get("route_progress_generation"),
    ]
    progress = runtime.get("route_progress")
    if isinstance(progress, dict):
        candidates.extend(
            progress.get(field)
            for field in ("generation", "route_generation", "step", "node_index", "terminal_count", "advancement")
        )
    values = [
        int(value) for value in candidates
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    return max(values) if values else None


def _validate_drudge_observation_geometry(
    observation: dict[str, Any],
    roster: list[dict[str, Any]],
    tank_guids: set[int],
    frozen_anchors: dict[int, tuple[float, float, float]] | None = None,
) -> list[str]:
    """Recompute the frozen two-lane geometry from immutable coordinates.

    The runtime's ``reseparation_recorded`` bit and lane-side booleans are
    claims, not acceptance evidence.  This verifier deliberately recomputes
    projections, source separation, tank ownership geometry, and every
    non-tank anchor from the serialized observation so a forged completion bit
    or crossed source cannot certify a capture.
    """

    geometry = observation.get("geometry")
    if not isinstance(geometry, dict):
        return ["drudge_observation_geometry_missing"]
    required = (
        "home0_x", "home0_y", "home1_x", "home1_y", "midpoint_x", "midpoint_y",
        "axis_x", "axis_y", "lane_separation", "minimum_distance", "navigation_margin",
        "source0_x", "source0_y", "source0_projection", "source0_lane_side_valid",
        "source0_health_pct",
        "source1_x", "source1_y", "source1_projection", "source1_lane_side_valid",
        "source1_health_pct",
        "source0_victim_guid", "source1_victim_guid",
        "source0_alive", "source1_alive",
        "source_separation", "minimum_source_separation", "minimum_member_spacing",
        "arrival_tolerance", "tank_arrival_tolerance", "members",
        "tank0_x", "tank0_y", "tank0_guid", "tank0_slot", "tank0_projection",
        "tank0_source_distance", "tank1_x", "tank1_y", "tank1_guid", "tank1_slot",
        "tank1_projection", "tank1_source_distance",
    )
    reasons: list[str] = []

    def number(name: str) -> float | None:
        value = geometry.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
            reasons.append(f"drudge_geometry_{name}_invalid")
            return None
        return float(value)

    boolean_fields = {
        "source0_lane_side_valid", "source1_lane_side_valid",
        "source0_alive", "source1_alive",
    }
    values = {
        name: number(name)
        for name in required
        if name not in boolean_fields and name != "members"
    }
    if any(value is None for value in values.values()):
        return sorted(set(reasons))
    tolerance = 0.05
    home_dx = values["home1_x"] - values["home0_x"]
    home_dy = values["home1_y"] - values["home0_y"]
    home_length = hypot(home_dx, home_dy)
    if home_length <= 0.001:
        reasons.append("drudge_geometry_home_axis_invalid")
        return sorted(set(reasons))
    expected_axis = (home_dx / home_length, home_dy / home_length)
    if hypot(values["axis_x"] - expected_axis[0], values["axis_y"] - expected_axis[1]) > tolerance:
        reasons.append("drudge_geometry_axis_mismatch")
    expected_midpoint = (
        (values["home0_x"] + values["home1_x"]) * 0.5,
        (values["home0_y"] + values["home1_y"]) * 0.5,
    )
    if hypot(values["midpoint_x"] - expected_midpoint[0], values["midpoint_y"] - expected_midpoint[1]) > tolerance:
        reasons.append("drudge_geometry_midpoint_mismatch")
    lane_sep = values["lane_separation"]
    minimum_source_sep = values["minimum_source_separation"]
    minimum_spacing = values["minimum_member_spacing"]
    arrival_tolerance = values["arrival_tolerance"]
    tank_arrival_tolerance = values["tank_arrival_tolerance"]
    if (lane_sep <= 0 or minimum_source_sep <= 0 or minimum_spacing <= 0
            or arrival_tolerance <= 0 or tank_arrival_tolerance <= 0
            or tank_arrival_tolerance > arrival_tolerance):
        reasons.append("drudge_geometry_threshold_invalid")
    # Frozen in validation_scenarios_cata_001.json, BWD step 3
    # (trash_two_tank_charge_lanes); these are contract values, not claims
    # copied from the runtime row.
    frozen_thresholds = {
        "minimum_source_separation": 15.0,
        "navigation_margin": 2.0,
        "lane_separation": 17.0,
        "minimum_distance": 15.0,
        "minimum_member_spacing": 3.0,
        "arrival_tolerance": 2.0,
        "tank_arrival_tolerance": 1.0,
    }
    for name, expected in frozen_thresholds.items():
        if abs(values[name] - expected) > tolerance:
            reasons.append(f"drudge_geometry_{name}_contract_mismatch")
    if abs(values["lane_separation"] - (
        values["minimum_source_separation"] + values["navigation_margin"]
    )) > tolerance:
        reasons.append("drudge_geometry_lane_separation_contract_mismatch")

    def projection(x: float, y: float) -> float:
        return ((x - values["midpoint_x"]) * values["axis_x"]
                + (y - values["midpoint_y"]) * values["axis_y"])

    source_positions = (
        (values["source0_x"], values["source0_y"], "source0"),
        (values["source1_x"], values["source1_y"], "source1"),
    )
    source_projections: list[float] = []
    for index, (x, y, prefix) in enumerate(source_positions):
        computed = projection(x, y)
        source_projections.append(computed)
        if abs(values[f"{prefix}_projection"] - computed) > tolerance:
            reasons.append(f"drudge_geometry_{prefix}_projection_mismatch")
        expected_side = ((-1.0 if index == 0 else 1.0) * computed
                         >= lane_sep * 0.25)
        if geometry.get(f"{prefix}_lane_side_valid") is not expected_side:
            reasons.append(f"drudge_geometry_{prefix}_lane_side_mismatch")
        if not expected_side:
            reasons.append(f"drudge_geometry_{prefix}_lane_side_unsafe")
        if not isinstance(geometry.get(f"{prefix}_alive"), bool):
            reasons.append(f"drudge_geometry_{prefix}_alive_invalid")
        health_pct = values[f"{prefix}_health_pct"]
        if health_pct < 0.0 or health_pct > 100.0:
            reasons.append(f"drudge_geometry_{prefix}_health_invalid")
        if geometry.get(f"{prefix}_alive") is not (health_pct > 0.0):
            reasons.append(f"drudge_geometry_{prefix}_alive_health_mismatch")
        if geometry.get(f"{prefix}_alive") is True and not _positive_int(geometry.get(f"{prefix}_victim_guid")):
            reasons.append(f"drudge_geometry_{prefix}_victim_missing")
        if geometry.get(f"{prefix}_alive") is False and geometry.get(f"{prefix}_victim_guid") not in (0, None):
            reasons.append(f"drudge_geometry_{prefix}_dead_victim_present")
    source_separation = hypot(
        values["source1_x"] - values["source0_x"],
        values["source1_y"] - values["source0_y"],
    )
    if abs(values["source_separation"] - source_separation) > tolerance:
        reasons.append("drudge_geometry_source_separation_mismatch")
    if source_separation < lane_sep:
        reasons.append("drudge_geometry_source_separation_unsafe")

    roster_by_guid = {
        row.get("guid"): row for row in roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    lane_a_slots = {1, 3, 4, 6, 7}
    expected_tank_by_slot = {
        int(row["slot"]) + 1: int(row["guid"])
        for row in roster
        if isinstance(row, dict) and row.get("role") == "tank"
        and _positive_int(row.get("guid"))
    }
    source_victims = {
        0: geometry.get("source0_victim_guid"),
        1: geometry.get("source1_victim_guid"),
    }
    for source_index, victim in source_victims.items():
        alive = geometry.get(f"source{source_index}_alive")
        expected_victim = expected_tank_by_slot.get(source_index + 1)
        if alive is True and (not _positive_int(victim) or victim != expected_victim):
            reasons.append(f"drudge_geometry_source{source_index}_victim_invalid")
        if alive is False and victim not in (0, None):
            reasons.append(f"drudge_geometry_source{source_index}_dead_victim_present")
    members = geometry.get("members")
    if not isinstance(members, list):
        reasons.append("drudge_geometry_members_missing")
        return sorted(set(reasons))
    member_by_guid = {
        row.get("guid"): row for row in members
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    if set(member_by_guid) != set(roster_by_guid) or len(members) != len(roster_by_guid):
        reasons.append("drudge_geometry_exact_members_missing")
    canonical_tanks = (
        ("tank0", values["tank0_guid"], values["tank0_slot"], 0,
         values["tank0_x"], values["tank0_y"], values["tank0_projection"], values["tank0_source_distance"]),
        ("tank1", values["tank1_guid"], values["tank1_slot"], 1,
         values["tank1_x"], values["tank1_y"], values["tank1_projection"], values["tank1_source_distance"]),
    )
    canonical_guids: set[int] = set()
    frozen_anchors = frozen_anchors or _frozen_drudge_member_anchors()
    if set(frozen_anchors) != set(range(1, 11)):
        reasons.append("drudge_geometry_frozen_member_anchors_missing")
    for prefix, guid_value, slot_value, source_index, x, y, stored_projection, stored_distance in canonical_tanks:
        raw_guid = geometry.get(f"{prefix}_guid")
        raw_slot = geometry.get(f"{prefix}_slot")
        if (not isinstance(raw_guid, int) or isinstance(raw_guid, bool) or raw_guid <= 0
                or not isinstance(raw_slot, int) or isinstance(raw_slot, bool) or raw_slot <= 0):
            reasons.append(f"drudge_geometry_{prefix}_identity_invalid")
            continue
        guid, slot = raw_guid, raw_slot
        canonical_guids.add(guid)
        expected_guid = expected_tank_by_slot.get(source_index + 1)
        if guid != expected_guid or slot != source_index + 1:
            reasons.append(f"drudge_geometry_{prefix}_identity_invalid")
        expected_anchor = frozen_anchors.get(source_index + 1)
        if (expected_anchor is None
                or hypot(x - expected_anchor[0], y - expected_anchor[1])
                > tank_arrival_tolerance):
            reasons.append(f"drudge_geometry_{prefix}_declared_anchor_mismatch")
        computed_projection = projection(x, y)
        if abs(stored_projection - computed_projection) > tolerance:
            reasons.append(f"drudge_geometry_{prefix}_projection_mismatch")
        source_x, source_y, _ = source_positions[source_index]
        distance = hypot(x - source_x, y - source_y)
        if abs(stored_distance - distance) > tolerance:
            reasons.append(f"drudge_geometry_{prefix}_source_distance_mismatch")
        if distance > minimum_source_sep:
            reasons.append(f"drudge_geometry_{prefix}_source_distance_unsafe")
        member = member_by_guid.get(guid)
        if not isinstance(member, dict):
            reasons.append(f"drudge_geometry_{prefix}_member_missing")
        else:
            for field, expected in (("x", x), ("y", y), ("projection", stored_projection)):
                observed = member.get(field)
                if (not isinstance(observed, (int, float)) or isinstance(observed, bool)
                        or not isfinite(observed) or abs(float(observed) - expected) > tolerance):
                    reasons.append(f"drudge_geometry_{prefix}_member_{field}_mismatch")
        if ((-1.0 if source_index == 0 else 1.0) * computed_projection
                < lane_sep * 0.25):
            reasons.append(f"drudge_geometry_{prefix}_lane_side_invalid")
    if hypot(values["tank1_x"] - values["tank0_x"], values["tank1_y"] - values["tank0_y"]) < minimum_source_sep:
        reasons.append("drudge_geometry_tank_pair_separation_unsafe")
    if canonical_guids != tank_guids:
        reasons.append("drudge_geometry_canonical_tanks_missing")

    non_tank_positions: dict[int, tuple[float, float, bool]] = {}
    for guid, roster_row in roster_by_guid.items():
        member = member_by_guid.get(guid)
        if not isinstance(member, dict):
            continue
        slot = roster_row.get("slot")
        expected_slot = int(slot) + 1 if isinstance(slot, int) and not isinstance(slot, bool) else -1
        if member.get("roster_slot") != expected_slot:
            reasons.append("drudge_geometry_member_slot_mismatch")
            continue
        def member_number(name: str) -> float | None:
            value = member.get(name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
                reasons.append(f"drudge_geometry_member_{name}_invalid")
                return None
            return float(value)
        x = member_number("x")
        y = member_number("y")
        stored_projection = member_number("projection")
        if x is None or y is None or stored_projection is None:
            continue
        computed_projection = projection(x, y)
        if abs(stored_projection - computed_projection) > tolerance:
            reasons.append("drudge_geometry_member_projection_mismatch")
        slot_one = expected_slot
        lane_a = slot_one in lane_a_slots
        side_valid = ((-1.0 if lane_a else 1.0) * computed_projection
                      >= lane_sep * 0.25)
        if member.get("lane_side_valid") is not side_valid:
            reasons.append("drudge_geometry_member_lane_side_mismatch")
        if not side_valid:
            reasons.append("drudge_geometry_member_lane_side_unsafe")
        if guid in tank_guids:
            continue
        non_tank_positions[guid] = (x, y, lane_a)
        source_distances = (
            hypot(x - values["source0_x"], y - values["source0_y"]),
            hypot(x - values["source1_x"], y - values["source1_y"]),
        )
        if any(distance < values["minimum_distance"] for distance in source_distances):
            reasons.append("drudge_geometry_member_source_distance_unsafe")
        if member.get("anchor_selected") is not True:
            reasons.append("drudge_geometry_member_anchor_missing")
        if member.get("anchor_path_valid") is not True:
            reasons.append("drudge_geometry_member_anchor_path_unverified")
        candidate_index = member.get("anchor_candidate_index")
        if not isinstance(candidate_index, int) or isinstance(candidate_index, bool) or candidate_index != 0:
            reasons.append("drudge_geometry_member_anchor_index_invalid")
            continue
        expected_anchor_xyz = frozen_anchors.get(slot_one)
        if expected_anchor_xyz is None:
            reasons.append("drudge_geometry_member_declared_anchor_missing")
            continue
        expected_anchor = expected_anchor_xyz[:2]
        stored_anchor = (member_number("anchor_x"), member_number("anchor_y"))
        if stored_anchor[0] is None or stored_anchor[1] is None:
            continue
        if hypot(stored_anchor[0] - expected_anchor[0], stored_anchor[1] - expected_anchor[1]) > tolerance:
            reasons.append("drudge_geometry_member_anchor_mismatch")
        anchor_distance = hypot(x - expected_anchor[0], y - expected_anchor[1])
        stored_distance = member_number("anchor_distance")
        if stored_distance is None or abs(stored_distance - anchor_distance) > tolerance:
            reasons.append("drudge_geometry_member_anchor_distance_mismatch")
        if anchor_distance > arrival_tolerance:
            reasons.append("drudge_geometry_member_anchor_unsafe")
        stored_base = (member_number("group_anchor_base_x"), member_number("group_anchor_base_y"))
        if stored_base[0] is None or stored_base[1] is None or hypot(
            stored_base[0] - expected_anchor[0], stored_base[1] - expected_anchor[1]
        ) > tolerance:
            reasons.append("drudge_geometry_member_anchor_base_mismatch")

    for guid, (x, y, lane_a) in non_tank_positions.items():
        same_lane = [
            hypot(x - other_x, y - other_y)
            for other_guid, (other_x, other_y, other_lane_a) in non_tank_positions.items()
            if other_guid != guid and other_lane_a == lane_a
        ]
        nearest = min(same_lane) if same_lane else 0.0
        member = member_by_guid[guid]
        stored_nearest = member.get("nearest_same_lane_distance")
        if not isinstance(stored_nearest, (int, float)) or isinstance(stored_nearest, bool) or not isfinite(stored_nearest) or abs(float(stored_nearest) - nearest) > tolerance:
            reasons.append("drudge_geometry_member_spacing_measurement_mismatch")
        spacing_valid = not same_lane or nearest >= minimum_spacing
        if member.get("same_lane_spacing_valid") is not spacing_valid:
            reasons.append("drudge_geometry_member_spacing_invalid")
        if not spacing_valid:
            reasons.append("drudge_geometry_member_spacing_unsafe")
    return sorted(set(reasons))


def accepted_drudge_contract(
    statuses: list[dict[str, Any]],
    *,
    frozen_anchors: dict[int, tuple[float, float, float]] | None = None,
) -> tuple[bool, list[str]]:
    """Reconstruct the exact two-lane Drudge contract from native evidence.

    Stored counters and booleans are corroboration only. Acceptance is derived
    from the retained delivered observations, their exact source/target/scope,
    their per-roster reseparation acknowledgements, and the frozen role slots.
    """

    reasons: list[str] = []
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for status in statuses:
        runtime = status.get("raid_runtime") if isinstance(status, dict) else None
        evidence = runtime.get("drudge_charge") if isinstance(runtime, dict) else None
        if isinstance(evidence, dict) and evidence.get("evidence_route_generation") == 3:
            candidates.append((runtime, evidence))
    if not candidates:
        return False, ["drudge_evidence_missing"]

    def candidate_key(pair: tuple[dict[str, Any], dict[str, Any]]) -> tuple[int, int, int, int, int]:
        candidate_runtime, candidate_evidence = pair
        observations = candidate_evidence.get("observations")
        observations = observations if isinstance(observations, list) else []
        delivered_rows = [row for row in observations if isinstance(row, dict) and row.get("landed") is True]
        source_counts = Counter(row.get("source_spawn_id") for row in delivered_rows)
        roster_rows = candidate_runtime.get("roster")
        roster_set = {
            row.get("guid") for row in roster_rows
            if isinstance(row, dict) and _positive_int(row.get("guid"))
        } if isinstance(roster_rows, list) else set()
        tank_set = {
            row.get("guid") for row in roster_rows
            if isinstance(row, dict) and row.get("role") == "tank"
            and _positive_int(row.get("guid"))
        } if isinstance(roster_rows, list) else set()
        offensive_set = {
            row.get("guid") for row in roster_rows
            if isinstance(row, dict) and row.get("role") in {"tank", "dps"}
            and _positive_int(row.get("guid"))
        } if isinstance(roster_rows, list) else set()
        threat_seed = candidate_runtime.get("drudge_threat_seed")
        threat_seed_complete = (
            isinstance(threat_seed, dict)
            and threat_seed.get("closed") is True
            and threat_seed.get("complete") is True
            and threat_seed.get("failure") is False
        )
        def exact_set(field: str) -> set[int]:
            values = candidate_evidence.get(field)
            return set(values) if isinstance(values, list) and all(_positive_int(value) for value in values) else set()
        complete = int(
            len(delivered_rows) >= 4
            and source_counts.get(250140, 0) >= 2
            and source_counts.get(250141, 0) >= 2
            and all(isinstance(row.get("geometry"), dict) for row in delivered_rows)
            and exact_set("ownership_roster_guids") == tank_set
            and exact_set("health_sync_evaluated_roster_guids") == tank_set
            and exact_set("profile_action_roster_guids") == offensive_set
            and exact_set("health_sync_roster_guids")
            and exact_set("health_sync_roster_guids").issubset(tank_set)
            and candidate_evidence.get("health_sync_hold_source_spawn_id") in {250140, 250141}
            and _positive_int(candidate_evidence.get("health_sync_hold_tank_guid"))
            and _positive_int(candidate_evidence.get("death_evidence_sequence"))
            and _positive_int(candidate_evidence.get("rage_wait_evidence_sequence"))
            and _positive_int(candidate_evidence.get("rage_aura_evidence_sequence"))
            and threat_seed_complete
        )
        latest_observation = max(
            (int(row.get("sequence") or 0) for row in delivered_rows), default=0
        )
        evidence_sequence = int(candidate_runtime.get("evidence_sequence") or 0)
        return (
            complete,
            latest_observation,
            evidence_sequence,
            int(candidate_evidence.get("delivered_count") or 0),
            int(candidate_evidence.get("prepared_count") or 0),
        )

    _, (runtime, evidence) = max(
        enumerate(candidates), key=lambda indexed: (candidate_key(indexed[1]), indexed[0])
    )
    roster = runtime.get("roster")
    if not isinstance(roster, list) or len(roster) != 10:
        return False, ["drudge_exact_roster_missing"]
    roster_guids = {
        row.get("guid") for row in roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    if len(roster_guids) != 10:
        reasons.append("drudge_exact_roster_guids_invalid")
    tank_guids = {
        row.get("guid") for row in roster
        if isinstance(row, dict) and row.get("role") == "tank"
        and _positive_int(row.get("guid"))
    }
    offensive_guids = {
        row.get("guid") for row in roster
        if isinstance(row, dict) and row.get("role") in {"tank", "dps"}
        and _positive_int(row.get("guid"))
    }
    if len(tank_guids) != 2 or len(offensive_guids) != 7:
        reasons.append("drudge_frozen_role_slots_invalid")
    role_by_guid = {
        row.get("guid"): row.get("role")
        for row in roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    roster_by_guid = {
        row.get("guid"): row
        for row in roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }

    # A bad native delivery is permanently disqualifying for this capture,
    # even when a later status snapshot contains a clean-looking generation.
    # Otherwise a poisoned queue item could be hidden by selecting the latest
    # status and the resulting dataset would certify a formation that never
    # satisfied the native farthest-target selector.
    lane_a_slots = {1, 3, 4, 6, 7}
    for candidate_runtime, candidate_evidence in candidates:
        candidate_roster = candidate_runtime.get("roster")
        candidate_roles = {
            row.get("guid"): row
            for row in candidate_roster
            if isinstance(row, dict) and _positive_int(row.get("guid"))
        } if isinstance(candidate_roster, list) else {}
        candidate_observations = candidate_evidence.get("observations")
        if not isinstance(candidate_observations, list):
            continue
        for observation in candidate_observations:
            if not isinstance(observation, dict) or observation.get("landed") is not True:
                continue
            target_row = candidate_roles.get(observation.get("target_guid"))
            if target_row and target_row.get("role") == "tank":
                reasons.append("drudge_native_rush_target_tank")
            source = observation.get("source_spawn_id")
            if source not in {250140, 250141} or not target_row:
                continue
            target_slot = target_row.get("slot")
            if not isinstance(target_slot, int) or isinstance(target_slot, bool):
                continue
            target_slot += 1
            target_in_lane_a = target_slot in lane_a_slots
            source_in_lane_a = source == 250140
            if target_in_lane_a == source_in_lane_a:
                reasons.append("drudge_native_rush_lane_target_invalid")

    attempt_id = runtime.get("attempt_id")
    if evidence.get("evidence_attempt_id") != attempt_id:
        reasons.append("drudge_attempt_scope_mismatch")
    if evidence.get("evidence_wipe_generation") != 0:
        reasons.append("drudge_pre_magmaw_wipe_contamination")
    if evidence.get("queue_overflow") is not False:
        reasons.append("drudge_observation_queue_overflow")

    observations = evidence.get("observations")
    if not isinstance(observations, list):
        observations = []
        reasons.append("drudge_observations_missing")
    delivered = [
        row for row in observations
        if isinstance(row, dict) and row.get("landed") is True
    ]
    sequences = [row.get("sequence") for row in delivered]
    if (not sequences or any(not _positive_int(sequence) for sequence in sequences)
            or len(set(sequences)) != len(sequences)
            or sequences != sorted(sequences)):
        reasons.append("drudge_delivered_sequence_invalid")
    if evidence.get("delivered_count") != len(delivered):
        reasons.append("drudge_delivered_count_mismatch")
    prepared_count = evidence.get("prepared_count")
    if not isinstance(prepared_count, int) or isinstance(prepared_count, bool) \
            or prepared_count < len(delivered):
        reasons.append("drudge_prepared_count_invalid")

    exact_sources = {250140, 250141}
    reconstructed: dict[int, dict[str, int]] = {
        source: {"delivered": 0, "valid_intervals": 0, "source_guid": 0}
        for source in exact_sources
    }
    for row in delivered:
        source = row.get("source_spawn_id")
        if (row.get("attempt_id") != attempt_id
                or row.get("wipe_generation") != 0
                or row.get("route_generation") != 3):
            reasons.append("drudge_observation_scope_mismatch")
        if source not in exact_sources:
            reasons.append("drudge_observation_source_invalid")
            continue
        source_guid = row.get("source_guid")
        if not _positive_int(source_guid):
            reasons.append("drudge_observation_source_guid_invalid")
        elif reconstructed[source]["source_guid"] not in {0, source_guid}:
            reasons.append("drudge_observation_source_guid_drift")
        else:
            reconstructed[source]["source_guid"] = source_guid
        if row.get("target_guid") not in roster_guids:
            reasons.append("drudge_observation_target_not_in_roster")
        # The native Drudge Rush is the farthest-player selector.  A tank
        # target proves that the two non-tank lanes were not separated before
        # the cast and would make the capture a formation failure rather than
        # a valid two-group mechanic observation.
        if role_by_guid.get(row.get("target_guid")) == "tank":
            reasons.append("drudge_native_rush_target_tank")
        distance = row.get("selected_distance")
        source_reach = row.get("source_combat_reach")
        target_reach = row.get("target_combat_reach")
        reach_values = (source_reach, target_reach)
        native_range = (
            isinstance(distance, (int, float)) and not isinstance(distance, bool)
            and isfinite(float(distance)) and float(distance) >= 0.0
            and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and isfinite(float(value)) and 0.0 <= float(value) <= 100.0
                    for value in reach_values)
            and row.get("same_map") is True and row.get("same_phase") is True
            and float(distance) < 80.0 + float(source_reach) + float(target_reach)
        )
        if row.get("range_valid") is not native_range or not native_range:
            reasons.append("drudge_observation_range_invalid")
        reconstructed[source]["delivered"] += 1
        interval = row.get("observed_interval_ms")
        if isinstance(interval, int) and not isinstance(interval, bool) and interval > 0:
            if interval < 20000 or row.get("interval_valid") is not True:
                reasons.append("drudge_observation_interval_invalid")
            else:
                reconstructed[source]["valid_intervals"] += 1
        acknowledgements = row.get("reseparated_roster_guids")
        if not isinstance(acknowledgements, list) or set(acknowledgements) != roster_guids:
            reasons.append("drudge_observation_not_reseparated_by_exact_roster")
        # Geometry is immutable evidence for the acknowledgement.  Never
        # accept a stored reseparation bit/acknowledgement without rebuilding
        # the lane, tank, and member-anchor predicates from coordinates.
        reasons.extend(_validate_drudge_observation_geometry(
            row, roster, tank_guids, frozen_anchors=frozen_anchors,
        ))

    for source in exact_sources:
        if reconstructed[source]["delivered"] < 2:
            reasons.append(f"drudge_source_{source}_two_deliveries_missing")
        if reconstructed[source]["valid_intervals"] < 1:
            reasons.append(f"drudge_source_{source}_native_interval_missing")
    source_guids = {reconstructed[source]["source_guid"] for source in exact_sources}
    if 0 in source_guids or len(source_guids) != len(exact_sources):
        reasons.append("drudge_exact_source_runtime_guids_invalid")

    # The native selector is acceptance evidence, not a claim supplied by the
    # bot policy.  Reconstruct the candidate predicate from the exact roster
    # and the serialized core threat-list snapshot.  The runtime intentionally
    # bounds this list; a missing, truncated, or internally inconsistent first
    # Rush snapshot cannot prove selector fidelity and therefore fails closed.
    native_candidate_snapshot_signatures: dict[int, tuple[Any, ...]] = {}
    native_candidate_rows_by_guid: dict[int, dict[int, dict[str, Any]]] = {}
    native_candidate_eligible_guids_by_source: dict[int, set[int]] = {}
    native_first_rush_observed_at_ms: dict[int, int] = {}
    native_first_rush_landed_by_key: dict[tuple[int, int], bool] = {}
    native_candidate_tolerance = 0.05
    complete_candidate_snapshots = []
    for candidate_runtime, candidate_evidence in candidates:
        observations = candidate_evidence.get("observations")
        observations = observations if isinstance(observations, list) else []
        observed_sources = {
            row.get("source_spawn_id") for row in observations
            if isinstance(row, dict)
        }
        if exact_sources.issubset(observed_sources):
            complete_candidate_snapshots.append((candidate_runtime, candidate_evidence))
    if not complete_candidate_snapshots:
        for source in exact_sources:
            reasons.append(f"drudge_native_threat_source_{source}_first_rush_missing")
    for candidate_runtime, candidate_evidence in complete_candidate_snapshots:
        candidate_observations = candidate_evidence.get("observations")
        if not isinstance(candidate_observations, list):
            reasons.append("drudge_native_threat_candidates_observations_missing")
            continue
        candidate_roster = candidate_runtime.get("roster")
        candidate_roster_by_guid = {
            row.get("guid"): row
            for row in candidate_roster
            if isinstance(row, dict) and _positive_int(row.get("guid"))
        } if isinstance(candidate_roster, list) else {}
        for source in exact_sources:
            source_observations = [
                row for row in candidate_observations
                if isinstance(row, dict) and row.get("source_spawn_id") == source
            ]
            if not source_observations:
                reasons.append(f"drudge_native_threat_source_{source}_first_rush_missing")
                continue
            first_observation = min(
                source_observations,
                key=lambda row: (
                    int(row.get("sequence") or 0),
                    int(row.get("observed_at_ms") or 0),
                ),
            )
            first_time = first_observation.get("observed_at_ms")
            if _positive_int(first_time):
                native_first_rush_observed_at_ms[source] = int(first_time)
            sequence = first_observation.get("sequence")
            if not _positive_int(sequence):
                reasons.append("drudge_native_threat_observation_sequence_invalid")
            else:
                landing_key = (source, int(sequence))
                landed = first_observation.get("landed") is True
                prior_landed = native_first_rush_landed_by_key.get(landing_key)
                # A status sampled between SpellStarted and SpellLanded is a
                # legitimate partial observation.  Preserve the edge, merge
                # the later landing monotonically, and reject only an actual
                # true -> false regression.  Treating the early false row as
                # permanently disqualifying made a native landed Rush fail
                # capture even though every later scoped status retained it.
                if prior_landed is True and not landed:
                    reasons.append("drudge_native_threat_landing_regressed")
                native_first_rush_landed_by_key[landing_key] = bool(
                    prior_landed or landed
                )
            candidate_rows = first_observation.get("native_threat_candidates")
            if not isinstance(candidate_rows, list):
                reasons.append("drudge_native_threat_candidates_missing")
                continue
            count = first_observation.get("native_threat_candidates_count")
            complete = first_observation.get("native_threat_candidates_complete")
            truncated = first_observation.get("native_threat_candidates_truncated")
            if (not isinstance(count, int) or isinstance(count, bool) or count < 0
                    or complete is not True or truncated is not False
                    or count != len(candidate_rows) or count > 32):
                reasons.append("drudge_native_threat_candidates_metadata_invalid")
                if truncated is True or (isinstance(count, int) and count > len(candidate_rows)):
                    reasons.append("drudge_native_threat_candidates_truncated")
                continue

            source_lane = 0 if source == 250140 else 1
            expected_candidates: list[dict[str, Any]] = []
            reconstructed_native_selector_guids: set[int] = set()
            reconstructed_tactic_guids: set[int] = set()
            seen_raw_guids: set[int] = set()
            for candidate in candidate_rows:
                if not isinstance(candidate, dict):
                    reasons.append("drudge_native_threat_candidate_invalid")
                    continue
                guid = candidate.get("guid")
                raw_guid = candidate.get("raw_guid")
                if (not _positive_int(guid) or not _positive_int(raw_guid)
                        or raw_guid in seen_raw_guids):
                    reasons.append("drudge_native_threat_candidate_identity_invalid")
                    continue
                seen_raw_guids.add(raw_guid)
                distance = candidate.get("distance")
                threat = candidate.get("threat")
                if (not isinstance(distance, (int, float)) or isinstance(distance, bool)
                        or not isfinite(float(distance)) or distance < 0.0
                        or not isinstance(threat, (int, float)) or isinstance(threat, bool)
                        or not isfinite(float(threat)) or threat < 0.0):
                    reasons.append("drudge_native_threat_candidate_measurement_invalid")
                    continue
                boolean_fields = (
                    "is_player", "alive", "same_map", "same_phase", "available", "line_of_sight",
                    "in_range", "native_combat_range", "cross_lane", "native_selector_eligible",
                    "tactic_cross_lane_eligible",
                )
                if any(not isinstance(candidate.get(field), bool) for field in boolean_fields):
                    reasons.append("drudge_native_threat_candidate_flags_invalid")
                    continue
                is_player = candidate.get("is_player") is True
                roster_row = roster_by_guid.get(guid) if is_player else None
                candidate_runtime_row = candidate_roster_by_guid.get(guid) if is_player else None
                registered = isinstance(roster_row, dict)
                role = roster_row.get("role") if registered else "unregistered"
                slot = (roster_row.get("slot") + 1) if registered and isinstance(roster_row.get("slot"), int) else 0
                lane = (
                    0 if slot in lane_a_slots else 1
                ) if registered else 0
                active_lease = bool(
                    registered and roster_row.get("active") is True
                    and roster_row.get("lease_owned") is True
                )
                expected_in_range = float(distance) <= 80.0
                source_reach = candidate.get("source_combat_reach")
                candidate_reach = candidate.get("candidate_combat_reach")
                reaches_valid = all(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    and isfinite(float(value)) and 0.0 <= float(value) <= 100.0
                    for value in (source_reach, candidate_reach)
                )
                expected_native_combat_range = bool(
                    reaches_valid
                    and candidate.get("same_map") is True
                    and candidate.get("same_phase") is True
                    and float(distance) < 80.0 + float(source_reach) + float(candidate_reach)
                )
                expected_cross_lane = registered and lane != source_lane
                expected_native_selector_eligible = (
                    candidate.get("is_player") is True
                    and candidate.get("available") is True
                    and candidate.get("line_of_sight") is True
                    and expected_native_combat_range
                )
                expected_tactic_eligible = (
                    expected_native_selector_eligible
                    and registered
                    and active_lease
                    and candidate.get("alive") is True
                    and candidate.get("same_map") is True
                    and expected_cross_lane
                    and role != "tank"
                )
                if ((is_player and (not registered or candidate_runtime_row is None))
                        or (not is_player and (registered or candidate_runtime_row is not None))
                        or (is_player and raw_guid != guid)
                        or candidate.get("role") != role
                        or candidate.get("slot") != slot
                        or candidate.get("lane") != lane
                        or candidate.get("in_range") is not expected_in_range
                        or candidate.get("native_combat_range") is not expected_native_combat_range
                        or candidate.get("cross_lane") is not expected_cross_lane
                        or candidate.get("native_selector_eligible") is not expected_native_selector_eligible
                        or candidate.get("tactic_cross_lane_eligible") is not expected_tactic_eligible):
                    reasons.append("drudge_native_threat_candidate_eligibility_mismatch")
                if expected_native_selector_eligible:
                    reconstructed_native_selector_guids.add(raw_guid)
                if expected_tactic_eligible:
                    reconstructed_tactic_guids.add(raw_guid)
                expected_candidates.append(candidate)

            if len(seen_raw_guids) != len(candidate_rows):
                reasons.append("drudge_native_threat_candidate_identity_invalid")
            if not expected_candidates:
                reasons.append(f"drudge_native_threat_source_{source}_candidate_list_empty")
                continue
            eligible_candidates = [
                row for row in expected_candidates
                if row.get("raw_guid") in reconstructed_native_selector_guids
            ]
            target_guid = first_observation.get("target_guid")
            target_raw_guid = first_observation.get("target_raw_guid")
            target = next((row for row in expected_candidates if row.get("raw_guid") == target_raw_guid), None)
            if (not _positive_int(target_raw_guid) or target is None
                    or target_raw_guid not in reconstructed_native_selector_guids
                    or target.get("guid") != target_guid):
                reasons.append("drudge_native_threat_selected_target_ineligible")
            else:
                if target_raw_guid not in reconstructed_tactic_guids:
                    reasons.append("drudge_native_threat_selected_target_not_cross_lane_tactic")
                selected_distance = first_observation.get("selected_distance")
                if (not isinstance(selected_distance, (int, float))
                        or isinstance(selected_distance, bool)
                        or abs(float(selected_distance) - float(target.get("distance"))) > native_candidate_tolerance):
                    reasons.append("drudge_native_threat_selected_distance_mismatch")
                if eligible_candidates:
                    farthest_distance = max(float(row.get("distance")) for row in eligible_candidates)
                    if farthest_distance - float(target.get("distance")) > native_candidate_tolerance:
                        reasons.append("drudge_native_threat_selected_target_not_farthest")
                else:
                    reasons.append(f"drudge_native_threat_source_{source}_eligible_candidates_missing")

            # Repeated status snapshots must retain the exact first-Rush
            # candidate set.  Do not let a later forged list erase it.
            signature = tuple(
                tuple(sorted(row.items())) for row in sorted(expected_candidates, key=lambda row: row.get("guid", 0))
            )
            previous_signature = native_candidate_snapshot_signatures.get(source)
            if previous_signature is not None and previous_signature != signature:
                reasons.append("drudge_native_threat_candidate_snapshot_drift")
            else:
                native_candidate_snapshot_signatures[source] = signature
                native_candidate_rows_by_guid[source] = {
                    row.get("guid"): row for row in expected_candidates
                    if row.get("is_player") is True
                }
                native_candidate_eligible_guids_by_source[source] = {
                    row.get("guid") for row in expected_candidates
                    if row.get("raw_guid") in reconstructed_tactic_guids
                }

    for source in exact_sources:
        source_landings = [
            landed for (observed_source, _), landed
            in native_first_rush_landed_by_key.items()
            if observed_source == source
        ]
        if not source_landings or not any(source_landings):
            reasons.append(f"drudge_native_threat_source_{source}_first_rush_not_landed")

    # The pre-first-Rush seed is a bounded, real profile action rather than a
    # threat-manager shortcut.  Reconstruct both cross-lane rows and all
    # safety/authority predicates from the serialized evidence.
    threat_seed = runtime.get("drudge_threat_seed")
    if not isinstance(threat_seed, dict):
        reasons.append("drudge_threat_seed_missing")
    else:
        if (threat_seed.get("attempt_id") != attempt_id
                or threat_seed.get("wipe_generation") != 0
                or threat_seed.get("route_generation") != 3):
            reasons.append("drudge_threat_seed_scope_mismatch")
        if threat_seed.get("closed") is not True:
            reasons.append("drudge_threat_seed_not_closed_by_native_rush")
        if threat_seed.get("complete") is not True:
            reasons.append("drudge_threat_seed_incomplete")
        if threat_seed.get("failure") is not False:
            reasons.append("drudge_threat_seed_failure")

        seed_roster_value = threat_seed.get("roster_guids")
        seed_roster = (
            set(seed_roster_value)
            if isinstance(seed_roster_value, list)
            and all(_positive_int(guid) for guid in seed_roster_value)
            and len(set(seed_roster_value)) == len(seed_roster_value)
            else set()
        )
        if len(seed_roster) != 2 or not seed_roster.issubset(roster_guids):
            reasons.append("drudge_threat_seed_roster_invalid")

        seed_observations = threat_seed.get("observations")
        if not isinstance(seed_observations, list):
            seed_observations = []
            reasons.append("drudge_threat_seed_observations_missing")
        successful_seed_rows = []
        successful_source_lanes: set[int] = set()
        successful_member_guids: set[int] = set()
        expected_seed_source = {0: 250140, 1: 250141}
        first_native_observation_ms: dict[int, int] = {}
        for native_row in delivered:
            native_source = native_row.get("source_spawn_id")
            native_time = native_row.get("observed_at_ms")
            if (native_source in exact_sources and _positive_int(native_time)
                    and (native_source not in first_native_observation_ms
                         or native_time < first_native_observation_ms[native_source])):
                first_native_observation_ms[native_source] = native_time
        for row in seed_observations:
            if not isinstance(row, dict):
                reasons.append("drudge_threat_seed_observation_invalid")
                continue
            if (row.get("attempt_id") != attempt_id
                    or row.get("wipe_generation") != 0
                    or row.get("route_generation") != 3):
                reasons.append("drudge_threat_seed_observation_scope_mismatch")
            source_lane = row.get("source_lane")
            member_lane = row.get("member_lane")
            source_spawn = row.get("source_spawn_id")
            member_guid = row.get("member_guid")
            if source_lane not in {0, 1} or member_lane not in {0, 1}:
                reasons.append("drudge_threat_seed_lane_invalid")
                continue
            if source_spawn != expected_seed_source[source_lane]:
                reasons.append("drudge_threat_seed_source_lane_invalid")
            if member_lane != 1 - source_lane:
                reasons.append("drudge_threat_seed_cross_lane_invalid")
            member_row = next(
                (member for member in roster
                 if isinstance(member, dict) and member.get("guid") == member_guid),
                None,
            )
            if (not _positive_int(member_guid) or member_guid not in roster_guids
                    or not isinstance(member_row, dict)
                    or member_row.get("role") != "dps"):
                reasons.append("drudge_threat_seed_member_identity_invalid")
            elif member_row.get("slot") != (row.get("member_slot") or 0) - 1:
                reasons.append("drudge_threat_seed_member_slot_invalid")
            if row.get("source_guid") != reconstructed.get(source_spawn, {}).get("source_guid"):
                reasons.append("drudge_threat_seed_source_identity_invalid")
            seed_time = row.get("observed_at_ms")
            first_native_time = first_native_observation_ms.get(source_spawn)
            if (row.get("action_succeeded") is True
                    and (not _positive_int(seed_time)
                         or not _positive_int(first_native_time)
                         or seed_time >= first_native_time)):
                reasons.append("drudge_threat_seed_not_pre_first_rush")
            distance = row.get("selected_distance")
            minimum = row.get("min_range")
            maximum = row.get("max_range")
            if (not isinstance(distance, (int, float)) or isinstance(distance, bool)
                    or not isfinite(float(distance)) or distance < 0.0 or distance > 80.0
                    or not isinstance(minimum, (int, float)) or isinstance(minimum, bool)
                    or not isfinite(float(minimum)) or minimum < 0.0
                    or not isinstance(maximum, (int, float)) or isinstance(maximum, bool)
                    or not isfinite(float(maximum)) or maximum < 0.0
                    or (maximum > 0.0 and distance > maximum)
                    or distance < minimum):
                reasons.append("drudge_threat_seed_range_invalid")
            if (row.get("position_safe") is not True
                    or row.get("line_of_sight") is not True
                    or row.get("in_range") is not True
                    or row.get("profile_action_valid") is not True
                    or row.get("action_succeeded") is not True
                    or row.get("selected_offense_unsuppressed") is not True
                    or row.get("other_offense_suppressed") is not True):
                reasons.append("drudge_threat_seed_safety_evidence_invalid")
            if (not _positive_int(row.get("spell_id"))
                    or not isinstance(row.get("action_debug_name"), str)
                    or not row.get("action_debug_name", "").strip()
                    or not isinstance(row.get("action_result"), str)
                    or not row.get("action_result", "").strip()):
                reasons.append("drudge_threat_seed_profile_action_invalid")
            if row.get("action_succeeded") is True:
                successful_seed_rows.append(row)
                successful_source_lanes.add(source_lane)
                if _positive_int(member_guid):
                    successful_member_guids.add(member_guid)

        if successful_source_lanes != {0, 1}:
            reasons.append("drudge_threat_seed_source_lanes_incomplete")
        if len(successful_seed_rows) != 2:
            reasons.append("drudge_threat_seed_success_count_invalid")
        if len(successful_member_guids) != 2 or successful_member_guids != seed_roster:
            reasons.append("drudge_threat_seed_roster_evidence_mismatch")
        for row in successful_seed_rows:
            source = row.get("source_spawn_id")
            member_guid = row.get("member_guid")
            candidate = native_candidate_rows_by_guid.get(source, {}).get(member_guid)
            if candidate is None:
                reasons.append("drudge_native_threat_seed_member_missing_from_candidates")
                continue
            if (member_guid not in native_candidate_eligible_guids_by_source.get(source, set())
                    or candidate.get("role") != "dps"
                    or candidate.get("cross_lane") is not True):
                reasons.append("drudge_native_threat_seed_member_ineligible")
            seed_time = row.get("observed_at_ms")
            first_time = native_first_rush_observed_at_ms.get(source)
            if (not _positive_int(seed_time) or not _positive_int(first_time)
                    or int(seed_time) >= int(first_time)):
                reasons.append("drudge_native_threat_seed_timing_link_invalid")

    death_fields = (
        "death_attempt_id", "death_wipe_generation", "death_route_generation",
        "death_source_spawn_id", "death_source_guid", "survivor_source_spawn_id",
        "survivor_source_guid", "death_evidence_sequence",
        "rage_wait_evidence_sequence", "rage_aura_evidence_sequence",
    )
    death_values = {field: evidence.get(field) for field in death_fields}
    if (death_values["death_attempt_id"] != attempt_id
            or death_values["death_wipe_generation"] != 0
            or death_values["death_route_generation"] != 3):
        reasons.append("drudge_death_scope_mismatch")
    if (not isinstance(death_values["death_source_spawn_id"], int)
            or isinstance(death_values["death_source_spawn_id"], bool)
            or not isinstance(death_values["survivor_source_spawn_id"], int)
            or isinstance(death_values["survivor_source_spawn_id"], bool)
            or death_values["death_source_spawn_id"] not in exact_sources
            or death_values["survivor_source_spawn_id"] not in exact_sources
            or death_values["death_source_spawn_id"] == death_values["survivor_source_spawn_id"]
            or not _positive_int(death_values["death_source_guid"])
            or not _positive_int(death_values["survivor_source_guid"])
            or death_values["death_source_guid"] != reconstructed[death_values["death_source_spawn_id"]]["source_guid"]
            or death_values["survivor_source_guid"] != reconstructed[death_values["survivor_source_spawn_id"]]["source_guid"]):
        reasons.append("drudge_death_source_identity_mismatch")
    if (not all(_positive_int(death_values[field]) for field in (
            "death_evidence_sequence", "rage_wait_evidence_sequence",
            "rage_aura_evidence_sequence"))
            or not (death_values["death_evidence_sequence"]
                    < death_values["rage_wait_evidence_sequence"]
                    < death_values["rage_aura_evidence_sequence"])):
        reasons.append("drudge_native_rage_transition_order_invalid")

    source_rows = evidence.get("sources")
    source_summary = {
        row.get("spawn_id"): row for row in source_rows
        if isinstance(row, dict)
    } if isinstance(source_rows, list) else {}
    if set(source_summary) != exact_sources:
        reasons.append("drudge_source_summary_identity_mismatch")
    else:
        for source in exact_sources:
            if source_summary[source].get("delivered_count") != reconstructed[source]["delivered"]:
                reasons.append("drudge_source_delivered_summary_mismatch")
            if source_summary[source].get("valid_interval_count") != reconstructed[source]["valid_intervals"]:
                reasons.append("drudge_source_interval_summary_mismatch")

    def exact_guid_set(field: str) -> set[int]:
        value = evidence.get(field)
        if not isinstance(value, list) or any(not _positive_int(guid) for guid in value):
            reasons.append(f"drudge_{field}_invalid")
            return set()
        result = set(value)
        if len(result) != len(value) or not result.issubset(roster_guids):
            reasons.append(f"drudge_{field}_identity_mismatch")
        return result

    reseparated = exact_guid_set("reseparated_roster_guids")
    taunts = exact_guid_set("taunt_roster_guids")
    health_sync = exact_guid_set("health_sync_roster_guids")
    health_sync_evaluated = exact_guid_set("health_sync_evaluated_roster_guids")
    profile_actions = exact_guid_set("profile_action_roster_guids")
    ownership = exact_guid_set("ownership_roster_guids")
    if ownership != tank_guids:
        reasons.append("drudge_exact_tank_ownership_missing")
    if reseparated != roster_guids:
        reasons.append("drudge_exact_roster_reseparation_missing")
    if not taunts.issubset(tank_guids):
        reasons.append("drudge_taunt_evidence_identity_mismatch")
    if not health_sync.issubset(tank_guids):
        reasons.append("drudge_tank_health_sync_hold_identity_mismatch")
    if not health_sync:
        reasons.append("drudge_tank_health_sync_hold_missing")
    hold_source = evidence.get("health_sync_hold_source_spawn_id")
    hold_tank = evidence.get("health_sync_hold_tank_guid")
    hold_lower = evidence.get("health_sync_hold_lower_pct")
    hold_peer = evidence.get("health_sync_hold_peer_pct")
    hold_lower_alive = evidence.get("health_sync_hold_lower_alive")
    hold_peer_alive = evidence.get("health_sync_hold_peer_alive")
    expected_hold_tank = {250140: next((row.get("guid") for row in roster if row.get("slot") == 0), None),
                          250141: next((row.get("guid") for row in roster if row.get("slot") == 1), None)}
    if (not health_sync or hold_tank not in health_sync
            or hold_source not in expected_hold_tank
            or hold_tank != expected_hold_tank.get(hold_source)):
        reasons.append("drudge_health_sync_hold_source_identity_mismatch")
    if (not isinstance(hold_lower, (int, float)) or isinstance(hold_lower, bool)
            or not isinstance(hold_peer, (int, float)) or isinstance(hold_peer, bool)
            or not isfinite(float(hold_lower)) or not isfinite(float(hold_peer))
            or hold_lower <= 0.0 or hold_peer <= 0.0
            or hold_lower >= hold_peer
            or hold_lower_alive is not True or hold_peer_alive is not True):
        reasons.append("drudge_health_sync_hold_order_invalid")
    if health_sync_evaluated != tank_guids:
        reasons.append("drudge_exact_tank_health_sync_evaluation_missing")
    if evidence.get("health_sync_evidence_attempt_id") != attempt_id:
        reasons.append("drudge_health_sync_scope_attempt_mismatch")
    if evidence.get("health_sync_evidence_wipe_generation") != 0:
        reasons.append("drudge_health_sync_scope_wipe_mismatch")
    if evidence.get("health_sync_evidence_route_generation") != 3:
        reasons.append("drudge_health_sync_scope_route_mismatch")
    if profile_actions != offensive_guids:
        reasons.append("drudge_trained_single_target_profile_missing")

    return not reasons, sorted(set(reasons))


def accepted_native_recovery(
    statuses: list[dict[str, Any]],
    *,
    profile_name: str = "blackwing_descent_10n",
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    runtimes = [status.get("raid_runtime") if isinstance(status, dict) else None for status in statuses]
    if not statuses or any(not isinstance(runtime, dict) for runtime in runtimes):
        return False, ["native_event_evidence_missing"]

    identity: tuple[Any, ...] | None = None
    roster_identity: tuple[tuple[Any, ...], ...] | None = None
    previous_sequence = 0
    previous_generations = (0, 0, 0)
    previous_strategy: str | None = None
    previous_route_advance = 0
    previous_transition_state: tuple[Any, ...] | None = None
    engagement_index: int | None = None
    latest_engagement_index: int | None = None
    wipe_index: int | None = None
    selected_wipe_generation = 0
    selected_engagement_sequence = 0
    boss_reset_generation_at_wipe: int | None = None
    recovery_generation_at_wipe: int | None = None
    reset_index: int | None = None
    recovery_index: int | None = None
    for index, runtime in enumerate(runtimes):
        assert isinstance(runtime, dict)
        if statuses[index].get("ok") is not True:
            reasons.append("native_status_not_ok")
        current_identity = _runtime_identity(runtime)
        if current_identity is None:
            reasons.append("native_identity_fields_missing")
        elif identity is None:
            identity = current_identity
        elif current_identity != identity:
            reasons.append("native_recovery_mixed_identity")
        strategy = runtime.get(STRATEGY_FIELD)
        strategy_changed = previous_strategy is not None and strategy != previous_strategy
        route_marker = _route_advancement_marker(runtime)
        if not isinstance(strategy, str) or not strategy.strip():
            reasons.append("native_strategy_identity_missing")
        elif strategy_changed:
            transition = runtime.get("strategy_transition")
            transition_ok = (
                isinstance(transition, dict)
                and transition.get("from_strategy") == previous_strategy
                and transition.get("to_strategy") == strategy
                and transition.get("advanced") is True
                and route_marker is not None
                and route_marker > previous_route_advance
            )
            if not transition_ok:
                reasons.append("native_strategy_transition_without_route_advancement")
        if route_marker is not None:
            previous_route_advance = max(previous_route_advance, route_marker)
        if isinstance(strategy, str):
            previous_strategy = strategy
        transition_state = (
            strategy,
            runtime.get("wipe_generation"),
            runtime.get("boss_reset_generation"),
            runtime.get("recovery_generation"),
            runtime.get("encounter_in_progress"),
            runtime.get("wipe_state"),
            runtime.get("recovery_state"),
            runtime.get("alive_size"),
        )
        if any(
            not _positive_int(runtime.get(field))
            for field in ("group_guid", "leader_guid", "instance_id", "lockout_save_id", "server_epoch",
                          "attempt_id", "profile_generation", "assignment_generation")
        ):
            reasons.append("native_identity_values_invalid")
        if not isinstance(runtime.get("profile_content_hash"), str) or not runtime.get("profile_content_hash", "").strip():
            reasons.append("native_profile_content_hash_invalid")
        if runtime.get("lockout_save_id") != runtime.get("instance_id"):
            reasons.append("native_lockout_instance_mismatch")
        if (
            runtime.get("expected_size") != 10
            or runtime.get("expected_difficulty") != 0
            or runtime.get("group_difficulty") != 0
            or runtime.get("map_difficulty") != 0
            or runtime.get("map_id") != 669
            or not isinstance(runtime.get("strategy_id"), str)
            or not runtime.get("strategy_id", "").strip()
        ):
            reasons.append("native_identity_not_exact_bwd_10n")

        current_roster = _roster_identity(runtime.get("roster") if isinstance(runtime.get("roster"), list) else [])
        if current_roster is None:
            reasons.append("native_roster_identity_missing")
        elif roster_identity is None:
            roster_identity = current_roster
        elif current_roster != roster_identity:
            reasons.append("native_recovery_mixed_roster")
        reasons.extend(
            f"native_{reason}"
            for reason in _roster_rejections(runtime, profile_name)
            if reason not in {"all_roster_active", "all_roster_leases_owned"}
        )

        sequence = runtime.get("evidence_sequence")
        if not _positive_int(sequence):
            reasons.append("native_evidence_sequence_missing")
        elif sequence < previous_sequence:
            reasons.append("native_evidence_sequence_not_monotonic")
        elif sequence == previous_sequence and transition_state != previous_transition_state:
            reasons.append("native_evidence_sequence_transition_without_advancement")
        previous_sequence = max(previous_sequence, sequence if _positive_int(sequence) else 0)
        previous_transition_state = transition_state

        generation_fields = ("wipe_generation", "boss_reset_generation", "recovery_generation")
        if any(
            not isinstance(runtime.get(field), int)
            or isinstance(runtime.get(field), bool)
            or runtime.get(field) < 0
            for field in generation_fields
        ):
            reasons.append("native_generation_missing_or_invalid")
        generations = tuple(
            int(runtime.get(field))
            if isinstance(runtime.get(field), int) and not isinstance(runtime.get(field), bool) and runtime.get(field) >= 0
            else 0
            for field in generation_fields
        )
        if any(current < previous for current, previous in zip(generations, previous_generations, strict=True)):
            reasons.append("native_generations_not_monotonic")
        previous_generations = tuple(max(current, previous) for current, previous in zip(generations, previous_generations, strict=True))

        route_progress = runtime.get("route_progress")
        boss_states = runtime.get("boss_states") or []
        exact_magmaw_engagement = (
            runtime.get("encounter_in_progress") is True
            and isinstance(route_progress, dict)
            and route_progress.get("generation") == 4
            and route_progress.get("node_index") == 3
            and isinstance(boss_states, list)
            and len(boss_states) == 6
            and boss_states[0] == 1
        )
        if engagement_index is None and exact_magmaw_engagement:
            engagement_index = index
        if exact_magmaw_engagement:
            latest_engagement_index = index
        if (
            latest_engagement_index is not None
            and index > latest_engagement_index
            and isinstance(route_progress, dict)
            and route_progress.get("generation") == 4
            and route_progress.get("node_index") == 3
            and generations[0] > selected_wipe_generation
            and runtime.get("wipe_state") == "wiped"
            and runtime.get("alive_size") == 0
            and runtime.get("recovery_state") in {"awaiting_native_reset", "release_resurrection_pending"}
        ):
            wipe_index = index
            selected_wipe_generation = generations[0]
            selected_engagement_sequence = (
                runtimes[latest_engagement_index].get("evidence_sequence", 0)
                if latest_engagement_index is not None and latest_engagement_index < index else 0
            )
            reset_index = None
            recovery_index = None
            declared_reset_baseline = runtime.get("boss_reset_generation_at_wipe")
            boss_reset_generation_at_wipe = (
                declared_reset_baseline
                if _nonnegative_int(declared_reset_baseline)
                and declared_reset_baseline <= generations[1]
                else generations[1]
            )
            recovery_generation_at_wipe = generations[2]
            if generations[1] > boss_reset_generation_at_wipe:
                reset_index = index
        if (
            wipe_index is not None
            and reset_index is None
            and index > wipe_index
            and boss_reset_generation_at_wipe is not None
            and generations[1] > boss_reset_generation_at_wipe
            and runtime.get("encounter_in_progress") is False
        ):
            reset_index = index
        if (
            reset_index is not None
            and recovery_index is None
            and index > reset_index
            and recovery_generation_at_wipe is not None
            and generations[2] > recovery_generation_at_wipe
            and runtime.get("recovery_state") == "recovered_ready_check"
            and runtime.get("ready_check_satisfied") is True
            and runtime.get("alive_size") == 10
        ):
            recovery_index = index

    native_signals = [
        runtime.get("native_recovery")
        for runtime in runtimes
        if isinstance(runtime.get("native_recovery"), dict)
    ]
    final_native = native_signals[-1] if native_signals else {}
    final_runtime = runtimes[-1]
    if engagement_index is None:
        reasons.append("native_magmaw_engagement_not_observed")
    wipe_generation = final_runtime.get("wipe_generation")
    if not isinstance(wipe_generation, int) or isinstance(wipe_generation, bool) or wipe_generation <= 0:
        reasons.append("native_recovery_wipe_scope_missing")
    if selected_wipe_generation != wipe_generation:
        reasons.append("native_latest_wipe_transition_not_observed")
    for transition_name, transition_index in (
        ("wipe", wipe_index),
        ("reset", reset_index),
        ("recovery", recovery_index),
    ):
        if transition_index is not None and runtimes[transition_index].get("wipe_generation") != wipe_generation:
            reasons.append(f"native_{transition_name}_transition_wipe_scope_mismatch")
    if final_native.get("recovery_wipe_generation") != wipe_generation:
        reasons.append("native_recovery_wipe_scope_mismatch")
    for field in (
        "death_observed", "corpse_observed", "release_observed",
        "resurrection_observed", "runback_observed", "ready_check_action_observed",
        "evidence_complete",
    ):
        if final_native.get(field) is not True:
            reasons.append(f"native_{field}_missing")
    if not _positive_int(final_native.get("ready_check_action_generation")):
        reasons.append("native_ready_check_action_generation_missing")
    if final_native.get("ready_check_action_attempt_id") != runtimes[-1].get("attempt_id"):
        reasons.append("native_ready_check_action_attempt_mismatch")
    if final_native.get("ready_check_action_wipe_generation") != runtimes[-1].get("wipe_generation"):
        reasons.append("native_ready_check_action_wipe_generation_mismatch")
    if final_native.get("ready_check_assignment_generation") != runtimes[-1].get("assignment_generation"):
        reasons.append("native_ready_check_assignment_generation_mismatch")
    ready_sequence = final_native.get("ready_check_action_evidence_sequence")
    if not _positive_int(ready_sequence) or not _positive_int(final_runtime.get("evidence_sequence")) \
            or ready_sequence > final_runtime["evidence_sequence"]:
        reasons.append("native_ready_check_sequence_exceeds_runtime")
    recovery_members = final_native.get("members")
    final_roster = final_runtime.get("roster")
    roster_guids = {
        row.get("guid") for row in final_roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    } if isinstance(final_roster, list) else set()
    if not isinstance(recovery_members, list) or len(recovery_members) != 10:
        reasons.append("native_per_member_recovery_missing")
    else:
        recovery_guids = {
            row.get("guid") for row in recovery_members
            if isinstance(row, dict) and _positive_int(row.get("guid"))
        }
        if recovery_guids != roster_guids or len(recovery_guids) != 10:
            reasons.append("native_per_member_recovery_roster_mismatch")
        sequence_fields = (
            "death_sequence", "corpse_sequence", "release_sequence",
            "runback_sequence", "reentry_sequence", "resurrection_sequence",
        )
        for row in recovery_members:
            if not isinstance(row, dict):
                reasons.append("native_per_member_recovery_invalid")
                continue
            sequences = tuple(row.get(field) for field in sequence_fields)
            if row.get("wipe_generation") != wipe_generation:
                reasons.append("native_per_member_recovery_wipe_mismatch")
            if not all(_positive_int(value) for value in sequences) or not all(
                left < right for left, right in zip(sequences, sequences[1:])
            ):
                reasons.append("native_per_member_recovery_order_invalid")
            elif not _positive_int(selected_engagement_sequence) or sequences[0] <= selected_engagement_sequence:
                reasons.append("native_per_member_recovery_predates_latest_engagement")
            elif wipe_index is None or not _positive_int(runtimes[wipe_index].get("evidence_sequence")) \
                    or sequences[0] > runtimes[wipe_index]["evidence_sequence"]:
                reasons.append("native_per_member_death_postdates_latest_wipe_snapshot")
            elif not _positive_int(final_runtime.get("evidence_sequence")) or any(
                value > final_runtime["evidence_sequence"] for value in sequences
            ):
                reasons.append("native_per_member_recovery_sequence_exceeds_runtime")

    ordered_checks = {
        "ready_check_observed": any(runtime.get("ready_check_satisfied") is True for runtime in runtimes),
        "native_engagement_observed": engagement_index is not None,
        "native_wipe_observed": wipe_index is not None,
        "boss_reset_observed": reset_index is not None,
        "native_recovery_observed": recovery_index is not None,
    }
    reasons.extend(name for name, passed in ordered_checks.items() if not passed)
    # Preserve deterministic diagnostics rather than reporting the same
    # rejection once for every status snapshot.
    return not reasons, list(dict.fromkeys(reasons))


def native_readycheck_request_identity(status: dict[str, Any]) -> tuple[Any, ...]:
    """Bind one controller request to the exact recovery and route scope."""
    runtime = status.get("raid_runtime") or {}
    route = status.get("validation_route") or {}
    return (
        runtime.get("attempt_id"),
        runtime.get("wipe_generation"),
        runtime.get("assignment_generation"),
        route.get("generation"),
        route.get("node_id"),
    )


def ready_for_native_readycheck(status: dict[str, Any]) -> bool:
    """Mirror the native C++ boss-or-hostile reset admission predicate."""
    runtime = status.get("raid_runtime") or {}
    route = status.get("validation_route") or {}
    native = runtime.get("native_recovery") or {}
    attempt_id = int(runtime.get("attempt_id") or 0)
    assignment_generation = int(runtime.get("assignment_generation") or 0)
    route_generation = int(route.get("generation") or 0)
    route_node_id = str(route.get("node_id") or "")
    recovery_scope_matches = (
        attempt_id > 0
        and assignment_generation > 0
        and route_generation > 0
        and bool(route_node_id)
        and runtime.get("native_recovery_hold_active") is True
        and int(runtime.get("native_recovery_route_generation") or 0) == route_generation
        and str(runtime.get("native_recovery_node_id") or "") == route_node_id
    )
    boss_reset_observed = int(runtime.get("boss_reset_generation") or 0) > int(
        runtime.get("boss_reset_generation_at_wipe") or 0
    )
    hostile_reset_observed = (
        runtime.get("native_hostile_inactivity_observed") is True
        and int(runtime.get("native_hostile_reset_generation") or 0)
        > int(runtime.get("native_hostile_reset_generation_at_wipe") or 0)
        and int(runtime.get("native_hostile_observation_attempt_id") or 0) == attempt_id
        and int(runtime.get("native_hostile_observation_route_generation") or 0) == route_generation
        and str(runtime.get("native_hostile_observation_node_id") or "") == route_node_id
    )
    return (
        recovery_scope_matches
        and runtime.get("alive_size") == 10
        and runtime.get("encounter_in_progress") is False
        and int(runtime.get("wipe_generation") or 0) > 0
        and runtime.get("native_hostile_activity_active") is False
        and (boss_reset_observed or hostile_reset_observed)
        and native.get("death_observed") is True
        and native.get("corpse_observed") is True
        and native.get("release_observed") is True
        and native.get("resurrection_observed") is True
        and native.get("runback_observed") is True
        and native.get("ready_check_action_observed") is not True
    )


def wait_for_prompt(process: subprocess.Popen[bytes], log_path: Path, timeout_sec: int) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"worldserver exited before readiness with code {process.returncode}")
        if log_path.exists() and b"TC>" in log_path.read_bytes()[-65536:]:
            return
        time.sleep(0.25)
    raise RuntimeError("worldserver readiness prompt timed out")


def semantic_progress_signature(status: dict[str, Any], diagnosis: dict[str, Any] | None) -> str:
    """Hash only raid facts whose change proves meaningful live progress.

    Timers, heartbeat counters, cumulative deaths and trace length are
    deliberately excluded. Boss health/phase, route state and native recovery
    generations are included so a living but semantically wedged run can be
    stopped for diagnosis without imposing a raid-duration deadline.
    """
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    bot_progress: list[dict[str, Any]] = []
    if isinstance(diagnosis, dict):
        for row in diagnosis.get("bots") or []:
            if not isinstance(row, dict):
                continue
            identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
            snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
            progress = snapshot.get("route_progress") if isinstance(snapshot.get("route_progress"), dict) else {}
            target = progress.get("target") if isinstance(progress.get("target"), dict) else {}
            state = progress.get("state") if isinstance(progress.get("state"), dict) else {}
            bot_progress.append({
                "bot_guid": identity.get("bot_guid"),
                # Decision churn is diagnostic evidence, not objective
                # progress. Keep it in the immutable raw diagnose/trace rows,
                # but do not let alternating wrong actions reset this clock.
                "target": {key: target.get(key) for key in (
                    "guid", "entry", "hp_pct", "best_hp_pct",
                )},
                "combat_state": {key: state.get(key) for key in (
                    "victim_guid", "bot_in_combat", "bot_casting",
                )},
            })
    payload = {
        "route": {key: route.get(key) for key in (
            "manifest_index", "generation", "node_id", "kind", "manifest_complete",
            "terminal_evidence", "boss_death_evidence",
        )},
        "raid": {key: runtime.get(key) for key in (
            "map_id", "instance_id", "lockout_save_id", "strategy_id",
            "assignment_generation", "boss_states", "encounter_phase",
            "encounter_in_progress", "alive_size", "wipe_state", "recovery_state",
            "wipe_generation", "boss_reset_generation", "recovery_generation",
        )},
        "metrics": {key: status.get(key) for key in (
            "kills", "raid_boss_kills", "instance_resets",
        )},
        "bots": sorted(bot_progress, key=lambda row: int(row.get("bot_guid") or 0)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def observe_monotonic_semantic_progress(
    state: dict[str, Any], status: dict[str, Any], diagnosis: dict[str, Any] | None,
) -> bool:
    """Update objective high-water marks and report genuine forward progress."""
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    advanced = not state

    counters = {
        "route_generation": int(route.get("generation") or 0),
        "route_index": int(route.get("manifest_index") or 0),
        "route_terminal_count": len(route.get("terminal_evidence") or []),
        "boss_death_evidence_count": len(route.get("boss_death_evidence") or []),
        "kills": int(status.get("kills") or 0),
        "raid_boss_kills": int(status.get("raid_boss_kills") or 0),
        "instance_resets": int(status.get("instance_resets") or 0),
        "boss_done_count": sum(1 for value in runtime.get("boss_states") or [] if value == 3),
    }
    high_water = state.setdefault("high_water", {})
    for key, value in counters.items():
        previous = int(high_water.get(key, -1))
        if value > previous:
            advanced = True
            high_water[key] = value

    # Wipe/reset counters and aggregate native booleans are lifecycle churn,
    # not objective progress.  Advance only when the current runtime contains
    # an exact-roster, per-member, ordered native recovery proof.  The proof
    # identity deliberately excludes recovery_generation so incrementing that
    # counter cannot replay stale evidence as a new completion.
    native = runtime.get("native_recovery") if isinstance(
        runtime.get("native_recovery"), dict
    ) else {}
    completion_scope: list[Any] | None = None
    evidence_sequence = int(runtime.get("evidence_sequence") or 0)
    attempt_id = int(runtime.get("attempt_id") or 0)
    wipe_generation = int(runtime.get("wipe_generation") or 0)
    assignment_generation = int(runtime.get("assignment_generation") or 0)
    expected_size = int(runtime.get("expected_size") or 0)
    roster = runtime.get("roster") if isinstance(runtime.get("roster"), list) else []
    roster_guids = sorted(
        int(row.get("guid") or 0) for row in roster
        if isinstance(row, dict) and int(row.get("guid") or 0) > 0
    )
    members = native.get("members") if isinstance(native.get("members"), list) else []
    ordered_members: list[list[int]] = []
    member_guids: list[int] = []
    member_sequences_valid = len(members) == expected_size == len(roster_guids) > 0
    sequence_fields = (
        "death_sequence", "corpse_sequence", "release_sequence",
        "runback_sequence", "reentry_sequence", "resurrection_sequence",
    )
    for member in members:
        if not isinstance(member, dict):
            member_sequences_valid = False
            continue
        guid = int(member.get("guid") or 0)
        sequences = [int(member.get(field) or 0) for field in sequence_fields]
        if (
            guid <= 0
            or int(member.get("wipe_generation") or 0) != wipe_generation
            or any(value <= 0 for value in sequences)
            or sequences != sorted(sequences)
            or len(set(sequences)) != len(sequences)
            or sequences[-1] > evidence_sequence
        ):
            member_sequences_valid = False
        member_guids.append(guid)
        ordered_members.append([guid, *sequences])
    ordered_members.sort()
    member_guids.sort()
    ready_sequence = int(native.get("ready_check_action_evidence_sequence") or 0)
    proof_valid = (
        native.get("evidence_complete") is True
        and all(native.get(field) is True for field in (
            "death_observed", "corpse_observed", "release_observed",
            "runback_observed", "resurrection_observed",
            "ready_check_action_observed",
        ))
        and evidence_sequence > 0 and attempt_id > 0 and wipe_generation > 0
        and assignment_generation > 0
        and int(native.get("recovery_wipe_generation") or 0) == wipe_generation
        and member_sequences_valid and member_guids == roster_guids
        and int(native.get("ready_check_action_generation") or 0) > 0
        and int(native.get("ready_check_response_count") or 0) == expected_size
        and int(native.get("ready_check_action_attempt_id") or 0) == attempt_id
        and int(native.get("ready_check_action_wipe_generation") or 0) == wipe_generation
        and int(native.get("ready_check_assignment_generation") or 0) == assignment_generation
        and ready_sequence > max((row[-1] for row in ordered_members), default=0)
        and ready_sequence <= evidence_sequence
    )
    if proof_valid:
        completion_scope = [
            attempt_id, wipe_generation, assignment_generation,
            ordered_members, ready_sequence,
        ]
    if completion_scope is not None:
        completed_scopes = state.setdefault("accepted_native_recovery_scopes", [])
        if completion_scope not in completed_scopes:
            completed_scopes.append(completion_scope)
            advanced = True

    if runtime.get("encounter_in_progress") is True and not state.get("engagement_observed"):
        state["engagement_observed"] = True
        advanced = True
    encounter_phase = str(runtime.get("encounter_phase") or "")
    observed_phases = state.setdefault("observed_encounter_phases", [])
    if encounter_phase and encounter_phase not in observed_phases:
        observed_phases.append(encounter_phase)
        advanced = True
    if route.get("manifest_complete") is True and not state.get("manifest_complete_observed"):
        state["manifest_complete_observed"] = True
        advanced = True

    lowest_hp = state.setdefault("lowest_target_hp", {})
    if isinstance(diagnosis, dict):
        for row in diagnosis.get("bots") or []:
            if not isinstance(row, dict):
                continue
            snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
            progress = snapshot.get("route_progress") if isinstance(snapshot.get("route_progress"), dict) else {}
            target = progress.get("target") if isinstance(progress.get("target"), dict) else {}
            # Runtime GUIDs change when the same native boss respawns after an
            # evade. Entry identity is the stable semantic target; a replacement
            # object alone must not keep an invalid pull loop alive forever.
            target_id = int(target.get("entry") or target.get("guid") or 0)
            hp = target.get("best_hp_pct", target.get("hp_pct"))
            if not target_id or not isinstance(hp, (int, float)) or hp <= 0:
                continue
            key = f"{int(runtime.get('instance_id') or 0)}:{int(route.get('generation') or 0)}:{target_id}"
            previous_hp = float(lowest_hp.get(key, 101.0))
            if float(hp) < previous_hp:
                lowest_hp[key] = float(hp)
                advanced = True
    return advanced


def observe_telemetry_freshness(
    state: dict[str, dict[str, float | int]], counts: dict[str, int], now: float,
    timeout_seconds: float,
) -> list[str]:
    """Update per-channel heartbeats and return channels whose output is stale.

    The canonical raid runtime is intentionally uncapped, but its control and
    evidence channels are not. A live worldserver that stops producing any one
    of status, diagnosis, or trace evidence is an infrastructure failure, not a
    healthy long boss attempt.
    """
    stale: list[str] = []
    for channel in ("status", "diagnosis", "trace"):
        channel_state = state.setdefault(channel, {
            "count": 0,
            "last_observed_monotonic": now,
        })
        count = int(counts.get(channel, 0))
        if count > int(channel_state["count"]):
            channel_state["count"] = count
            channel_state["last_observed_monotonic"] = now
        if now - float(channel_state["last_observed_monotonic"]) > timeout_seconds:
            stale.append(channel)
    return stale


def material_status_signature(status: dict[str, Any]) -> str:
    """Return a stable signature for status changes that need a full diagnose.

    Status includes several heartbeat/evidence counters which change on every
    poll and must not turn the reduced steady-state cadence back into a full
    diagnose cadence. The fields below are the state edges that change the
    interpretation of a decision trace: route/encounter/boss lifecycle,
    roster/recovery state, and explicit errors. The complete status remains
    retained in the immutable evidence stream; this projection only controls
    when an additional command is requested.
    """
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    error_fields = {
        "status_error": status.get("error"),
        "status_failure": status.get("failure"),
        "status_failure_reason": status.get("failure_reason"),
        "runtime_error": runtime.get("error"),
        "runtime_failure": runtime.get("failure"),
        "runtime_error_state": runtime.get("error_state"),
    }
    payload = {
        "ok": status.get("ok"),
        "active": runtime.get("active"),
        "route": {key: route.get(key) for key in (
            "manifest_index", "generation", "node_id", "kind", "manifest_complete",
            "terminal_evidence", "boss_death_evidence",
        )},
        "raid": {key: runtime.get(key) for key in (
            "map_id", "instance_id", "lockout_save_id", "strategy_id",
            "assignment_generation", "boss_states", "encounter_phase",
            "encounter_in_progress", "alive_size", "expected_size", "wipe_state",
            "recovery_state", "wipe_generation", "boss_reset_generation",
            "recovery_generation", "ready_check_satisfied", "roster_complete",
        )},
        # These fields are deliberately not heartbeat counters.  A hostile
        # that remains alive after a native wipe changes whether re-entry is
        # safe, while the reset generation and reason explain which native
        # edge produced that state.  Keep all known reason spellings so a
        # compact/full producer transition cannot hide a material edge.
        "native_hostile": {key: runtime.get(key) for key in (
            "native_hostile_activity_active",
            "native_hostile_activity_seen_at_wipe",
            "native_hostile_inactivity_observed",
            "native_hostile_reset_generation",
            "native_hostile_reset_generation_at_wipe",
            "native_hostile_activity_entry",
            "native_hostile_activity_guid",
            "native_hostile_activity_reason",
            "native_hostile_inactivity_reason",
            "native_hostile_reset_reason",
            "native_hostile_state_reason",
        )},
        # Recovery booleans alone cannot express a newly completed per-GUID
        # transition.  Include the ordered native sequence tuple for every
        # member; sorting makes status map iteration order immaterial.
        "native_recovery_members": sorted(
            [
                {
                    key: member.get(key)
                    for key in (
                        "guid", "wipe_generation", "death_sequence",
                        "corpse_sequence", "release_sequence", "runback_sequence",
                        "reentry_sequence", "resurrection_sequence",
                    )
                }
                for member in (runtime.get("native_recovery", {}).get("members", [])
                               if isinstance(runtime.get("native_recovery"), dict)
                               else [])
                if isinstance(member, dict)
            ],
            key=lambda member: int(member.get("guid") or 0),
        ),
        "errors": error_fields,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def validate_forced_evidence_bundle(
    observations: list[tuple[dict[str, Any], float]],
    expected_status: dict[str, Any] | None,
    *,
    requested_at_monotonic: float,
    freshness_timeout_seconds: float,
) -> dict[str, Any]:
    """Validate the diagnose/trace responses to one explicit final request.

    The worldserver console is asynchronous.  A one-second sleep after
    writing commands is not evidence that either command ran, and a forged
    ``ok`` bit or a response from another cohort must not satisfy the final
    stall bundle.  Callers pass each newly observed row with the monotonic
    time at which it was read; this function therefore enforces both request
    ordering and a bounded freshness window without trusting producer-side
    timestamps.
    """

    required_channels = ("diagnosis", "trace")
    action_by_channel = {
        "diagnosis": "botauto_diagnose",
        "trace": "botauto_trace",
    }
    channels: dict[str, dict[str, Any]] = {
        channel: {
            "action": action,
            "observed": 0,
            "valid": False,
            "rejections": [],
        }
        for channel, action in action_by_channel.items()
    }
    expected_runtime = (
        expected_status.get("raid_runtime")
        if isinstance(expected_status, dict)
        else None
    )
    expected_identity = (
        _runtime_identity(expected_runtime, include_strategy=False)
        if isinstance(expected_runtime, dict)
        else None
    )
    expected_roster = (
        _roster_binding_identity(expected_runtime.get("roster"))
        if isinstance(expected_runtime, dict)
        and isinstance(expected_runtime.get("roster"), list)
        else None
    )
    expected_cohort = (
        expected_status.get("cohort_id")
        if isinstance(expected_status, dict)
        else None
    )
    expected_guids = {
        int(member[3])
        for member in expected_roster or ()
        if _positive_int(member[3])
    }
    expected_binding_missing = []
    if expected_identity is None:
        expected_binding_missing.append("forced_expected_runtime_identity_missing")
    if expected_roster is None or len(expected_guids) != 10:
        expected_binding_missing.append("forced_expected_roster_identity_missing")
    if not isinstance(expected_cohort, str) or not expected_cohort:
        expected_binding_missing.append("forced_expected_cohort_missing")

    def reject(channel: str, reason: str) -> None:
        reasons = channels[channel]["rejections"]
        if reason not in reasons:
            reasons.append(reason)

    for row, observed_at in observations:
        if not isinstance(row, dict):
            continue
        action = row.get("action")
        channel = next(
            (name for name, expected_action in action_by_channel.items()
             if expected_action == action),
            None,
        )
        if channel is None:
            continue
        channels[channel]["observed"] += 1
        if not isinstance(observed_at, (int, float)) or not isfinite(float(observed_at)):
            reject(channel, "forced_response_observation_time_invalid")
            continue
        if observed_at < requested_at_monotonic:
            reject(channel, "forced_response_before_request")
        elif observed_at - requested_at_monotonic > freshness_timeout_seconds:
            reject(channel, "forced_response_stale")
        if row.get("ok") is not True:
            reject(channel, "forced_response_envelope_not_ok")
        if expected_binding_missing:
            for reason in expected_binding_missing:
                reject(channel, reason)
            continue
        runtime = row.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        if (
            not isinstance(runtime, dict)
            or _runtime_identity(runtime, include_strategy=False) != expected_identity
            or _roster_binding_identity(roster) != expected_roster
            or row.get("cohort_id") != expected_cohort
        ):
            reject(channel, "forced_response_runtime_identity_unbound")
        if _roster_binding_lifecycle_rejections(roster):
            reject(channel, "forced_response_roster_lifecycle_invalid")
        bot_rows = row.get("bots")
        if not isinstance(bot_rows, list):
            reject(channel, "forced_response_bot_rows_missing")
            continue
        observed_guids: list[int] = []
        for bot_row in bot_rows:
            if not isinstance(bot_row, dict):
                reject(channel, "forced_response_bot_row_invalid")
                continue
            if channel == "trace" and bot_row.get("gap") is True:
                reject(channel, "forced_response_trace_delta_gap")
            identity = bot_row.get("identity")
            guid = identity.get("bot_guid") if isinstance(identity, dict) else bot_row.get("bot_guid")
            if not _positive_int(guid):
                reject(channel, "forced_response_bot_guid_invalid")
                continue
            observed_guids.append(int(guid))
        if len(observed_guids) != 10:
            reject(channel, "forced_response_bot_row_count_invalid")
        if len(set(observed_guids)) != len(observed_guids):
            reject(channel, "forced_response_duplicate_bot_guid")
        if set(observed_guids) != expected_guids:
            reject(channel, "forced_response_roster_incomplete_or_unbound")
        if not channels[channel]["rejections"]:
            channels[channel]["valid"] = True
            channels[channel]["observed_at_monotonic"] = float(observed_at)

    missing_channels = [
        channel for channel in required_channels
        if not channels[channel]["valid"]
    ]
    rejections = [
        f"{channel}:{reason}"
        for channel in required_channels
        for reason in channels[channel]["rejections"]
    ]
    return {
        "requested_at_monotonic": requested_at_monotonic,
        "freshness_timeout_seconds": freshness_timeout_seconds,
        "required_channels": list(required_channels),
        "missing_channels": missing_channels,
        "channels": channels,
        "rejections": rejections,
        "gate_passed": not missing_channels and not rejections,
    }


@dataclass
class TelemetryScheduler:
    """Schedule independent evidence channels without losing transition edges.

    Status is the control heartbeat and remains frequent. Diagnose is the
    expensive semantic snapshot and trace is the append-only delta export. A
    material status edge promotes the next loop to an immediate diagnose;
    callers can also force both heavy channels before terminating on a stall.
    ``commands_due`` advances each channel independently, so a delayed
    diagnosis never delays status or causes a trace cursor gap.
    """

    status_interval_sec: float = 5.0
    # Full diagnosis and trace are materially larger than the status
    # heartbeat.  Keep their steady-state cadence deliberately sparse for an
    # uncapped raid; material status edges and the final forced bundle still
    # request them immediately, so this is a volume reduction rather than an
    # evidence reduction.
    diagnose_interval_sec: float = 30.0
    trace_interval_sec: float = 20.0
    _next_status_at: float = 0.0
    _next_diagnose_at: float = 0.0
    _next_trace_at: float = 0.0
    _diagnose_forced: bool = True
    _trace_forced: bool = False
    _last_status_signature: str | None = None

    def __post_init__(self) -> None:
        if self.status_interval_sec <= 0 or self.diagnose_interval_sec <= 0 or self.trace_interval_sec <= 0:
            raise ValueError("telemetry intervals must be positive")

    def observe_status(self, status: dict[str, Any]) -> bool:
        """Record a status and request immediate diagnosis on a material edge."""
        signature = material_status_signature(status)
        changed = self._last_status_signature is not None and signature != self._last_status_signature
        # The initial scheduler tick already includes one full diagnosis. A
        # later material edge must promote the next tick immediately.
        if changed:
            self._diagnose_forced = True
        self._last_status_signature = signature
        return changed

    def force_diagnosis(self, *, include_trace: bool = True) -> None:
        """Force a final semantic bundle before a stall/error termination."""
        self._diagnose_forced = True
        if include_trace:
            self._trace_forced = True

    def commands_due(self, now: float) -> list[str]:
        """Return due console commands and advance only their own deadlines."""
        commands: list[str] = []
        if now >= self._next_status_at:
            commands.append("botauto status")
            self._next_status_at = now + self.status_interval_sec
        if now >= self._next_trace_at or self._trace_forced:
            commands.append("botauto trace all 128 delta")
            self._next_trace_at = now + self.trace_interval_sec
            self._trace_forced = False
        if now >= self._next_diagnose_at or self._diagnose_forced:
            commands.append("botauto diagnose all")
            self._next_diagnose_at = now + self.diagnose_interval_sec
            self._diagnose_forced = False
        return commands

    def state(self) -> dict[str, Any]:
        """Expose scheduler state for watchdog evidence and deterministic tests."""
        return {
            "status_interval_seconds": self.status_interval_sec,
            "diagnose_interval_seconds": self.diagnose_interval_sec,
            "trace_interval_seconds": self.trace_interval_sec,
            "next_status_at": self._next_status_at,
            "next_diagnose_at": self._next_diagnose_at,
            "next_trace_at": self._next_trace_at,
            "diagnose_forced": self._diagnose_forced,
            "trace_forced": self._trace_forced,
        }


def git_identity(cwd: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=cwd, text=True).strip()
    porcelain = subprocess.check_output(["git", "status", "--porcelain=v1", "-z"], cwd=cwd)
    return {
        "head": head,
        "tree": tree,
        "clean": not porcelain,
        "dirty": bool(porcelain),
        "porcelain_sha256": hashlib.sha256(porcelain).hexdigest(),
    }


def _utc_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def validate_build_receipt(
    receipt_path: Path,
    policy_path: Path,
    worktree: Path,
    binary: Path,
    config: Path | None = None,
    attestation_path: Path | None = None,
) -> dict[str, Any]:
    """Reconstruct the production build gate without trusting receipt pass fields."""

    try:
        from tools.raid_program.queued_build import load_json, verify_receipt

        policy = load_json(policy_path)
        receipt = load_json(receipt_path)
        verification = verify_receipt(receipt_path, policy, allow_test_mode=False)
        privileged_verification = None
        if policy.get("mechanical_controls", {}).get(
            "privileged_receipt_signature_required"
        ):
            if attestation_path is None:
                raise RuntimeError("privileged build attestation is required")
            from tools.raid_program.privileged_build_attestation import (
                verify_privileged_attestation,
            )

            privileged_verification = verify_privileged_attestation(
                attestation_path,
                receipt_path,
                policy_path,
                None,
                allow_test_mode=False,
            )
        identity = git_identity(worktree)
        rejections: list[str] = []
        if verification.get("classification") != "success" or receipt.get("classification") != "success":
            rejections.append("build_receipt_not_success")
        if receipt.get("test_mode") is not False:
            rejections.append("build_receipt_test_mode")
        if receipt.get("exit_code") != 0:
            rejections.append("build_receipt_nonzero_exit")
        if receipt.get("commit") != identity["head"]:
            rejections.append("build_receipt_commit_mismatch")
        if Path(str(receipt.get("worktree", ""))).resolve() != worktree.resolve():
            rejections.append("build_receipt_worktree_mismatch")
        if receipt.get("worktree_dirty_at_request") is not False:
            rejections.append("build_receipt_worktree_dirty")
        source_identity = receipt.get("source_identity")
        if not isinstance(source_identity, dict):
            rejections.append("build_receipt_source_identity_missing")
        else:
            snapshots = [source_identity.get(stage) for stage in ("request", "admission", "completion")]
            if not all(isinstance(snapshot, dict) for snapshot in snapshots):
                rejections.append("build_receipt_source_identity_incomplete")
            elif not (snapshots[0] == snapshots[1] == snapshots[2]):
                rejections.append("build_receipt_source_identity_changed")
            else:
                completion = snapshots[2]
                current_source = {
                    "commit": identity["head"],
                    "tree": identity["tree"],
                    "clean": identity["clean"],
                    "dirty": identity["dirty"],
                    "porcelain_sha256": identity["porcelain_sha256"],
                }
                if completion != current_source:
                    rejections.append("build_receipt_completion_source_mismatch")
                if completion.get("clean") is not True or completion.get("dirty") is not False:
                    rejections.append("build_receipt_completion_source_dirty")
        controls = policy.get("mechanical_controls", {})
        release_flags = controls.get("cmake_release_cxx_flags")
        if isinstance(release_flags, str) and release_flags:
            expected_cmake = {
                "CMAKE_BUILD_TYPE": controls.get("cmake_build_type"),
                "CMAKE_GENERATOR": str(controls.get("cmake_generator", "")),
                "CMAKE_MAKE_PROGRAM": str(controls.get("cmake_make_program", "")),
                "CMAKE_EXPORT_COMPILE_COMMANDS": (
                    "ON" if controls.get("cmake_export_compile_commands") else "OFF"
                ),
                "CMAKE_CXX_FLAGS": str(controls.get("cmake_cxx_flags", "")),
                "CMAKE_CXX_FLAGS_RELEASE": release_flags,
                "CMAKE_CXX_COMPILER": str(
                    controls.get("cmake_cxx_compiler", "/usr/bin/c++")
                ),
                "CMAKE_CXX_COMPILER_LAUNCHER": str(
                    controls.get("cmake_cxx_compiler_launcher", "")
                ),
                "CMAKE_INTERPROCEDURAL_OPTIMIZATION": (
                    "ON" if controls.get("interprocedural_optimization") else "OFF"
                ),
                "CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE": (
                    "ON" if controls.get("release_interprocedural_optimization") else "OFF"
                ),
                "UNITY_BUILDS": "ON" if controls.get("unity_builds") else "OFF",
                "USE_COREPCH": "ON" if controls.get("core_precompiled_headers") else "OFF",
                "USE_SCRIPTPCH": "ON" if controls.get("script_precompiled_headers") else "OFF",
                "WITH_COREDEBUG": "ON" if controls.get("with_coredebug") else "OFF",
            }
            cache_path = (worktree / "build/CMakeCache.txt").resolve()
            cache_values: dict[str, str] = {}
            if cache_path.is_file():
                for line in cache_path.read_text(encoding="utf-8").splitlines():
                    if not line or line.startswith(("//", "#")) or "=" not in line:
                        continue
                    typed_key, value = line.split("=", 1)
                    cache_values[typed_key.split(":", 1)[0]] = value
            current_cmake = {key: cache_values.get(key) for key in expected_cmake}
            if current_cmake != expected_cmake:
                rejections.append("effective_cmake_settings_policy_mismatch")
            build_configuration = receipt.get("build_configuration")
            stages = (
                [build_configuration.get(stage) for stage in ("request", "admission", "completion")]
                if isinstance(build_configuration, dict)
                else []
            )
            if len(stages) != 3 or not all(isinstance(stage, dict) for stage in stages):
                rejections.append("build_receipt_cmake_snapshots_missing")
            else:
                if not all(stage.get("settings") == expected_cmake for stage in stages):
                    rejections.append("build_receipt_cmake_settings_mismatch")
                if not all(stage.get("matches_policy") is True for stage in stages):
                    rejections.append("build_receipt_cmake_policy_match_missing")
                if not (
                    stages[0].get("settings_sha256")
                    == stages[1].get("settings_sha256")
                    == stages[2].get("settings_sha256")
                ):
                    rejections.append("build_receipt_cmake_settings_changed")
                if not (
                    stages[0].get("cache_sha256")
                    == stages[1].get("cache_sha256")
                    == stages[2].get("cache_sha256")
                ):
                    rejections.append("build_receipt_cmake_cache_changed")
                if not all(
                    stage.get("build_graph", {}).get("generated") is True
                    for stage in stages
                ):
                    rejections.append("build_receipt_generated_graph_invalid")
                if not (
                    stages[0].get("build_graph", {}).get("manifest_sha256")
                    == stages[1].get("build_graph", {}).get("manifest_sha256")
                    == stages[2].get("build_graph", {}).get("manifest_sha256")
                ):
                    rejections.append("build_receipt_generated_graph_changed")
                current_cache_sha256 = sha256_file(cache_path) if cache_path.is_file() else None
                if stages[2].get("cache_sha256") != current_cache_sha256:
                    rejections.append("build_receipt_cmake_cache_hash_mismatch")
                lineage = receipt.get("configure_lineage")
                if not isinstance(lineage, dict):
                    rejections.append("build_receipt_configure_lineage_missing")
                elif not (
                    lineage.get("completion_cache_sha256")
                        == stages[0].get("cache_sha256")
                    and lineage.get("completion_settings_sha256")
                        == stages[0].get("settings_sha256")
                    and lineage.get("compiler_sha256")
                        == stages[0].get("compiler_sha256")
                    and lineage.get("completion_build_graph_sha256")
                        == stages[0].get("build_graph", {}).get("manifest_sha256")
                    and isinstance(lineage.get("receipt_sha256"), str)
                    and isinstance(lineage.get("ticket_id"), str)
                ):
                    rejections.append("build_receipt_configure_lineage_mismatch")
            if receipt.get("build_configuration_stable") is not True:
                rejections.append("build_receipt_cmake_stability_missing")
        expected_config_sha256 = sha256_file(config) if config is not None and config.is_file() else None
        try:
            binary.relative_to(worktree)
        except ValueError:
            rejections.append("binary_outside_worktree")
        binary_bytes = binary.read_bytes() if binary.is_file() else b""
        is_elf = binary_bytes[:4] == b"\x7fELF"
        if not binary_bytes:
            rejections.append("binary_missing")
        if not is_elf:
            rejections.append("binary_not_elf")
        artifacts = receipt.get("output_artifacts")
        expected_binary = None
        if isinstance(artifacts, list):
            expected_binary = next(
                (row for row in artifacts if isinstance(row, dict) and row.get("kind") == "worldserver_elf"),
                None,
            )
        if not expected_binary:
            rejections.append("build_receipt_binary_artifact_missing")
        else:
            if expected_binary.get("sha256") != (sha256_file(binary) if binary.is_file() else None):
                rejections.append("build_receipt_binary_hash_mismatch")
            if Path(str(expected_binary.get("path", ""))).resolve() != binary.resolve():
                rejections.append("build_receipt_binary_path_mismatch")
            if expected_binary.get("size_bytes") != (binary.stat().st_size if binary.is_file() else 0):
                rejections.append("build_receipt_binary_size_mismatch")
            try:
                binary_mtime = binary.stat().st_mtime
                admitted_at = _utc_timestamp(str(receipt["admitted_at_utc"]))
                receipt_end = _utc_timestamp(str(receipt["ended_at_utc"]))
                if binary_mtime < admitted_at - 2.0:
                    rejections.append("binary_precedes_admitted_build")
                if binary_mtime > receipt_end + 2.0:
                    rejections.append("binary_newer_than_receipt")
                if expected_binary.get("produced_by_ticket") is not True:
                    rejections.append("build_receipt_binary_not_produced_by_ticket")
                if int(expected_binary.get("mtime_ns") or 0) != binary.stat().st_mtime_ns:
                    rejections.append("build_receipt_binary_mtime_mismatch")
            except (KeyError, OSError, TypeError, ValueError):
                rejections.append("binary_provenance_timestamp_unavailable")
        return {
            "valid": not rejections,
            "rejections": rejections,
            "receipt_path": str(receipt_path),
            "policy_path": str(policy_path),
            "receipt_sha256": receipt.get("receipt_sha256"),
            "ticket_id": receipt.get("ticket_id"),
            "commit": receipt.get("commit"),
            "worktree": receipt.get("worktree"),
            "classification": receipt.get("classification"),
            "test_mode": receipt.get("test_mode"),
            "config_sha256": expected_config_sha256,
            "binary_path": str(binary),
            "binary_sha256": sha256_file(binary) if binary.is_file() else None,
            "binary_size_bytes": binary.stat().st_size if binary.is_file() else 0,
            "binary_is_elf": is_elf,
            "binary_binding": (
                "privileged_ed25519_attestation_plus_coordinator_receipt_path_size_sha256_commit_and_timestamp_verified"
                if privileged_verification is not None
                else "explicit_trusted_local_operator_coordinator_receipt_path_size_sha256_commit_and_timestamp_verified"
            ),
            "privileged_attestation": privileged_verification,
            "receipt_trust_model": verification.get("receipt_trust_model"),
            "operator_identity": verification.get("operator_identity"),
        }
    except Exception as error:  # fail closed, while retaining a useful rejection
        return {
            "valid": False,
            "rejections": [f"build_receipt_verification_error:{type(error).__name__}:{error}"],
            "receipt_path": str(receipt_path),
            "policy_path": str(policy_path),
            "binary_path": str(binary),
        }


def normalized_batch_payload(log_bytes: bytes) -> list[dict[str, Any]]:
    """Return an immutable, replayable JSONL representation of parsed evidence."""

    channel_by_action = {
        "botauto_status": "status",
        "botauto_diagnose": "diagnosis",
        "botauto_trace": "trace",
        "botauto_profile": "profile_selection",
        "botauto_readycheck": "native_action",
        "botauto_stop": "cleanup",
    }
    rows = [
        {
            "normalized_schema_version": 2,
            "capture_sequence": sequence,
            "action": row.get("action"),
            "evidence_channel": channel_by_action.get(str(row.get("action")), "other"),
            "payload": row,
        }
        for sequence, row in enumerate(json_rows(log_bytes), start=1)
    ]
    # Populate diagnostic bindings for the immutable batch, but never trust
    # them during acceptance: evidence_demux_report reconstructs and replaces
    # every binding from the retained payload on every call.
    evidence_demux_report(rows)
    return rows


def _canonical_object_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_telemetry_envelope_report(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate the complete canonical bot roster in every diagnose/trace row.

    Status rows establish the canonical live runtime.  Diagnose and trace are
    independent retained evidence channels, so a non-empty channel alone is
    insufficient: every one of their envelopes must bind to that runtime and
    enumerate each canonical bot exactly once.
    """

    canonical_identity: tuple[Any, ...] | None = None
    canonical_roster: tuple[tuple[Any, ...], ...] | None = None
    canonical_cohort: str | None = None
    canonical_guids: set[int] | None = None
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict) or payload.get("action") != "botauto_status":
            continue
        runtime = payload.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        identity = _runtime_identity(runtime, include_strategy=False) if isinstance(runtime, dict) else None
        roster_identity = _roster_binding_identity(roster) if isinstance(roster, list) else None
        cohort = payload.get("cohort_id")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            continue
        if identity is None or roster_identity is None or not isinstance(cohort, str) or not cohort:
            continue
        guids = [member[3] for member in roster_identity]
        if not all(_positive_int(guid) for guid in guids) or len(set(guids)) != 10:
            continue
        canonical_identity = identity
        canonical_roster = roster_identity
        canonical_cohort = cohort
        canonical_guids = {int(guid) for guid in guids}
        break

    row_rejections: dict[int, list[str]] = {}
    channel_counts = {"diagnosis": 0, "trace": 0}
    if canonical_identity is None or canonical_roster is None or canonical_cohort is None or canonical_guids is None:
        return {
            "rejections": ["evidence_demux_telemetry_canonical_runtime_missing"],
            "row_rejections": row_rejections,
            "diagnosis_envelopes": 0,
            "trace_envelopes": 0,
            "gate_passed": False,
        }

    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        action = payload.get("action")
        channel = {"botauto_diagnose": "diagnosis", "botauto_trace": "trace"}.get(action)
        if channel is None:
            continue
        channel_counts[channel] += 1
        row_reasons: list[str] = []
        if payload.get("ok") is not True:
            row_reasons.append(f"evidence_demux_{channel}_envelope_not_ok")
        runtime = payload.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        if (
            not isinstance(runtime, dict)
            or runtime.get("active") is not True
            or _runtime_identity(runtime, include_strategy=False) != canonical_identity
            or (_roster_binding_identity(roster) if isinstance(roster, list) else None) != canonical_roster
            or payload.get("cohort_id") != canonical_cohort
        ):
            row_reasons.append(f"evidence_demux_{channel}_runtime_identity_unbound")
        row_reasons.extend(
            f"evidence_demux_{channel}_{reason}"
            for reason in _roster_binding_lifecycle_rejections(roster)
        )

        bot_rows = payload.get("bots")
        if not isinstance(bot_rows, list):
            row_reasons.append(f"evidence_demux_{channel}_bot_rows_missing")
        elif not bot_rows:
            row_reasons.append(f"evidence_demux_{channel}_roster_empty")
        else:
            if channel == "trace" and any(
                isinstance(bot_row, dict) and bot_row.get("gap") is True
                for bot_row in bot_rows
            ):
                # A cursor gap means the bounded server trace ring overwrote
                # an edge before export.  Bind nothing from that envelope;
                # current diagnose/status facts remain useful for diagnosis,
                # but the capture must fail closed on missing edge evidence.
                row_reasons.append("evidence_demux_trace_delta_gap")
            bot_guids: list[int] = []
            for bot_row in bot_rows:
                if not isinstance(bot_row, dict):
                    row_reasons.append(f"evidence_demux_{channel}_bot_row_invalid")
                    continue
                bot_guid = bot_row.get("bot_guid")
                identity_object = bot_row.get("identity")
                if isinstance(identity_object, dict):
                    bot_guid = identity_object.get("bot_guid")
                if not _positive_int(bot_guid):
                    row_reasons.append(f"evidence_demux_{channel}_bot_guid_invalid")
                    continue
                bot_guids.append(int(bot_guid))
            counts = Counter(bot_guids)
            if any(count > 1 for count in counts.values()):
                row_reasons.append(f"evidence_demux_{channel}_duplicate_bot_guid")
            if any(guid not in canonical_guids for guid in counts):
                row_reasons.append(f"evidence_demux_{channel}_bot_outside_roster")
            if set(bot_guids) != canonical_guids:
                row_reasons.append(f"evidence_demux_{channel}_canonical_roster_incomplete")
            if len(bot_guids) != 10:
                row_reasons.append(f"evidence_demux_{channel}_bot_row_count_invalid")
        if row_reasons:
            row_rejections[int(row.get("capture_sequence") or 0)] = list(dict.fromkeys(row_reasons))

    rejections = [
        reason
        for reasons in row_rejections.values()
        for reason in reasons
    ]
    for channel, count in channel_counts.items():
        if count == 0:
            rejections.append(f"evidence_demux_{channel}_roster_envelope_missing")
    unique_rejections = list(dict.fromkeys(rejections))
    return {
        "rejections": unique_rejections,
        "row_rejections": row_rejections,
        "diagnosis_envelopes": channel_counts["diagnosis"],
        "trace_envelopes": channel_counts["trace"],
        "gate_passed": not unique_rejections,
    }


def evidence_demux_report(
    rows: list[dict[str, Any]], *, profile_name: str = "blackwing_descent_10n"
) -> dict[str, Any]:
    """Independently bind every retained JSON row to one raid lifecycle."""

    reasons: list[str] = []
    known_actions = {
        "botauto_profile", "botauto_status", "botauto_diagnose", "botauto_trace",
        "botauto_readycheck", "botauto_stop",
    }
    canonical_identity: tuple[Any, ...] | None = None
    canonical_roster: tuple[tuple[Any, ...], ...] | None = None
    canonical_cohort: str | None = None
    roster_guids: set[int] = set()
    canonical_identity_sha256: str | None = None
    canonical_roster_sha256: str | None = None
    canonical_active_sequence: int | None = None

    for row in rows:
        # An outer annotation is evidence output, not evidence input.  Replace
        # it before reconstructing so a forged binding can never self-certify.
        row["identity_binding"] = {
            "state": "rejected",
            "scope": "unknown",
            "canonical_identity_sha256": None,
            "cohort_id": None,
            "roster_sha256": None,
            "binding_source": "retained_payload_reconstruction",
            "reasons": [],
        }

    # First establish canonical identity only from a complete active status.
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict) or payload.get("action") != "botauto_status":
            continue
        runtime = payload.get("raid_runtime")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            continue
        identity = _runtime_identity(runtime, include_strategy=False)
        roster = runtime.get("roster")
        roster_identity = _roster_binding_identity(roster) if isinstance(roster, list) else None
        cohort = payload.get("cohort_id")
        roster_guid_values = (
            [member[3] for member in roster_identity]
            if roster_identity is not None else []
        )
        if (
            identity is not None
            and roster_identity is not None
            and all(_positive_int(guid) for guid in roster_guid_values)
            and len(set(roster_guid_values)) == 10
            and isinstance(cohort, str)
            and cohort
        ):
            canonical_identity = identity
            canonical_roster = roster_identity
            canonical_cohort = cohort
            canonical_active_sequence = row.get("capture_sequence")
            roster_guids = {int(member[3]) for member in roster_identity if _positive_int(member[3])}
            canonical_roster_sha256 = _canonical_object_sha256(roster_identity)
            canonical_identity_sha256 = _canonical_object_sha256(
                {
                    "cohort_id": canonical_cohort,
                    "runtime_identity": canonical_identity,
                    "roster_sha256": canonical_roster_sha256,
                }
            )
            break
    if canonical_identity is None:
        telemetry_envelopes = _required_telemetry_envelope_report(rows)
        for row in rows:
            row["identity_binding"]["reasons"] = ["evidence_demux_no_active_raid_rows"]
        return {
            "rejections": ["evidence_demux_no_active_raid_rows"],
            "retained_rows": len(rows),
            "bound_rows": 0,
            "rejected_rows": len(rows),
            "unchecked_rows": 0,
            "canonical_identity_sha256": None,
            "canonical_roster_sha256": None,
            "required_telemetry_envelopes": telemetry_envelopes,
            "gate_passed": False,
        }

    telemetry_envelopes = _required_telemetry_envelope_report(rows)
    stop_seen = False
    inactive_cleanup_seen = False
    observed_actions: set[str] = set()
    previous_strategy: str | None = None
    previous_route_advance = 0
    profile_selection_seen = False
    terminal_failure_seen = False
    for expected_sequence, row in enumerate(rows, start=1):
        binding = row["identity_binding"]
        binding.update(
            canonical_identity_sha256=canonical_identity_sha256,
            cohort_id=canonical_cohort,
            roster_sha256=canonical_roster_sha256,
        )
        row_reasons: list[str] = binding["reasons"]

        def reject(reason: str) -> None:
            row_reasons.append(reason)
            reasons.append(reason)

        payload = row.get("payload")
        if not isinstance(payload, dict):
            reject("evidence_demux_payload_missing")
            continue
        action = payload.get("action")
        if row.get("capture_sequence") != expected_sequence:
            reject("evidence_demux_sequence_invalid")
        if row.get("action") != action:
            reject("evidence_demux_wrapper_action_mismatch")
        if action not in known_actions:
            reject("evidence_demux_unclassified_row")
            continue
        observed_actions.add(str(action))

        if action == "botauto_status":
            terminal_reason, _ = terminal_runtime_failure_reason(
                payload, profile_name=profile_name,
            )
            terminal_failure_seen = terminal_failure_seen or terminal_reason is not None

        if action == "botauto_profile":
            binding["scope"] = "pre_start_profile"
            if canonical_cohort != "default" or payload.get("cohort_id") != canonical_cohort:
                reject("evidence_demux_profile_cohort_mismatch")
            if payload.get("ok") is not True or payload.get("active_profile") != profile_name:
                reject("evidence_demux_profile_selection_invalid")
            if profile_selection_seen:
                reject("evidence_demux_duplicate_profile_selection")
            if (not isinstance(canonical_active_sequence, int)
                    or expected_sequence >= canonical_active_sequence):
                reject("evidence_demux_profile_selection_not_before_active_status")
            profile_selection_seen = True
            if not row_reasons:
                binding["state"] = "bound"
            continue

        runtime_key = "raid_runtime_before_cleanup" if action == "botauto_stop" else "raid_runtime"
        runtime = payload.get(runtime_key)
        if action == "botauto_status" and isinstance(runtime, dict) and runtime.get("active") is False:
            binding["scope"] = "post_cleanup"
            if not stop_seen:
                reject("evidence_demux_inactive_status_before_stop")
            if payload.get("cohort_id") != canonical_cohort:
                reject("evidence_demux_cross_identity_row")
            if payload.get("bots") != 0 or payload.get("lease_count") != 0:
                reject("evidence_demux_cleanup_not_empty")
            if (
                payload.get("server_epoch") != canonical_identity[9]
                or payload.get("attempt_id") != canonical_identity[10]
                or _runtime_identity(runtime, include_strategy=False) != canonical_identity
            ):
                reject("evidence_demux_cross_identity_row")
            inactive_cleanup_seen = True
            if not row_reasons:
                binding["state"] = "bound"
            continue

        binding["scope"] = "pre_cleanup_runtime" if action == "botauto_stop" else "active_runtime"
        if stop_seen:
            reject("evidence_demux_active_row_after_stop")
        if not isinstance(runtime, dict) or runtime.get("active") is not True:
            reject("evidence_demux_identity_missing")
            continue
        identity = _runtime_identity(runtime, include_strategy=False)
        roster = runtime.get("roster")
        roster_identity = _roster_binding_identity(roster) if isinstance(roster, list) else None
        if (identity != canonical_identity or roster_identity != canonical_roster
                or payload.get("cohort_id") != canonical_cohort):
            reject("evidence_demux_cross_identity_row")
        for lifecycle_reason in _roster_binding_lifecycle_rejections(roster):
            reject(f"evidence_demux_{lifecycle_reason}")
        strategy = runtime.get(STRATEGY_FIELD)
        route_marker = _route_advancement_marker(runtime)
        if not isinstance(strategy, str) or not strategy.strip():
            reject("evidence_demux_strategy_identity_missing")
        elif previous_strategy is not None and strategy != previous_strategy:
            transition = runtime.get("strategy_transition")
            if not (
                isinstance(transition, dict)
                and transition.get("from_strategy") == previous_strategy
                and transition.get("to_strategy") == strategy
                and transition.get("advanced") is True
                and route_marker is not None
                and route_marker > previous_route_advance
            ):
                reject("evidence_demux_strategy_transition_without_route_advancement")
        if route_marker is not None:
            previous_route_advance = max(previous_route_advance, route_marker)
        if isinstance(strategy, str) and strategy.strip():
            previous_strategy = strategy

        if action == "botauto_stop":
            if stop_seen:
                reject("evidence_demux_duplicate_stop")
            cleanup = payload.get("post_cleanup")
            if (payload.get("server_epoch") != canonical_identity[9]
                    or payload.get("attempt_id") != canonical_identity[10]
                    or not isinstance(cleanup, dict) or cleanup.get("active") is not False
                    or cleanup.get("bots") != 0 or cleanup.get("lease_count") != 0):
                reject("evidence_demux_cleanup_identity_invalid")
            stop_seen = True

        for reason in telemetry_envelopes["row_rejections"].get(expected_sequence, []):
            reject(reason)

        bot_rows = payload.get("bots")
        if isinstance(bot_rows, list):
            for bot_row in bot_rows:
                if not isinstance(bot_row, dict):
                    reject("evidence_demux_bot_row_invalid")
                    continue
                bot_guid = bot_row.get("bot_guid")
                identity_object = bot_row.get("identity")
                if isinstance(identity_object, dict):
                    bot_guid = identity_object.get("bot_guid")
                if not _positive_int(bot_guid) or int(bot_guid) not in roster_guids:
                    reject("evidence_demux_bot_outside_roster")
        if not row_reasons:
            binding["state"] = "bound"
    if not stop_seen:
        reasons.append("evidence_demux_cleanup_missing")
    if not inactive_cleanup_seen:
        reasons.append("evidence_demux_inactive_cleanup_missing")
    reasons.extend(telemetry_envelopes["rejections"])
    required_actions = known_actions - {"botauto_profile"}
    if terminal_failure_seen:
        # A recognized failed attempt never reaches the post-wipe ready-check
        # success gate.  Its exact terminal status plus forced diagnose/trace
        # and ordinary cleanup remain mandatory evidence.
        required_actions.discard("botauto_readycheck")
    for required_action in required_actions:
        if required_action not in observed_actions:
            reasons.append(f"evidence_demux_required_action_missing:{required_action}")
    unique_reasons = list(dict.fromkeys(reasons))
    states = Counter(
        str((row.get("identity_binding") or {}).get("state", "unchecked"))
        for row in rows
    )
    unchecked = len(rows) - states.get("bound", 0) - states.get("rejected", 0)
    return {
        "rejections": unique_reasons,
        "retained_rows": len(rows),
        "bound_rows": states.get("bound", 0),
        "rejected_rows": states.get("rejected", 0),
        "unchecked_rows": unchecked,
        "canonical_identity_sha256": canonical_identity_sha256,
        "canonical_roster_sha256": canonical_roster_sha256,
        "required_telemetry_envelopes": telemetry_envelopes,
        "gate_passed": not unique_reasons and states.get("bound", 0) == len(rows) and unchecked == 0,
    }


def evidence_demux_rejections(rows: list[dict[str, Any]]) -> list[str]:
    return evidence_demux_report(rows)["rejections"]


def write_normalized_batch(path: Path, rows: list[dict[str, Any]]) -> tuple[str, int]:
    if path.exists():
        raise RuntimeError("raw normalized batch output already exists; artifacts are immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("xb") as handle:
        for row in rows:
            encoded = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            handle.write(encoded)
            digest.update(encoded)
    return digest.hexdigest(), len(rows)


def _forbidden_assistance_entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in FORBIDDEN_ASSISTANCE_FIELDS and child not in (None, False, [], {}, "", 0):
                    found.append({"path": f"{path}.{key}", "value": child})
                # This diagnostic means that no fallback was available or
                # executed; its wording must not invert the evidence.
                negative_fallback_marker = child == "blocked_no_fallback"
                if (key in FORBIDDEN_MARKER_FIELDS and isinstance(child, str)
                        and not negative_fallback_marker and FORBIDDEN_MARKER_RE.search(child)):
                    found.append({"path": f"{path}.{key}", "value": child, "kind": "forbidden_event_marker"})
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    for row in rows:
        visit(row, "evidence")
    return found


def _process_arguments(pid: int) -> list[str]:
    try:
        return [
            value.decode(errors="replace")
            for value in (Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0"))
            if value
        ]
    except OSError:
        return []


def _protected_process_matches(arguments: list[str]) -> list[str]:
    """Classify process entrypoints without treating data arguments as processes.

    The capture command itself passes the prospective worldserver path through
    ``--binary``.  Scanning every argv basename therefore classified the
    capture's parent ``pixi`` process as a live worldserver.  Only argv[0] is an
    executable; for Python, the script or ``-m`` module is also an entrypoint.
    """

    if not arguments:
        return []
    protected_names = {
        "worldserver", "run_live_bot_validation.py", "live_validation_session.py",
        "run_phase9_serial_canaries.py", "publish_live_validation.py",
        "publish_live_validation", "promote_live_validation_artifact.py",
        "bot-live-validate", "operator", "raid_operator.py",
    }
    entrypoints = {Path(arguments[0]).name}
    executable = Path(arguments[0]).name.lower()
    if executable.startswith("python"):
        for index, value in enumerate(arguments[1:], start=1):
            if value == "-m" and index + 1 < len(arguments):
                module = arguments[index + 1].rsplit(".", 1)[-1]
                entrypoints.update((module, f"{module}.py"))
                break
            if not value.startswith("-"):
                entrypoints.add(Path(value).name)
                break
    return sorted(entrypoints & protected_names)


def _dvc_status_is_clean(output: str) -> bool:
    try:
        payload = json.loads(output)
    except (TypeError, ValueError):
        return False
    return isinstance(payload, dict) and not payload


def preflight_runtime_exclusions(worktree: Path) -> dict[str, Any]:
    """Require an idle coordinator and exclusive canonical-capture host."""

    from tools.raid_program.queued_build import Paths, status as coordinator_status

    coordinator = coordinator_status(Paths.for_worktree(worktree), recover=False)
    reasons: list[str] = []
    if coordinator.get("active") is not None:
        reasons.append("coordinator_active_lease")
    if coordinator.get("queue"):
        reasons.append("coordinator_queue_not_idle")

    overlap: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        arguments = _process_arguments(int(entry.name))
        if not arguments:
            continue
        matched = _protected_process_matches(arguments)
        lower_args = [value.lower() for value in arguments]
        dvc_index = next((index for index, value in enumerate(lower_args) if Path(value).name == "dvc"), None)
        if dvc_index is not None and "push" in lower_args[dvc_index + 1:]:
            matched.append("dvc push")
        if matched:
            overlap.append({"pid": int(entry.name), "matched": sorted(set(matched))})
    if overlap:
        reasons.append("canonical_process_overlap")
    return {
        "coordinator_idle": coordinator.get("active") is None and not coordinator.get("queue"),
        "coordinator": {
            "active": coordinator.get("active"),
            "queue": coordinator.get("queue", []),
        },
        "process_overlap": overlap,
        "reasons": reasons,
        "passed": not reasons,
    }


def validate_runtime_profile_assets(
    worktree: Path,
    reference_worktree: Path = ROOT,
    profile_name: str = "blackwing_descent_10n",
    require_dvc_lineage: bool = True,
    scenario_id: str | None = None,
    pool_tag: str | None = None,
) -> dict[str, Any]:
    """Fail closed when a capture lacks its exact profile-owned route partition.

    ``profile_name`` and ``scenario_id`` are explicit inputs for diagnostic
    boss shards.  The route file is shared, so validating only its full-file
    digest would allow a shard to consume a canonical or neighboring shard
    partition.  This function independently checks the selected scenario's
    contiguous node sequence, identity fields, diagnostic flags, and profile
    binding before a worldserver is started.
    """

    reasons: list[str] = []
    selected_scenario_id = scenario_id or profile_name
    if scenario_id is not None and scenario_id != profile_name:
        reasons.append("profile_scenario_argument_mismatch")
    if not selected_scenario_id:
        reasons.append("profile_scenario_required")
    profile_relative = Path("dataset/bot_runtime_profiles/profiles.json")

    def load_profile(root: Path) -> tuple[dict[str, Any] | None, Path | None, str | None]:
        manifest = root / profile_relative
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None, None, "profile_manifest_unreadable"
        profiles = payload.get("profiles") if isinstance(payload, dict) else None
        matches = [row for row in profiles or [] if isinstance(row, dict) and row.get("name") == profile_name]
        if len(matches) != 1:
            return None, None, "profile_missing_or_duplicated"
        profile = matches[0]
        route = profile.get("validation_route")
        if not isinstance(route, dict) or route.get("enable") is not True:
            return profile, None, "profile_route_disabled"
        route_text = route.get("manifest_path")
        if not isinstance(route_text, str) or not route_text:
            return profile, None, "profile_route_path_missing"
        if route.get("scenario_id") != selected_scenario_id:
            return profile, None, "profile_route_scenario_mismatch"
        route_relative = Path(route_text)
        if route_relative.is_absolute() or ".." in route_relative.parts:
            return profile, None, "profile_route_path_outside_worktree"
        route_path = (root / route_relative).resolve()
        try:
            route_path.relative_to(root.resolve())
        except ValueError:
            return profile, None, "profile_route_path_outside_worktree"
        return profile, route_path, None

    worktree_profile, route_path, worktree_error = load_profile(worktree)
    reference_profile, reference_route_path, reference_error = load_profile(reference_worktree)
    if worktree_error:
        reasons.append(f"worktree_{worktree_error}")
    if reference_error:
        reasons.append(f"reference_{reference_error}")
    if worktree_profile is not None:
        declared_tag = worktree_profile.get("pool_tag_filter")
        if ((profile_name != "blackwing_descent_10n" or pool_tag is not None)
                and (not isinstance(declared_tag, str) or not declared_tag)):
            reasons.append("profile_pool_tag_missing")
        elif pool_tag is not None and declared_tag != pool_tag:
            reasons.append("profile_pool_tag_argument_mismatch")
        if worktree_profile.get("name") != profile_name:
            reasons.append("profile_name_identity_mismatch")
        route = worktree_profile.get("validation_route")
        if isinstance(route, dict) and route.get("scenario_id") != selected_scenario_id:
            reasons.append("profile_scenario_identity_mismatch")

    route_rows = 0
    route_sha256 = None
    reference_route_sha256 = None
    route_partition: dict[str, Any] = {
        "scenario_id": selected_scenario_id,
        "profile_name": profile_name,
        "node_count": 0,
        "terminal_index": None,
        "terminal_kind": None,
        "node_ids": [],
        "diagnostic_only": None,
        "boss_node_count": 0,
        "passed": False,
        "reasons": [],
    }
    if route_path is not None:
        try:
            route_bytes = route_path.read_bytes()
            if not route_bytes:
                reasons.append("worktree_route_manifest_empty")
            if len(route_bytes) > 4 * 1024 * 1024:
                reasons.append("worktree_route_manifest_oversized")
            route_sha256 = hashlib.sha256(route_bytes).hexdigest()
            rows = [json.loads(line) for line in route_bytes.decode("utf-8").splitlines() if line.strip()]
            matching_rows = [row for row in rows if isinstance(row, dict) and row.get("scenario_id") == selected_scenario_id]
            route_rows = len(matching_rows)
            route_partition["node_count"] = route_rows
            if route_rows == 0:
                route_partition["reasons"].append("route_partition_empty")
            steps = [int(row.get("step") or 0) for row in matching_rows]
            node_ids = [str(row.get("route_node_id") or "") for row in matching_rows]
            kinds = [str(row.get("kind") or "") for row in matching_rows]
            route_partition["node_ids"] = node_ids
            route_partition["terminal_index"] = route_rows - 1 if route_rows else None
            route_partition["terminal_kind"] = kinds[-1] if kinds else None
            diagnostic_values = [row.get("diagnostic_only") for row in matching_rows]
            diagnostic_only = diagnostic_values[0] if diagnostic_values else None
            route_partition["diagnostic_only"] = diagnostic_only
            route_partition["boss_node_count"] = sum(kind == "boss" for kind in kinds)
            expected_partition = EXPECTED_BWD_ROUTE_PARTITION_COUNTS.get(profile_name)
            if expected_partition is not None and (
                route_rows != expected_partition[0]
                or route_partition["boss_node_count"] != expected_partition[1]
            ):
                route_partition["reasons"].append("route_partition_shape_mismatch")
            if matching_rows and isinstance(worktree_profile, dict):
                if any(row.get("runtime_profile_id", profile_name) != profile_name for row in matching_rows):
                    route_partition["reasons"].append("route_partition_runtime_profile_mismatch")
                declared_population = worktree_profile.get("target_population")
                route_population = matching_rows[0].get("expected_bot_count")
                if (isinstance(declared_population, int) and declared_population > 0
                        and route_population != declared_population):
                    route_partition["reasons"].append("route_partition_roster_size_mismatch")
                expected_roster = matching_rows[0].get("roster_identity")
                if declared_population and (
                    not isinstance(expected_roster, list)
                    or len(expected_roster) != declared_population
                    or len({str(row.get("roster_slot_id")) for row in expected_roster if isinstance(row, dict)}) != declared_population
                    or len({str(row.get("guid")) for row in expected_roster if isinstance(row, dict)}) != declared_population
                    or any(
                        not isinstance(row, dict)
                        or not str(row.get("roster_slot_id") or "").strip()
                        or not _positive_int(row.get("guid"))
                        or not str(row.get("name") or "").strip()
                        or not str(row.get("class_spec") or "").strip()
                        or not str(row.get("role") or "").strip()
                        for row in expected_roster
                    )
                ):
                    route_partition["reasons"].append("route_partition_roster_identity_invalid")
                roster_signatures = {
                    _canonical_object_sha256(row.get("roster_identity"))
                    if isinstance(row.get("roster_identity"), list) else "missing"
                    for row in matching_rows
                }
                if len(roster_signatures) != 1:
                    route_partition["reasons"].append("route_partition_roster_identity_drift")
            route_identity = tuple(
                (
                    int(row.get("step") or 0),
                    str(row.get("kind") or ""),
                    str(row.get("label") or ""),
                    int(row.get("source_entry") or 0),
                    str(row.get("source_guid") or ""),
                )
                for row in matching_rows
            )
            if steps != list(range(1, route_rows + 1)):
                route_partition["reasons"].append("route_partition_steps_not_contiguous")
                if selected_scenario_id == "blackwing_descent_10n":
                    reasons.append("worktree_route_steps_not_ordered_one_through_eleven")
            # Preserve the canonical Phase 1 identity contract for the
            # foundation capture. Diagnostic shards use the generated
            # partition contract above and are never compared to this list.
            if selected_scenario_id == "blackwing_descent_10n":
                if route_rows != len(EXPECTED_BWD_ROUTE_IDENTITY):
                    reasons.append("worktree_route_expected_eleven_rows")
                if route_identity != EXPECTED_BWD_ROUTE_IDENTITY:
                    reasons.append("worktree_route_identity_mismatch")
            if any(not node_id for node_id in node_ids):
                route_partition["reasons"].append("route_partition_node_id_missing")
            if len(set(node_ids)) != len(node_ids):
                route_partition["reasons"].append("route_partition_node_id_duplicated")
            if any(not kind for kind in kinds):
                route_partition["reasons"].append("route_partition_kind_missing")
            if kinds and kinds[-1] != "boss":
                route_partition["reasons"].append("route_partition_terminal_not_boss")
            for row in matching_rows:
                kind = str(row.get("kind") or "")
                if kind in {"trash", "boss"} and not str(row.get("label") or "").strip():
                    route_partition["reasons"].append("route_partition_target_label_missing")
                if kind in {"trash", "boss"} and not str(row.get("source_guid") or "").strip():
                    route_partition["reasons"].append("route_partition_target_identity_missing")
            if matching_rows and any(value != diagnostic_only for value in diagnostic_values):
                route_partition["reasons"].append("route_partition_diagnostic_flag_drift")
            if worktree_profile is not None:
                declared_diagnostic = worktree_profile.get("diagnostic_only")
                if declared_diagnostic is not None and diagnostic_only != declared_diagnostic:
                    route_partition["reasons"].append("route_partition_profile_diagnostic_mismatch")
                parent = worktree_profile.get("diagnostic_parent_scenario_id")
                if parent and any(row.get("diagnostic_parent_scenario_id") != parent for row in matching_rows):
                    route_partition["reasons"].append("route_partition_parent_identity_mismatch")
                prerequisite = worktree_profile.get("prerequisite_contract")
                if declared_diagnostic is True:
                    if not isinstance(prerequisite, dict) or prerequisite.get("certifies_predecessors") is not False:
                        route_partition["reasons"].append("profile_prerequisite_contract_not_noncertifying")
                    else:
                        expected_precompleted = prerequisite.get("precompleted_boss_entries", [])
                        for row in matching_rows:
                            state = row.get("diagnostic_prerequisite_state")
                            if not isinstance(state, dict):
                                route_partition["reasons"].append("route_partition_prerequisite_state_missing")
                                continue
                            if state.get("certifies_predecessors") is not False:
                                route_partition["reasons"].append("route_partition_prerequisite_certification_enabled")
                            if ("precompleted_boss_entries" not in state
                                    or state.get("precompleted_boss_entries") != expected_precompleted):
                                route_partition["reasons"].append("route_partition_precompleted_boss_identity_mismatch")
                            for key in ("upper_ledge_start", "requires_native_descent_before_engagement"):
                                if key in prerequisite and state.get(key) != prerequisite.get(key):
                                    route_partition["reasons"].append(f"route_partition_prerequisite_{key}_mismatch")
                        if prerequisite.get("requires_native_descent_before_engagement") is True:
                            descent_rows = [row for row in matching_rows if str(row.get("node_kind") or "") == "descent"]
                            preparation_rows = [row for row in matching_rows if row.get("upper_ledge_preparation") is True]
                            if not descent_rows:
                                route_partition["reasons"].append("route_partition_native_descent_node_missing")
                            elif any(row.get("descent_action") != "native_jump_or_fall" for row in descent_rows):
                                route_partition["reasons"].append("route_partition_native_descent_action_invalid")
                            if not preparation_rows:
                                route_partition["reasons"].append("route_partition_upper_ledge_preparation_missing")
                            elif descent_rows and not any(
                                isinstance(prep.get("z"), (int, float))
                                and isinstance(descent.get("z"), (int, float))
                                and prep["z"] > descent["z"]
                                for prep in preparation_rows for descent in descent_rows
                            ):
                                route_partition["reasons"].append("route_partition_upper_ledge_height_invalid")
            route_partition["passed"] = not route_partition["reasons"]
            reasons.extend(route_partition["reasons"])
        except (OSError, UnicodeError, ValueError, TypeError):
            reasons.append("worktree_route_manifest_unreadable")
    if reference_route_path is not None:
        try:
            reference_route_sha256 = sha256_file(reference_route_path)
        except OSError:
            reasons.append("reference_route_manifest_unreadable")

    if worktree_profile is not None and reference_profile is not None and worktree_profile != reference_profile:
        reasons.append("runtime_profile_differs_from_reference")
    if route_sha256 is not None and reference_route_sha256 is not None and route_sha256 != reference_route_sha256:
        reasons.append("runtime_route_differs_from_reference")

    dvc_status = None
    if require_dvc_lineage:
        dvc_environment = os.environ.copy()
        # A capture launched by ``pixi run`` inherits the caller's manifest
        # path.  The DVC check intentionally runs in the reviewed worktree;
        # leaving the caller locator set produces a warning on otherwise clean
        # output and makes the exact human-text check reject itself.
        dvc_environment.pop("PIXI_PROJECT_MANIFEST", None)
        result = subprocess.run(
            ["pixi", "run", "dvc", "status", "validation_scenarios", "--json"],
            cwd=worktree,
            env=dvc_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        dvc_status = result.stdout.strip()
        if result.returncode != 0 or not _dvc_status_is_clean(dvc_status):
            reasons.append("runtime_route_dvc_lineage_dirty")

    return {
        "profile_name": profile_name,
        "profile_manifest": str(worktree / profile_relative),
        "route_manifest": str(route_path) if route_path else None,
        "route_sha256": route_sha256,
        "reference_route_sha256": reference_route_sha256,
        "matching_route_rows": route_rows,
        "scenario_id": selected_scenario_id,
        "pool_tag_filter": (
            worktree_profile.get("pool_tag_filter")
            if isinstance(worktree_profile, dict) else None
        ),
        "route_partition": route_partition,
        "dvc_stage": "validation_scenarios",
        "dvc_status": dvc_status,
        "reasons": reasons,
        "passed": not reasons,
    }


def _artifact_record(path: Path, kind: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"immutable artifact missing: {path}")
    return {
        "kind": kind,
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "immutable": True,
    }


def bounded_native_shutdown(
    process: subprocess.Popen[bytes], wait_seconds: float,
) -> dict[str, Any]:
    """Request native cleanup and wait for the child within a hard budget.

    The caller still owns process-group escalation after this function
    returns.  Keeping the native request separate makes the operator-abort
    path testable without starting a worldserver and ensures repeated Ctrl-C
    cannot turn cleanup into an uncaught traceback.
    """
    result: dict[str, Any] = {
        "commands_sent": False,
        "operator_interrupted": False,
        "error": None,
        "exited": process.poll() is not None,
        "wait_seconds": wait_seconds,
    }
    if result["exited"]:
        return result
    if process.stdin is None:
        result["error"] = "native_shutdown_stdin_unavailable"
        return result
    try:
        process.stdin.write(b"botauto stop\nbotauto status\nserver exit\n")
        process.stdin.flush()
        result["commands_sent"] = True
    except (BrokenPipeError, OSError) as error:
        result["error"] = f"native_shutdown_write:{type(error).__name__}:{error}"
        return result
    deadline = time.monotonic() + wait_seconds
    while process.poll() is None and time.monotonic() < deadline:
        try:
            process.wait(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            continue
        except KeyboardInterrupt:
            result["operator_interrupted"] = True
            continue
    result["exited"] = process.poll() is not None
    if not result["exited"]:
        result["error"] = f"native_shutdown_timeout:{wait_seconds:g}s"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, default=None)
    parser.add_argument("--server-log-output", type=Path, default=None)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--build-attestation", type=Path, default=None)
    parser.add_argument("--worktree", type=Path, default=ROOT)
    parser.add_argument(
        "--scenario-id", default=None,
        help="exact validation scenario partition to execute; defaults to --runtime-profile",
    )
    parser.add_argument(
        "--runtime-profile", default=None,
        help="exact runtime profile to select; defaults to blackwing_descent_10n",
    )
    parser.add_argument(
        "--pool-tag", default=None,
        help="optional exact pool tag; must match the selected runtime profile",
    )
    parser.add_argument(
        "--observe-sec", type=int, default=0,
        help=(
            "optional diagnostic wall-clock limit; 0 (the canonical default) "
            "runs until the terminal acceptance gates are satisfied"
        ),
    )
    parser.add_argument("--startup-timeout-sec", type=int, default=180)
    parser.add_argument("--required-stable-statuses", type=int, default=3)
    parser.add_argument("--semantic-stall-sec", type=int, default=300)
    parser.add_argument("--semantic-stall-min-samples", type=int, default=12)
    parser.add_argument("--telemetry-timeout-sec", type=int, default=60)
    parser.add_argument(
        "--status-interval-sec", type=float, default=5.0,
        help="status heartbeat cadence; must remain below telemetry timeout",
    )
    parser.add_argument(
        "--diagnose-interval-sec", type=float, default=30.0,
        help="steady-state full semantic diagnosis cadence",
    )
    parser.add_argument(
        "--trace-interval-sec", type=float, default=20.0,
        help="append-only trace-delta export cadence",
    )
    parser.add_argument(
        "--resource-sample-interval-sec", type=float, default=5.0,
        help="low-cost worldserver /proc CPU-tick and RSS sampling cadence",
    )
    args = parser.parse_args()

    binary = args.binary.resolve()
    config = args.config.resolve()
    output = args.output.resolve()
    worktree = args.worktree.resolve()
    profile_name = args.runtime_profile or args.scenario_id or "blackwing_descent_10n"
    scenario_id = args.scenario_id or profile_name
    if args.runtime_profile and args.scenario_id and args.runtime_profile != args.scenario_id:
        raise SystemExit("runtime profile and scenario ID must identify the same partition")
    raw_output = (args.raw_output or output.with_name(f"{output.stem}.raw.jsonl")).resolve()
    server_log_output = (
        args.server_log_output or output.with_name(f"{output.stem}.worldserver.log")
    ).resolve()
    if output.exists():
        raise SystemExit("output already exists; phase1 artifacts are immutable")
    if raw_output.exists():
        raise SystemExit("raw output already exists; phase1 artifacts are immutable")
    if server_log_output.exists():
        raise SystemExit("server log output already exists; phase1 artifacts are immutable")
    if not binary.is_file() or not config.is_file():
        raise SystemExit("binary and config must exist")
    if args.observe_sec < 0 or 0 < args.observe_sec < 30 or args.required_stable_statuses < 2:
        raise SystemExit(
            "observation must be uncapped (0) or at least 30 seconds and require at least two stable statuses"
        )
    if args.semantic_stall_sec < 60 or args.semantic_stall_min_samples < 3:
        raise SystemExit("semantic stall detection requires at least 60 seconds and three samples")
    if args.telemetry_timeout_sec < 15:
        raise SystemExit("telemetry freshness timeout must be at least 15 seconds")
    if any(interval <= 0 for interval in (
        args.status_interval_sec, args.diagnose_interval_sec, args.trace_interval_sec,
        args.resource_sample_interval_sec,
    )):
        raise SystemExit("telemetry intervals must be positive")
    if any(interval >= args.telemetry_timeout_sec for interval in (
        args.status_interval_sec, args.diagnose_interval_sec, args.trace_interval_sec,
    )):
        raise SystemExit("telemetry intervals must be shorter than the freshness timeout")
    preflight = preflight_runtime_exclusions(worktree)
    if not preflight["passed"]:
        raise SystemExit("capture preflight rejected: " + ",".join(preflight["reasons"]))

    identity_before = git_identity(worktree)
    if not identity_before["clean"]:
        raise SystemExit("canonical phase1 capture requires a clean worktree")
    runtime_assets = validate_runtime_profile_assets(
        worktree,
        profile_name=profile_name,
        scenario_id=scenario_id,
        pool_tag=args.pool_tag,
    )
    if not runtime_assets["passed"]:
        raise SystemExit("runtime profile assets rejected: " + ",".join(runtime_assets["reasons"]))
    route_manifest = runtime_assets.get("route_manifest")
    drudge_frozen_anchors = _frozen_drudge_member_anchors(
        Path(route_manifest) if isinstance(route_manifest, str) else None
    )
    if (profile_name == "blackwing_descent_10n" or profile_name.endswith("_magmaw_diagnostic")) \
            and set(drudge_frozen_anchors) != set(range(1, 11)):
        raise SystemExit("runtime profile assets rejected: drudge_frozen_member_anchors_missing")
    build_provenance = validate_build_receipt(
        args.build_receipt.resolve(),
        (worktree / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").resolve(),
        worktree, binary, config,
        args.build_attestation.resolve() if args.build_attestation is not None else None,
    )
    if not build_provenance.get("valid"):
        raise SystemExit("build receipt rejected: " + ",".join(build_provenance.get("rejections", [])))

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    recovery_required = profile_name == "blackwing_descent_10n"
    drudge_required = profile_name == "blackwing_descent_10n" or profile_name.endswith("_magmaw_diagnostic")
    stable: list[dict[str, Any]] = []
    last_rejections: list[str] = ["no_status_observed"]
    startup_error: str | None = None
    process: subprocess.Popen[bytes] | None = None
    telemetry_scheduler: TelemetryScheduler | None = None
    telemetry_command_counts = {"status": 0, "diagnose": 0, "trace": 0}
    operator_interrupt = False
    shutdown_error: str | None = None
    stop_commands_sent = False
    resource_samples: list[dict[str, Any]] = []
    resource_sampling_errors: list[str] = []
    resource_sampling_error_count = 0
    resource_sample_sequence = 0
    try:
        resource_tick_rate = int(os.sysconf(os.sysconf_names["SC_CLK_TCK"]))
    except (AttributeError, KeyError, OSError, ValueError):
        resource_tick_rate = None
    forced_evidence_report: dict[str, Any] = {
        "requested": False,
        "gate_passed": False,
        "missing_channels": ["diagnosis", "trace"],
        "rejections": ["forced_bundle_not_requested"],
    }
    terminal_failure: dict[str, Any] = {"detected": False}
    flush_forced_evidence_callback: Any = None

    def request_final_evidence(reason: str) -> dict[str, Any]:
        nonlocal operator_interrupt
        if forced_evidence_report.get("requested") is True:
            return forced_evidence_report
        if flush_forced_evidence_callback is None or process is None or process.poll() is not None:
            return {
                "requested": False,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": ["forced_bundle_process_unavailable"],
                "reason": reason,
            }
        try:
            report = flush_forced_evidence_callback()
            report["reason"] = reason
            return report
        except KeyboardInterrupt:
            operator_interrupt = True
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            return {
                "requested": True,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": ["forced_bundle_operator_interrupted"],
                "reason": reason,
            }
        except BaseException as error:
            return {
                "requested": True,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": [f"forced_bundle_error:{type(error).__name__}:{error}"],
                "reason": reason,
            }
    server_log_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".raid-phase1-worldserver-", suffix=".log.tmp", dir=server_log_output.parent, delete=False
    ) as log:
        log_path = Path(log.name)
        process = subprocess.Popen(
            [str(binary), "--config", str(config)], cwd=worktree, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )

        try:
            wait_for_prompt(process, log_path, args.startup_timeout_sec)
            assert process.stdin is not None
            # Bind the run to the explicitly selected frozen runtime profile.
            # The test worldserver configuration deliberately has AutoStart
            # disabled, so an explicit native operator command is required;
            # omitting it would only poll an inactive default cohort forever.
            if profile_name == "blackwing_descent_10n":
                process.stdin.write(b"botauto start blackwing_descent_10n\n")
            else:
                process.stdin.write((f"botauto start {profile_name}\n").encode())
            process.stdin.flush()
            time.sleep(1.0)
            # Canonical raid validation is terminal-gate driven. Raid and boss
            # duration alone must never end an otherwise healthy run. A
            # positive limit remains available only for explicitly bounded
            # diagnostics and tests; zero is deliberately uncapped.
            deadline = time.monotonic() + args.observe_sec if args.observe_sec else None
            telemetry_scheduler = TelemetryScheduler(
                status_interval_sec=args.status_interval_sec,
                diagnose_interval_sec=args.diagnose_interval_sec,
                trace_interval_sec=args.trace_interval_sec,
            )
            log_cursor = JsonLogCursor(log_path)
            monitor_statuses: list[dict[str, Any]] = []
            diagnosis_count = 0
            trace_count = 0
            latest_diagnosis: dict[str, Any] | None = None
            recovery_accepted = not recovery_required
            drudge_accepted = not drudge_required
            readycheck_requested_for: tuple[Any, ...] | None = None
            semantic_progress_state: dict[str, Any] = {}
            last_semantic_progress_at = time.monotonic()
            unchanged_semantic_samples = 0
            semantic_stall: dict[str, Any] = {"detected": False}
            monitor_started_at = time.monotonic()
            telemetry_freshness: dict[str, dict[str, float | int]] = {}
            telemetry_abort: dict[str, Any] = {"detected": False}

            next_resource_sample_at = monitor_started_at

            def record_process_resource_sample(*, force: bool = False) -> None:
                nonlocal next_resource_sample_at, resource_sample_sequence
                nonlocal resource_sampling_error_count
                now = time.monotonic()
                if not force and now < next_resource_sample_at:
                    return
                if process.poll() is not None:
                    return
                try:
                    resource_samples.append(process_resource_sample(
                        process.pid,
                        sample_sequence=resource_sample_sequence,
                        scenario_id=scenario_id,
                        runtime_profile=profile_name,
                        status=monitor_statuses[-1] if monitor_statuses else None,
                    ))
                    resource_sample_sequence += 1
                except (OSError, IndexError, KeyError, TypeError, ValueError) as error:
                    resource_sampling_error_count += 1
                    # Preserve a bounded diagnostic prefix; a persistent
                    # /proc race must not make a long-run report grow without
                    # limit. The summary retains the exact total count.
                    if len(resource_sampling_errors) < 8:
                        resource_sampling_errors.append(f"{type(error).__name__}:{error}")
                finally:
                    next_resource_sample_at = now + args.resource_sample_interval_sec

            # Start the resource series as soon as the worldserver is ready;
            # later rows gain cohort/attempt identity once status is observed.
            record_process_resource_sample(force=True)

            def flush_forced_evidence() -> dict[str, Any]:
                """Retain and independently validate a final evidence bundle.

                Console commands are asynchronous.  Wait for the exact
                identity-bound responses to this request, bounded by the
                telemetry freshness budget, rather than treating a fixed
                sleep as proof that the commands ran.
                """
                nonlocal diagnosis_count, trace_count, latest_diagnosis
                telemetry_scheduler.force_diagnosis(include_trace=True)
                request_started = time.monotonic()
                commands = telemetry_scheduler.commands_due(request_started)
                required_commands = {
                    "botauto diagnose all", "botauto trace all 128 delta",
                }
                if not required_commands.issubset(commands):
                    return {
                        "requested": False,
                        "gate_passed": False,
                        "missing_channels": [
                            channel for channel in ("diagnosis", "trace")
                            if {
                                "diagnosis": "botauto diagnose all",
                                "trace": "botauto trace all 128 delta",
                            }[channel] not in commands
                        ],
                        "rejections": ["forced_request_commands_not_scheduled"],
                        "commands": commands,
                    }
                for command in commands:
                    if command == "botauto status":
                        telemetry_command_counts["status"] += 1
                    elif command == "botauto diagnose all":
                        telemetry_command_counts["diagnose"] += 1
                    elif command == "botauto trace all 128 delta":
                        telemetry_command_counts["trace"] += 1
                process.stdin.write(("\n".join(commands) + "\n").encode())
                process.stdin.flush()
                observations: list[tuple[dict[str, Any], float]] = []
                expected_status = monitor_statuses[-1] if monitor_statuses else None
                deadline = request_started + args.telemetry_timeout_sec
                report: dict[str, Any] = {
                    "requested": True,
                    "gate_passed": False,
                    "missing_channels": ["diagnosis", "trace"],
                    "rejections": ["forced_responses_not_observed"],
                    "commands": commands,
                }
                while time.monotonic() < deadline:
                    time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
                    record_process_resource_sample()
                    observed_at = time.monotonic()
                    for row in log_cursor.read_new_rows():
                        action = row.get("action")
                        if action == "botauto_diagnose":
                            diagnosis_count += 1
                            latest_diagnosis = row
                            observations.append((row, observed_at))
                        elif action == "botauto_trace":
                            trace_count += 1
                            observations.append((row, observed_at))
                    report = validate_forced_evidence_bundle(
                        observations,
                        expected_status,
                        requested_at_monotonic=request_started,
                        freshness_timeout_seconds=args.telemetry_timeout_sec,
                    )
                    report["requested"] = True
                    report["commands"] = commands
                    if report["gate_passed"]:
                        break
                report["response_wait_seconds"] = round(time.monotonic() - request_started, 3)
                return report

            flush_forced_evidence_callback = flush_forced_evidence

            while (deadline is None or time.monotonic() < deadline) and not (
                len(stable) >= args.required_stable_statuses
                and recovery_accepted and drudge_accepted
            ):
                if process.poll() is not None:
                    break
                record_process_resource_sample()
                due_commands = telemetry_scheduler.commands_due(time.monotonic())
                if due_commands:
                    # Diagnosis carries the exact current decision per bot;
                    # trace is an incremental export so a long raid does not
                    # replay each bot's cumulative 128-entry history every
                    # five seconds. The server cursor retains every edge
                    # unless its bounded in-memory history was overrun.
                    for command in due_commands:
                        if command == "botauto status":
                            telemetry_command_counts["status"] += 1
                        elif command == "botauto diagnose all":
                            telemetry_command_counts["diagnose"] += 1
                        elif command == "botauto trace all 128 delta":
                            telemetry_command_counts["trace"] += 1
                    process.stdin.write(("\n".join(due_commands) + "\n").encode())
                    process.stdin.flush()
                    time.sleep(1.0)
                    new_statuses: list[dict[str, Any]] = []
                    for row in log_cursor.read_new_rows():
                        action = row.get("action")
                        if action == "botauto_status":
                            new_statuses.append(row)
                        elif action == "botauto_diagnose":
                            diagnosis_count += 1
                            latest_diagnosis = row
                        elif action == "botauto_trace":
                            trace_count += 1
                    monitor_statuses.extend(new_statuses)
                    for status in new_statuses:
                        telemetry_scheduler.observe_status(status)
                        accepted, rejections = accepted_foundation_status(
                            status,
                            profile_name=profile_name,
                            route_partition=runtime_assets.get("route_partition"),
                        )
                        last_rejections = rejections
                        if accepted:
                            stable.append(status)
                        else:
                            stable.clear()
                        failure_reason, failure_rejections = terminal_runtime_failure_reason(
                            status, profile_name=profile_name,
                        )
                        if failure_reason is not None:
                            forced_evidence_report = request_final_evidence(
                                "terminal_runtime_failure"
                            )
                            terminal_failure = {
                                "detected": True,
                                "classification": "gameplay_failure",
                                "failure_reason": failure_reason,
                                "status_rejections": failure_rejections,
                                "route": status.get("validation_route"),
                                "raid_runtime": status.get("raid_runtime"),
                                "elapsed_seconds": round(
                                    time.monotonic() - monitor_started_at, 3
                                ),
                                "final_forced_evidence":
                                    forced_evidence_report.get("gate_passed") is True,
                                "final_forced_evidence_report": forced_evidence_report,
                            }
                            if forced_evidence_report.get("gate_passed") is not True:
                                telemetry_abort = {
                                    "detected": True,
                                    "classification": "infrastructure_abort",
                                    "reason": "terminal_failure_forced_evidence_incomplete",
                                    "missing_channels": forced_evidence_report.get(
                                        "missing_channels", []
                                    ),
                                    "rejections": forced_evidence_report.get(
                                        "rejections", []
                                    ),
                                    "elapsed_seconds": round(
                                        time.monotonic() - monitor_started_at, 3
                                    ),
                                }
                            break
                    if terminal_failure.get("detected") is True:
                        break
                    telemetry_now = time.monotonic()
                    stale_channels = observe_telemetry_freshness(
                        telemetry_freshness,
                        {
                            "status": len(monitor_statuses),
                            "diagnosis": diagnosis_count,
                            "trace": trace_count,
                        },
                        telemetry_now,
                        args.telemetry_timeout_sec,
                    )
                    if stale_channels:
                        forced_evidence_report = request_final_evidence(
                            "telemetry_channel_stale"
                        )
                        telemetry_abort = {
                            "detected": True,
                            "classification": "infrastructure_abort",
                            "reason": "telemetry_channel_stale",
                            "stale_channels": stale_channels,
                            "timeout_seconds": args.telemetry_timeout_sec,
                            "elapsed_seconds": round(telemetry_now - monitor_started_at, 3),
                            "channel_state": telemetry_freshness,
                        }
                        break
                    if monitor_statuses:
                        signature = semantic_progress_signature(
                            monitor_statuses[-1], latest_diagnosis,
                        )
                        if observe_monotonic_semantic_progress(
                            semantic_progress_state,
                            monitor_statuses[-1], latest_diagnosis,
                        ):
                            last_semantic_progress_at = time.monotonic()
                            unchanged_semantic_samples = 1
                        else:
                            unchanged_semantic_samples += 1
                        stalled_for = time.monotonic() - last_semantic_progress_at
                        if (unchanged_semantic_samples >= args.semantic_stall_min_samples
                                and stalled_for >= args.semantic_stall_sec):
                            forced_evidence_report = flush_forced_evidence()
                            semantic_stall = {
                                "detected": True,
                                "stalled_for_seconds": round(stalled_for, 3),
                                "unchanged_samples": unchanged_semantic_samples,
                                "semantic_signature": signature,
                                "monotonic_progress_state": semantic_progress_state,
                                "route": monitor_statuses[-1].get("validation_route"),
                                "raid_runtime": monitor_statuses[-1].get("raid_runtime"),
                                "diagnosis_rows": diagnosis_count,
                                "trace_rows": trace_count,
                                "final_forced_evidence": forced_evidence_report.get("gate_passed") is True,
                                "final_forced_evidence_report": forced_evidence_report,
                            }
                            if forced_evidence_report.get("gate_passed") is not True:
                                telemetry_abort = {
                                    "detected": True,
                                    "classification": "infrastructure_abort",
                                    "reason": "final_forced_evidence_incomplete",
                                    "missing_channels": forced_evidence_report.get("missing_channels", []),
                                    "rejections": forced_evidence_report.get("rejections", []),
                                    "elapsed_seconds": round(time.monotonic() - monitor_started_at, 3),
                                }
                            break
                    if recovery_required:
                        recovery_accepted, _ = accepted_native_recovery(
                            monitor_statuses,
                            profile_name=profile_name,
                        )
                    if drudge_required:
                        drudge_accepted, _ = accepted_drudge_contract(
                            monitor_statuses, frozen_anchors=drudge_frozen_anchors,
                        )
                    if monitor_statuses:
                        runtime = monitor_statuses[-1].get("raid_runtime") or {}
                        status = monitor_statuses[-1]
                        request_identity = native_readycheck_request_identity(status)
                        ready_for_native_check = ready_for_native_readycheck(status)
                        if ready_for_native_check and readycheck_requested_for != request_identity:
                            # This invokes only the native Group ready-check packet path.
                            # It cannot alter encounter, death, movement, or resurrection state.
                            process.stdin.write(b"botauto readycheck\n")
                            process.stdin.flush()
                            readycheck_requested_for = request_identity
                time.sleep(0.25)

            # Capture one last live process sample before native shutdown so
            # the final CPU/RSS interval includes the terminal polling work.
            record_process_resource_sample(force=True)
            if forced_evidence_report.get("requested") is not True:
                forced_evidence_report = request_final_evidence(
                    "terminal_gate_or_process_exit"
                )
            shutdown = bounded_native_shutdown(process, 60.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
            if shutdown["operator_interrupted"]:
                operator_interrupt = True
                startup_error = "KeyboardInterrupt:operator_interrupt"
                signal.signal(signal.SIGINT, signal.SIG_IGN)
        except KeyboardInterrupt:
            # Do not let an operator abort become a Python traceback.  Keep
            # the already captured bytes, issue the native cleanup sequence,
            # and let the immutable report classify this as an infrastructure
            # abort with an explicit operator reason.
            operator_interrupt = True
            startup_error = "KeyboardInterrupt:operator_interrupt"
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            forced_evidence_report = request_final_evidence("operator_interrupt")
            shutdown = bounded_native_shutdown(process, 20.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
        except Exception as error:  # captured as infrastructure evidence below
            startup_error = f"{type(error).__name__}:{error}"
            forced_evidence_report = request_final_evidence("capture_exception")
            shutdown = bounded_native_shutdown(process, 20.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
        finally:
            # Once capture teardown begins, a further SIGINT must not tear
            # through raw-log normalization or immutable report publication.
            # Record the request without raising, finish bounded cleanup, and
            # classify the run as an operator infrastructure abort below.
            def defer_post_capture_interrupt(_signum: int, _frame: Any) -> None:
                nonlocal operator_interrupt, startup_error
                operator_interrupt = True
                startup_error = "KeyboardInterrupt:operator_interrupt"

            signal.signal(signal.SIGINT, defer_post_capture_interrupt)
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, 15)
                    process.wait(timeout=10)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    try:
                        os.killpg(process.pid, 9)
                        process.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
                        pass
                except OSError:
                    pass
        # Move the captured file into its caller-selected immutable location;
        # do not delete the raw worldserver log after capture.
        os.replace(log_path, server_log_output)
        log_bytes = server_log_output.read_bytes()

    normalized_rows = normalized_batch_payload(log_bytes)
    demux_report = evidence_demux_report(normalized_rows, profile_name=profile_name)
    demux_rejections = demux_report["rejections"]
    telemetry_envelopes = _required_telemetry_envelope_report(normalized_rows)
    raw_payload_sha256, raw_payload_rows = write_normalized_batch(raw_output, normalized_rows)
    # The complete log was decoded once into normalized_rows above.  Project
    # final action channels from those parsed payloads instead of decoding the
    # complete log five more times after every uncapped capture.
    statuses = action_payloads(normalized_rows, "botauto_status")
    active_statuses = [
        status for status in statuses
        if isinstance(status.get("raid_runtime"), dict)
        and status["raid_runtime"].get("active") is True
    ]
    diagnoses = action_payloads(normalized_rows, "botauto_diagnose")
    traces = action_payloads(normalized_rows, "botauto_trace")
    profiles = action_payloads(normalized_rows, "botauto_profile")
    stop_rows = action_payloads(normalized_rows, "botauto_stop")
    recovery_accepted, recovery_rejections = (
        accepted_native_recovery(active_statuses, profile_name=profile_name) if recovery_required
        else (True, ["native_recovery_not_required_for_diagnostic_partition"])
    )
    drudge_accepted, drudge_rejections = (
        accepted_drudge_contract(active_statuses, frozen_anchors=drudge_frozen_anchors)
        if drudge_required
        else (True, ["drudge_contract_not_required_for_diagnostic_partition"])
    )
    cleanup_status = statuses[-1] if statuses else {}
    cleanup_ok = cleanup_status.get("bots") == 0 and cleanup_status.get("lease_count") == 0
    postflight = preflight_runtime_exclusions(worktree)
    process_absent = not postflight["process_overlap"]
    forbidden_entries = _forbidden_assistance_entries(normalized_rows)
    identity_after = git_identity(worktree)
    identity_stable = identity_before == identity_after
    process_return_code = process.returncode if process is not None else None
    semantic_stall = locals().get("semantic_stall", {"detected": False})
    telemetry_abort = locals().get("telemetry_abort", {"detected": False})
    resource_summary = summarize_process_resource_samples(
        resource_samples,
        tick_rate=resource_tick_rate,
        sampling_errors=resource_sampling_errors,
        sampling_error_count=resource_sampling_error_count,
    )
    # From this point through the two immutable output writes, ignore another
    # interrupt. Any prior deferred interrupt is already reflected in the
    # variables used to construct the report and success classification.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    success = (
        startup_error is None
        and operator_interrupt is False
        and process_return_code == 0
        and len(stable) >= args.required_stable_statuses
        and recovery_accepted
        and drudge_accepted
        and cleanup_ok
        and bool(stop_rows and stop_rows[-1].get("ok") is True)
        and process_absent
        and postflight["passed"]
        and not forbidden_entries
        and not demux_rejections
        and telemetry_envelopes["gate_passed"]
        and len(profiles) == 1
        and profiles[0].get("ok") is True
        and profiles[0].get("cohort_id") == "default"
        and profiles[0].get("active_profile") == profile_name
        and identity_stable
        and terminal_failure.get("detected") is not True
        and semantic_stall.get("detected") is not True
        and telemetry_abort.get("detected") is not True
        and forced_evidence_report.get("gate_passed") is True
        and bool(diagnoses)
        and bool(traces)
    )
    report = {
        "schema_version": 1,
        "capture_id": f"cata_raid_phase1_{profile_name}_v1",
        "classification": "success" if success else (
            "diagnostic_only" if forbidden_entries else (
            "infrastructure_abort" if (
                startup_error
                or operator_interrupt
                or process_return_code != 0
                or telemetry_abort.get("detected")
                or not process_absent
                or not postflight["passed"]
                or not cleanup_ok
                or not identity_stable
                or bool(demux_rejections)
                or not telemetry_envelopes["gate_passed"]
                or forced_evidence_report.get("gate_passed") is not True
            ) else (
                "gameplay_failure"
                if terminal_failure.get("detected") is True
                else "incomplete_evidence"
            ))
        ),
        "started_at_utc": started_utc,
        "identity": identity_before,
        "scenario_id": scenario_id,
        "runtime_profile": profile_name,
        "pool_tag_filter": runtime_assets.get("pool_tag_filter"),
        "identity_stable_during_run": identity_stable,
        "build_provenance": build_provenance,
        "runtime_profile_assets": runtime_assets,
        "binary_sha256": build_provenance.get("binary_sha256"),
        "config_sha256": sha256_file(config),
        "worldserver_exit_code": process_return_code,
        "startup_error": startup_error,
        "operator_interrupt": operator_interrupt,
        "shutdown_error": shutdown_error,
        "native_shutdown": {
            "commands_sent": stop_commands_sent,
            "bounded_wait_seconds": 20 if operator_interrupt else 60,
            "operator_reason": "operator_interrupt" if operator_interrupt else None,
        },
        "resource_sampling": {
            "source": "proc_pid_stat_and_proc_pid_status_via_capture_no_bots_baseline",
            "interval_seconds": args.resource_sample_interval_sec,
            "samples_retained": True,
            "summary": resource_summary,
            "samples": resource_samples,
            "sampling_errors": resource_sampling_errors,
        },
        "required_stable_statuses": args.required_stable_statuses,
        "accepted_stable_statuses": len(stable),
        "last_foundation_rejections": last_rejections,
        "native_recovery_accepted": recovery_accepted,
        "native_recovery_required": recovery_required,
        "native_recovery_rejections": recovery_rejections,
        "drudge_contract_accepted": drudge_accepted,
        "drudge_contract_required": drudge_required,
        "drudge_contract_rejections": drudge_rejections,
        "terminal_failure": terminal_failure,
        "semantic_stall": semantic_stall,
        "telemetry_abort": telemetry_abort,
        "telemetry_schedule": {
            "status_interval_seconds": args.status_interval_sec,
            "diagnose_interval_seconds": args.diagnose_interval_sec,
            "trace_interval_seconds": args.trace_interval_sec,
            "commands_sent": telemetry_command_counts,
            "scheduler_state": telemetry_scheduler.state() if telemetry_scheduler is not None else None,
            "material_status_diagnosis": "immediate",
            "stall_bundle": "forced_diagnose_and_trace_delta_before_termination",
            "final_forced_evidence": forced_evidence_report,
        },
        "accepted_raid_runtime": stable[-1].get("raid_runtime") if stable else None,
        "diagnose_observed": bool(diagnoses),
        "trace_observed": bool(traces),
        "required_telemetry_envelopes": telemetry_envelopes,
        "profile_selection_observed": len(profiles) == 1,
        "stop_observed": bool(stop_rows),
        "native_event_evidence": {
            "source": "botauto_status.raid_runtime",
            "ordered_transition_reconstruction": recovery_accepted,
            "rejections": recovery_rejections,
            "synthetic_wipe_or_encounter_command_sent": False,
        },
        "drudge_contract_evidence": {
            "source": "botauto_status.raid_runtime.drudge_charge",
            "independently_reconstructed": drudge_accepted,
            "rejections": drudge_rejections,
            "requirements": "two delivered native Rushes per exact source; one non-early 20000ms interval per source; exact-roster reseparation; exact native tank ownership; any recorded taunts are successful tank casts; tank health-sync hold; all seven offensive slots use trained single-target profiles",
        },
        "forbidden_assistance": {
            "observed": bool(forbidden_entries),
            "entries": forbidden_entries,
            "gate_passed": not forbidden_entries,
            "policy": "native encounter events only; no forced state, teleport, spawn, kill, resurrection, or aura assistance",
        },
        "watchdog": {
            "policy": "capture-process-heartbeat-terminal-gate-driven",
            "heartbeat_rows": len(statuses) + len(diagnoses) + len(traces),
            "wall_clock_mode": "uncapped" if args.observe_sec == 0 else "bounded_diagnostic",
            "observe_window_seconds": args.observe_sec if args.observe_sec else None,
            "startup_timeout_seconds": args.startup_timeout_sec,
            "semantic_stall_seconds": args.semantic_stall_sec,
            "semantic_stall_min_samples": args.semantic_stall_min_samples,
            "telemetry_timeout_seconds": args.telemetry_timeout_sec,
            "telemetry_intervals_seconds": {
                "status": args.status_interval_sec,
                "diagnose": args.diagnose_interval_sec,
                "trace": args.trace_interval_sec,
            },
            "telemetry_commands_sent": telemetry_command_counts,
            "required_channels": ["status", "diagnosis", "trace"],
            "healthy": (
                startup_error is None
                and operator_interrupt is False
                and telemetry_abort.get("detected") is not True
                and forced_evidence_report.get("gate_passed") is True
                and bool(statuses) and bool(diagnoses) and bool(traces)
                and process_return_code == 0 and process_absent
            ),
        },
        "preflight": preflight,
        "postflight": postflight,
        "cleanup": {
            "zero_bots": cleanup_status.get("bots") == 0,
            "zero_leases": cleanup_status.get("lease_count") == 0,
            "stop_observed": bool(stop_rows),
            "stop_ok": bool(stop_rows and stop_rows[-1].get("ok") is True),
            "worldserver_process_absent": process_absent,
            "gate_passed": cleanup_ok and process_absent and bool(stop_rows and stop_rows[-1].get("ok") is True),
        },
        "cleanup_zero_bots_and_leases": cleanup_ok,
        "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "log_bytes": len(log_bytes),
        "raw_log_retained": True,
        "raw_server_log": {
            "path": str(server_log_output),
            "sha256": hashlib.sha256(log_bytes).hexdigest(),
            "bytes": len(log_bytes),
            "immutable": True,
        },
        "raw_normalized_batch": {
            "path": str(raw_output),
            "sha256": raw_payload_sha256,
            "row_count": raw_payload_rows,
            "immutable": True,
        },
        "evidence_demux": {
            "normalized_schema_version": 2,
            "retained_rows": demux_report["retained_rows"],
            "bound_rows": demux_report["bound_rows"],
            "rejected_rows": demux_report["rejected_rows"],
            "unchecked_rows": demux_report["unchecked_rows"],
            "canonical_identity_sha256": demux_report["canonical_identity_sha256"],
            "canonical_roster_sha256": demux_report["canonical_roster_sha256"],
            "required_telemetry_envelopes": demux_report["required_telemetry_envelopes"],
            "channels": dict(Counter(str(row.get("evidence_channel")) for row in normalized_rows)),
            "every_retained_row_demuxed": (
                demux_report["bound_rows"] == demux_report["retained_rows"]
                and demux_report["unchecked_rows"] == 0
            ),
            "identity_rejections": demux_rejections,
            "gate_passed": demux_report["gate_passed"],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report["artifact_inventory"] = [
        _artifact_record(raw_output, "raw_normalized_jsonl"),
        _artifact_record(server_log_output, "raw_worldserver_log"),
    ]
    # The report entry is a deliberate self-reference.  Its digest is the
    # canonical report hash after nulling both self-reference fields; this is
    # stable and independently reproducible without a circular hash.
    report["artifact_inventory"].append(
        {
            "kind": "capture_report",
            "path": str(output),
            "sha256": None,
            "bytes": 0,
            "immutable": True,
            "hash_basis": "canonical_report_with_report_sha256_and_self_inventory_sha256_null",
        }
    )
    for _ in range(8):
        encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        report["artifact_inventory"][-1]["bytes"] = len(encoded)
        hash_payload = json.loads(json.dumps(report))
        hash_payload["report_sha256"] = None
        hash_payload["artifact_inventory"][-1]["sha256"] = None
        report_hash = hashlib.sha256(
            json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        report["artifact_inventory"][-1]["sha256"] = report_hash
        report["report_sha256"] = report_hash
        final_encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if report["artifact_inventory"][-1]["bytes"] == len(final_encoded):
            break
    output.write_bytes(final_encoded)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
