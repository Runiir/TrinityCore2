"""Small projections of existing native and WoWSims evidence; no acceptance authority."""
from __future__ import annotations

from collections import Counter
import math

from tools.raid_program.evidence_inputs import digest


def number(value):
    if value is None or isinstance(value, bool):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite metric")
    return result


def positive(value):
    value = number(value)
    if value is None or value <= 0:
        raise ValueError("missing positive measured duration")
    return value


def compact_stats(stats):
    return {k: v for k, v in stats.items()
            if isinstance(v, (int, float, bool)) and k not in
            ("guid", "entry", "observed_at_ms", "health", "mana")}


def modifier_effects(stats):
    # Preserve the observed source of stat differences without whole aura ledgers.
    result = []
    for row in (stats.get("modifier_ledger") or {}).get("primary_stats", []):
        for effect in row.get("aura_effects", []):
            result.append({"stat": row.get("stat", row.get("stat_index")),
                           **{k: v for k, v in effect.items() if not isinstance(v, (dict, list))}})
    return result


def base_actor(actor, name, spec, role, duration, damage, hps, window):
    damage = number(damage)
    return {"actor": str(actor), "name": name, "spec": spec, "role": role,
            "duration_seconds": duration, "damage": damage,
            "dps": damage / duration if damage is not None else None, "hps": number(hps),
            "window": window, "components": {}, "setup": {}, "activity": {},
            "limitations": [], "identity": {}}


def native_actors(document):
    if "combat_calibration" in document:
        cal = document["combat_calibration"]
        if not (cal.get("window_complete") or cal.get("phase") == "complete") and isinstance(cal.get("previous_window"), dict):
            cal = cal["previous_window"]
        if not (cal.get("window_complete") or cal.get("phase") == "complete"):
            raise ValueError("requires a completed calibration window")
        duration = positive(cal.get("scored_seconds"))
        result = {}
        for bot in cal.get("bots", []):
            actor = str(bot["guid"])
            if actor in result:
                raise ValueError("duplicate native actor")
            window = {"basis": "completed_calibration_scoring_window", "seconds": duration,
                      "start_ms": cal.get("scored_started_at_ms"), "end_ms": cal.get("scored_ended_at_ms")}
            a = base_actor(actor, bot.get("name"), cal.get("target_spec"), bot.get("role"),
                           duration, bot.get("damage"), (bot.get("healer_metrics") or {}).get("effective_hps"), window)
            a["identity"] = {k: cal.get(k) for k in ("server_epoch", "attempt_id", "cohort_id", "mode", "seed")}
            for row in bot.get("spell_damage", []):
                key = str(row["spell_id"])
                if key in a["components"]:
                    raise ValueError("duplicate native spell damage bucket")
                a["components"][key] = {"spell_id": row["spell_id"], "name": row.get("spell_name"),
                    "damage": number(row.get("damage")), "landed_events": row.get("event_count"),
                    "ordinary_casts": None, "triggered_copies": None,
                    "ownership": "combined_or_unresolved", "periodic_split": "unavailable"}
            decisions = [r for r in bot.get("decision_timeline", [])
                         if r.get("elapsed_ms") is not None and 0 <= r["elapsed_ms"] <= duration * 1000]
            submissions = Counter(str(r.get("spell_id")) for r in decisions if r.get("result") == "ok")
            for key, row in a["components"].items():
                row["observed_successful_submissions"] = submissions[key] if decisions else None
            stats = (bot.get("scoring_start_stats") or {}).get("player") or {}
            a["setup"] = {"stats": compact_stats(stats), "modifier_effects": modifier_effects(stats),
                "gear_sha256": digest(bot["gear_profile_observation"]) if bot.get("gear_profile_observation") else None,
                "talents_sha256": digest(bot["active_talent_spell_ids"]) if "active_talent_spell_ids" in bot else None,
                "glyphs_sha256": digest(bot["glyph_property_ids"]) if "glyph_property_ids" in bot else None,
                "reference_setup_sha256": digest(bot["reference_setup"]) if bot.get("reference_setup") else None}
            a["activity"] = {"decision_observations": len(decisions),
                "successful_submission_observations": sum(submissions.values()) if decisions else None,
                "result_counts": dict(Counter(r.get("result", "unknown") for r in decisions)),
                "pet_damage": bot.get("pet_damage"), "off_target_damage": bot.get("off_target_damage"),
                "death_observations": sum(r.get("alive") is False for r in decisions)}
            a["limitations"] = ["Selections are not casts; successful submissions do not prove completion.",
                "Spell buckets combine ownership and proc/periodic damage unless separate evidence resolves it.",
                "Repeated dead samples are observations, not a count of deaths."]
            result[actor] = a
        return result
    if "window" in document and ("actors" in document or "summary" in document):
        summary = document.get("summary", document)
        window = document["window"]
        if not window.get("complete"):
            raise ValueError("requires a complete native timeline window")
        duration = positive(window.get("elapsed_seconds") or
                            ((window["native_boss_death_at_ms"] - window["first_hostile_at_ms"]) / 1000))
        result = {}
        for actor, data in summary.get("actors", {}).items():
            a = base_actor(actor, data.get("name"), data.get("class_spec"), data.get("role"), duration,
                           data.get("damage", {}).get("hostile_originated"), data.get("effective_hps"), window)
            a["identity"] = document.get("identity", {})
            a["activity"] = {"activity": data.get("activity"), "survival": data.get("survival"),
                "target_damage": data.get("target_damage"), "movement_event_count": data.get("movement_event_count"),
                "idle_backoff_event_count": data.get("idle_backoff_event_count"),
                "target_switch_latency_ms": data.get("target_switch_latency_ms")}
            a["limitations"] = ["Landed-event gaps are not casting downtime.",
                "Timeline completeness and phase coverage must be reviewed; DPS comparison is not acceptance."]
            result[str(actor)] = a
        lo, hi = window.get("first_hostile_at_ms"), window.get("native_boss_death_at_ms")
        for e in document.get("events", []):
            if e.get("kind") != "landed" or str(e.get("actor_guid")) not in result:
                continue
            if not (lo <= e["at_ms"] <= hi) or e.get("amount", 0) <= 0:
                continue
            # The existing timeline producer owns hostile-originated accounting.
            a = result[str(e["actor_guid"])]
            key = str(e.get("spell_id"))
            row = a["components"].setdefault(key, {"spell_id": e.get("spell_id"), "damage": 0,
                "landed_events": 0, "owner_damage": 0, "pet_damage": 0, "unknown_owner_damage": 0,
                "periodic_damage": 0, "ordinary_casts": None, "triggered_copies": None})
            row["damage"] += e["amount"]
            row["landed_events"] += 1
            ownership = "pet_damage" if e.get("source_is_pet") is True else "owner_damage" if e.get("source_is_pet") is False else "unknown_owner_damage"
            row[ownership] += e["amount"]
            if e.get("attack_origin") == "periodic":
                row["periodic_damage"] += e["amount"]
        for a in result.values():
            a["completeness"] = document.get("completeness", {})
            from tools.bot_ml.rank_raid_damage_gaps import interval_seconds
            phases = [p for p in document.get("phase_intervals", []) if str(p.get("actor_guid")) == a["actor"]]
            a["activity"]["phase_interval_seconds"] = {
                phase: interval_seconds([(p["start_ms"], p["end_ms"]) for p in phases
                                          if p.get("phase") == phase], lo, hi)
                for phase in sorted({p["phase"] for p in phases if p.get("phase")})}
            a["activity"]["phase_basis"] = "retained actor phase intervals; overlaps between different phases are not resolved"
        return result
    raise ValueError("native input must be a completed calibration report or existing bot timeline JSON")


def simulator_actor(document, player_index=0):
    from tools.bot_ml.review_rotation_mechanics import normalize_wowsims_result
    result = document.get("wowsims_result", document)
    if result.get("schema") != "rotation_review_wowsims_result_v1":
        result = normalize_wowsims_result(result, player_index)
    duration = positive(result.get("avg_iteration_duration_seconds"))
    dps = number(result.get("player_dps", {}).get("avg"))
    if dps is None:
        raise ValueError("WoWSims result has no mean DPS")
    a = base_actor(result.get("player_index", player_index), result.get("player_name"), None, None,
                   duration, dps * duration, None, {"basis": "simulator_mean_iteration", "seconds": duration})
    a["dps_distribution"] = {k: v for k, v in result.get("player_dps", {}).items() if isinstance(v, (int, float))}
    a["iterations"] = result.get("iterations_done")
    for metric in result.get("action_metrics", []):
        identity = metric["identity"]
        key = str(identity.get("id")) if identity.get("kind") == "spell" else f"{identity.get('kind')}:{identity.get('id')}"
        m = metric.get("per_iteration_target_metric_sums", {})
        row = a["components"].setdefault(key, {"spell_id": identity.get("id"), "damage": 0,
            "ordinary_casts": 0, "triggered_copies": 0, "other_tagged_casts": 0,
            "pet_casts": 0, "ticks": 0, "hits": 0, "crits": 0, "pet_damage": 0, "copy_damage": 0})
        damage = number(m.get("damage")) or 0
        row["damage"] += damage
        tag = identity.get("tag", 0)
        pet = metric.get("source", {}).get("kind") == "pet"
        category = "pet_casts" if pet else "triggered_copies" if tag == 71086 else "other_tagged_casts" if tag else "ordinary_casts"
        row[category] += number(m.get("casts")) or 0
        for k in ("ticks", "hits", "crits"):
            row[k] += number(m.get(k)) or 0
        if pet:
            row["pet_damage"] += damage
        if tag == 71086:
            row["copy_damage"] += damage
    a["gates"] = {k: {f: v for f, v in (document.get(k) or {}).items()
                       if f in ("status", "reason", "comparison_admitted", "tuning_admitted")}
                  for k in ("gear_parity", "effective_stat_parity", "consumable_parity", "dps_tuning_gate", "total_dps_comparison_gate")}
    a["gate_binding"] = "source-review gates only; not rebound to this comparison's current native input"
    a["limitations"] = ["Numeric gaps are exploratory until exact setup and reference gates are admitted.",
        "Literal spell IDs are not proof of equivalent actions; aliases and other-action IDs remain separate.",
        "DTR tag 71086 is separated from ordinary casts; other tags remain unclassified.",
        "Mean damage / mean duration can differ from mean DPS; the reconciliation residual preserves this.",
        "Simulator action casts can include per-target counts; they are not automatically player GCD counts."]
    return a


def wcl_actor(document, spec, reference_id=None, reference_actor=None):
    """Use retained WCL catalogs/manifests; do not invent spell damage from casts."""
    if "references" in document:
        refs = [r for r in document["references"] if reference_id is None or r.get("id") == reference_id]
        if len(refs) != 1:
            raise ValueError("select exactly one WCL catalog entry with --reference-id")
        reference = refs[0]
        if spec not in reference.get("actor_dps", {}):
            return None
        dps = number(reference["actor_dps"][spec])
        actor_id, name, activity = spec, spec, {}
    else:
        reference = document
        if reference_id is not None and reference.get("reference_id") != reference_id:
            raise ValueError("WCL reference ID mismatch")
        actors = [a for a in reference.get("actors", [])
                  if (str(a.get("actor_id")) == str(reference_actor) if reference_actor is not None
                      else a.get("class_spec") == spec)]
        if not actors:
            return None
        if len(actors) != 1:
            raise ValueError("ambiguous WCL actor; use --reference-actor")
        actor = actors[0]
        actor_id, name = actor.get("actor_id"), actor.get("source_name")
        dps = number(actor.get("observed_dps"))
        activity = {"completed_casts_by_ability": dict(Counter(c.get("ability", "unknown") for c in actor.get("casts", []))),
                    "cast_basis": "retained WCL manifest casts; not native landed effects"}
    duration = positive(reference.get("duration_sec"))
    a = base_actor(actor_id, name, spec, None, duration, dps*duration if dps is not None else None,
                   None, {"basis": "WCL_full_fight", "seconds": duration,
                          "target_scope": reference.get("target_scope"), "mode": reference.get("mode")})
    a["identity"] = {"url": reference.get("url"), "reference_id": reference.get("id", reference.get("reference_id")),
                     "actor_id": actor_id}
    a["activity"] = activity
    a["limitations"] = ["WCL full fight vs native full window; no phase/duty/gear matching established.",
        "No per-spell WCL damage supplied: entire DPS difference remains unattributed.",
        "Same-spec lookup is a benchmark, not evidence of matched gear or assignment."] + list(reference.get("limitations", []))
    return a
