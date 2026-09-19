"""Validate and join a closed native report with its compact timeline summary.

The raw capture is deliberately outside this adapter.  A report and a
timeline summary are already closed, bounded products, so the shadow packet
builder can validate their shared identity and project only per-actor
death-window facts.  Digests remain row provenance and are never copied into
the model state.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from tools.raid_program.bot_timeline import _report_source


SCHEMA = "shadow_timeline_context_v1"
SUMMARY_SCHEMA = "cata_raid_bot_timeline_summary_v1"
UNKNOWN_REASON = "native_report_and_timeline_summary_not_supplied"
UNKNOWN_FIELDS = ("absorption", "mana", "overheal", "threat", "mitigation")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}_unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}_must_be_object")
    return value, _sha256(raw)


def _guid(value: Any) -> int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value)
        except ValueError:
            return value
        return parsed if parsed else None
    return None


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, int) and isinstance(right, str):
        return str(left) == right
    if isinstance(left, str) and isinstance(right, int):
        return left == str(right)
    return left == right


def _required_equal(label: str, supplied: Mapping[str, Any], observed: Any) -> None:
    key = label
    if supplied.get(key) in (None, ""):
        raise ValueError(f"identity_{key}_missing")
    if observed in (None, "") or not _same(supplied[key], observed):
        raise ValueError(f"identity_{key}_mismatch")


def _actor_identity(review: Mapping[str, Any]) -> dict[int | str, dict[str, Any]]:
    input_section = review.get("jev_input")
    state = input_section.get("state", {}) if isinstance(input_section, Mapping) else {}
    boss = state.get("boss_dps_review", {}) if isinstance(state, Mapping) else {}
    rows = boss.get("actor_identity") if isinstance(boss, Mapping) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("actor_identity_missing")
    result: dict[int | str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("actor_identity_invalid")
        guid = _guid(row.get("bot_guid", row.get("actor_guid")))
        if guid is None or guid in result:
            raise ValueError("actor_identity_invalid")
        result[guid] = dict(row)
    return result


def _report_roster_guids(report: Mapping[str, Any]) -> set[int | str]:
    runtime = report.get("accepted_raid_runtime")
    roster = runtime.get("roster") if isinstance(runtime, Mapping) else None
    if not isinstance(roster, list) or not roster:
        raise ValueError("native_report_roster_missing")
    result: set[int | str] = set()
    for row in roster:
        if not isinstance(row, Mapping):
            raise ValueError("native_report_roster_invalid")
        guid = _guid(row.get("guid", row.get("bot_guid", row.get("actor_guid"))))
        if guid is None or guid in result:
            raise ValueError("native_report_roster_invalid")
        result.add(guid)
    return result


def _summary_actors(summary: Mapping[str, Any]) -> dict[int | str, dict[str, Any]]:
    rows = summary.get("actors")
    if not isinstance(rows, Mapping) or not rows:
        raise ValueError("timeline_summary_actors_missing")
    result: dict[int | str, dict[str, Any]] = {}
    for key, value in rows.items():
        guid = _guid(key)
        if guid is None or not isinstance(value, Mapping):
            raise ValueError("timeline_summary_actor_invalid")
        if guid in result:
            raise ValueError("timeline_summary_actor_invalid")
        if value.get("actor_guid") is not None and not _same(value["actor_guid"], guid):
            raise ValueError("timeline_summary_actor_guid_mismatch")
        result[guid] = dict(value)
    return result


def _unknown_metric(reason: str) -> dict[str, Any]:
    return {"status": "unknown", "reason": reason}


def _metric(source: Mapping[str, Any] | None, key: str, reason: str) -> dict[str, Any]:
    if not isinstance(source, Mapping) or key not in source or not _finite(source[key]):
        return _unknown_metric(reason)
    return {"status": "observed", "value": source[key]}


def _survival(source: Any) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {"status": "unknown", "reason": "survival_missing"}
    fields = (
        "alive_at_end",
        "alive_at_end_basis",
        "death_observed",
        "death_observed_at_ms",
        "first_activity_at_ms",
        "last_activity_at_ms",
        "scope",
    )
    result = {key: source[key] for key in fields if key in source}
    return {"status": "observed", **result} if result else {
        "status": "unknown",
        "reason": "survival_fields_missing",
    }


def _actor_projection(
    row: Mapping[str, Any],
    identity: Mapping[str, Any],
    window: Mapping[str, Any],
) -> dict[str, Any]:
    damage = row.get("damage") if isinstance(row.get("damage"), Mapping) else None
    role = str(identity.get("role") or row.get("role") or "unknown").lower()
    total = _metric(damage, "hostile_originated", "damage_missing")
    owned = _metric(damage, "owned_source", "owned_source_damage_missing")
    if total["status"] == "observed" and owned["status"] == "observed":
        owner = {
            "status": "observed",
            "value": total["value"] - owned["value"],
            "basis": "hostile_originated_minus_owned_source",
        }
    else:
        owner = _unknown_metric("owner_damage_split_unavailable")

    # The native elapsed HPS is the death-window value.  Do not fall back to
    # the retained review ledger's combat-duration HPS.
    hps = _metric(
        row,
        "native_elapsed_hps_through_death",
        "native_elapsed_hps_through_death_missing",
    )
    if hps["status"] == "observed":
        hps["basis"] = "native_elapsed_hps_through_death"
    healing = _metric(
        row,
        "effective_healing_through_death",
        "effective_healing_through_death_missing",
    )
    damage_dps = _metric(damage, "dps", "death_window_dps_missing")
    if damage_dps["status"] == "observed":
        damage_dps["basis"] = "timeline_summary_death_window"

    activity_source = row.get("activity")
    if role == "healer":
        activity = {
            "status": "unknown",
            "reason": "healer_damage_activity_proxy_forbidden",
        }
    elif isinstance(activity_source, Mapping):
        activity = {
            "status": "observed",
            **{
                key: activity_source[key]
                for key in (
                    "active_seconds",
                    "fresh_attack_active_seconds",
                    "longest_fresh_attack_outage_ms",
                    "metric_scope",
                )
                if key in activity_source
            },
        }
        if len(activity) == 1:
            activity = {"status": "unknown", "reason": "activity_fields_missing"}
    else:
        activity = {"status": "unknown", "reason": "activity_missing"}

    return {
        "role": role,
        "class_spec": identity.get("class_spec", row.get("class_spec")),
        "name": identity.get("bot_name", row.get("name")),
        "window": {
            "basis": window.get("basis"),
            "first_hostile_at_ms": window.get("first_hostile_at_ms"),
            "native_boss_death_at_ms": window.get("native_boss_death_at_ms"),
            "elapsed_seconds": window.get("elapsed_seconds"),
        },
        "dps": damage_dps,
        "hps": hps,
        "damage": {
            "total_hostile_originated": total,
            "owner": owner,
            "owned_source": owned,
        },
        "healing": healing,
        "survival": _survival(row.get("survival")),
        "activity": activity,
        "unknown_metrics": {
            key: _unknown_metric("not_present_in_timeline_summary")
            for key in UNKNOWN_FIELDS
        },
    }


def unknown_context(reason: str = UNKNOWN_REASON) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a review carrying explicit unknown timeline context."""
    provenance = {"schema": SCHEMA, "status": "unknown", "reason": reason}
    return {
        "schema": SCHEMA,
        "status": "unknown",
        "reason": reason,
        "window": None,
        "actors": {},
        "provenance": provenance,
    }, provenance


def join_timeline_context(
    review: Mapping[str, Any],
    *,
    native_report: Path | None,
    timeline_summary: Path | None,
    supplied_identity: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Join validated summary facts into a private review context.

    The returned review is safe to pass to packet builders.  The returned
    provenance is for the retained shadow row and is intentionally separate
    from model-visible state.
    """
    if native_report is None and timeline_summary is None:
        joined = deepcopy(dict(review))
        state = joined.setdefault("jev_input", {}).setdefault("state", {})
        boss = state.setdefault("boss_dps_review", {})
        context, provenance = unknown_context()
        boss["_shadow_timeline_context"] = context
        return joined, provenance
    if native_report is None or timeline_summary is None:
        raise ValueError("native_report_and_timeline_summary_must_be_paired")

    report, report_file_sha256 = _read_json(native_report, "native_report")
    summary, summary_file_sha256 = _read_json(timeline_summary, "timeline_summary")
    review_source_sha256 = review.get("source_sha256")
    if review_source_sha256 != report_file_sha256:
        raise ValueError("review_source_sha256_mismatch_native_report_file")

    run_id = review.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("review_run_id_missing")
    _required_equal("run_id", supplied_identity, run_id)
    input_section = review.get("jev_input")
    state = input_section.get("state") if isinstance(input_section, Mapping) else None
    if not isinstance(state, Mapping) or state.get("run_id") != run_id:
        raise ValueError("review_state_run_id_mismatch")

    runtime = report.get("accepted_raid_runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("native_report_runtime_missing")
    _required_equal("server_epoch", supplied_identity, runtime.get("server_epoch"))
    _required_equal("attempt_id", supplied_identity, runtime.get("attempt_id"))
    report_identity = report.get("identity")
    if not isinstance(report_identity, Mapping):
        raise ValueError("native_report_source_identity_missing")
    _required_equal("source_commit", supplied_identity, report_identity.get("head"))
    _required_equal("binary_sha256", supplied_identity, report.get("binary_sha256"))
    _required_equal("config_sha256", supplied_identity, report.get("config_sha256"))
    if supplied_identity.get("report_sha256") not in (None, ""):
        _required_equal("report_sha256", supplied_identity, report.get("report_sha256"))
    if supplied_identity.get("route_sha256") not in (None, ""):
        route_assets = report.get("runtime_profile_assets")
        if not isinstance(route_assets, Mapping):
            raise ValueError("native_report_route_identity_missing")
        _required_equal("route_sha256", supplied_identity, route_assets.get("route_sha256"))
    if supplied_identity.get("roster_sha256") not in (None, ""):
        demux = report.get("evidence_demux")
        if not isinstance(demux, Mapping):
            raise ValueError("native_report_roster_identity_missing")
        _required_equal("roster_sha256", supplied_identity, demux.get("canonical_roster_sha256"))

    report_projection, report_source_sha256 = _report_source(report)
    summary_identity = summary.get("identity")
    if not isinstance(summary_identity, Mapping):
        raise ValueError("timeline_summary_identity_missing")
    summary_source = summary_identity.get("source")
    if not isinstance(summary_source, Mapping):
        raise ValueError("timeline_summary_source_missing")
    if summary_source.get("report_source") != report_projection:
        raise ValueError("timeline_summary_report_source_projection_mismatch")
    if summary_source.get("report_source_sha256") != report_source_sha256:
        raise ValueError("timeline_summary_report_source_digest_mismatch")
    if not _same(summary_identity.get("server_epoch"), supplied_identity.get("server_epoch")):
        raise ValueError("timeline_summary_server_epoch_mismatch")
    if not _same(summary_identity.get("attempt_id"), supplied_identity.get("attempt_id")):
        raise ValueError("timeline_summary_attempt_id_mismatch")

    window = summary.get("window")
    if (
        summary.get("schema") != SUMMARY_SCHEMA
        or summary.get("clear_accepted") is not True
        or not isinstance(window, Mapping)
        or window.get("complete") is not True
        or window.get("basis") != "native_trace_boss_death"
        or not _finite(window.get("first_hostile_at_ms"))
        or not _finite(window.get("native_boss_death_at_ms"))
        or not _finite(window.get("elapsed_seconds"))
        or window["elapsed_seconds"] < 0
        or window["native_boss_death_at_ms"] < window["first_hostile_at_ms"]
    ):
        raise ValueError("timeline_summary_window_not_complete_native_death")

    identities = _actor_identity(review)
    summary_actors = _summary_actors(summary)
    identity_guids = set(identities)
    if set(summary_actors) != identity_guids:
        raise ValueError("timeline_summary_actor_guid_binding_mismatch")
    if _report_roster_guids(report) != identity_guids:
        raise ValueError("native_report_actor_guid_binding_mismatch")
    for guid, row in summary_actors.items():
        expected = identities[guid]
        for key in ("role", "class_spec"):
            if row.get(key) is not None and expected.get(key) is not None and row[key] != expected[key]:
                raise ValueError(f"timeline_summary_actor_{key}_mismatch")

    actors = {
        str(guid): _actor_projection(row, identities[guid], window)
        for guid, row in sorted(summary_actors.items(), key=lambda item: str(item[0]))
    }
    provenance = {
        "schema": SCHEMA,
        "status": "observed",
        "native_report_sha256": report_file_sha256,
        "declared_report_sha256": report.get("report_sha256"),
        "timeline_summary_sha256": summary_file_sha256,
        "report_source_sha256": report_source_sha256,
        "run_id": run_id,
        "server_epoch": supplied_identity.get("server_epoch"),
        "attempt_id": supplied_identity.get("attempt_id"),
        "source_commit": supplied_identity.get("source_commit"),
        "binary_sha256": supplied_identity.get("binary_sha256"),
        "config_sha256": supplied_identity.get("config_sha256"),
        "actor_guids": sorted(str(guid) for guid in identity_guids),
        "window_basis": window.get("basis"),
    }
    context = {
        "schema": SCHEMA,
        "status": "observed",
        "window": {
            "basis": window.get("basis"),
            "first_hostile_at_ms": window.get("first_hostile_at_ms"),
            "native_boss_death_at_ms": window.get("native_boss_death_at_ms"),
            "elapsed_seconds": window.get("elapsed_seconds"),
        },
        "actors": actors,
        # Kept on the private review only.  Packet builders must not copy it.
        "provenance": provenance,
    }
    joined = deepcopy(dict(review))
    state = joined.setdefault("jev_input", {}).setdefault("state", {})
    boss = state.setdefault("boss_dps_review", {})
    boss["_shadow_timeline_context"] = context
    return joined, provenance


__all__ = ["SCHEMA", "SUMMARY_SCHEMA", "UNKNOWN_REASON", "join_timeline_context", "unknown_context"]
