"""Random encounter events per kill: Magmaw's Massive Crash side from a synthetic combat log."""
from __future__ import annotations

import json

import pytest

from tools.bot_ml import live_validation_encounter_rng as rng

T0 = 1_790_000_000_000
RAID_WIDE = (-288.59, -14.847)  # MassiveCrashRightSpawnPosition, as logged
FAR = (-294.736, -11.431)       # the other Massive Crash dummy
MANIFEST = {"routes": [{"route_node_id": "bwd.magmaw.encounter", "kind": "boss", "source_entry": 41570}]}
ANALYSIS = {"encounters": [{"route_node_id": "bwd.magmaw.encounter", "first_at_ms": T0,
                            "actors": [{"actor_guid": 30001 + i} for i in range(10)]}]}


def crash_hit(at, target, *, dummy=RAID_WIDE, guid=41, pet=False, source_entry=47330, spell=88287):
    return {"kind": "damage", "spell_id": spell, "timestamp_ms": T0 + at, "route_node_id": "bwd.magmaw.encounter",
            "source_entry": source_entry, "source_guid": guid, "source_name": "Massive Crash",
            "source_x": dummy[0] if dummy else None, "source_y": dummy[1] if dummy else None,
            "target_guid": target, "target_name": f"unit{target}", "target_entry": 28017 if pet else 0,
            "amount": 50000}


def log(*events):
    return {"recent_events": list(events), "recent_events_dropped": 0}


def raid_wide_cast(at, players=9, pets=2, **options):
    return [crash_hit(at, 30001 + i, **options) for i in range(players)] + \
           [crash_hit(at + 1, 200 + i, pet=True, **options) for i in range(pets)]


def test_side_comes_from_the_casting_dummy_and_pets_are_not_players():
    events = raid_wide_cast(99_500) + [crash_hit(160_000, 201, dummy=FAR, guid=40, pet=True)]
    result = rng.encounter_rng(log(*events), MANIFEST, ANALYSIS)
    first, second = result["massive_crash"]
    assert first["side"] == "raid_wide" and first["side_basis"] == "source_position"
    assert (first["players_hit"], first["pets_hit"], first["units_hit"], first["raid_size"]) == (9, 2, 11, 10)
    assert first["at_sec"] == 99.5 and first["side_from_hits"] == "raid_wide" and first["basis_conflict"] is False
    assert first["player_names"][0] == "unit30001" and first["damage_total"] == 11 * 50000
    assert second["side"] == "far" and second["players_hit"] == 0 and second["pets_hit"] == 1
    assert second["at_sec"] == 160.0
    assert result["summary"] == {"massive_crash": {"raid_wide": 1, "far": 1, "unknown": 0}}
    assert result["informational"] is True


def test_players_hit_decides_only_without_a_caster_position():
    wide = rng.encounter_rng(log(*raid_wide_cast(0, players=6, dummy=None)), MANIFEST, ANALYSIS)["massive_crash"][0]
    assert wide["side"] == "raid_wide" and wide["side_basis"] == "players_hit" and wide["source_position"] is None
    far = rng.encounter_rng(log(*raid_wide_cast(0, players=3, dummy=None)), MANIFEST, ANALYSIS)["massive_crash"][0]
    assert far["side"] == "far"
    middle = rng.encounter_rng(log(*raid_wide_cast(0, players=4, dummy=None)), MANIFEST, ANALYSIS)["massive_crash"][0]
    assert middle["side"] == "unknown"


def test_position_wins_and_a_contradicting_hit_count_is_flagged():
    crash = rng.encounter_rng(log(*raid_wide_cast(0, players=9, dummy=FAR)), MANIFEST, ANALYSIS)["massive_crash"][0]
    assert crash["side"] == "far" and crash["side_from_hits"] == "raid_wide" and crash["basis_conflict"] is True


def test_casts_are_split_by_source_and_time_gap():
    events = raid_wide_cast(1000) + raid_wide_cast(1000 + rng.CAST_GAP_MS + 500)
    assert len(rng.encounter_rng(log(*events), MANIFEST, ANALYSIS)["massive_crash"]) == 2
    events = [crash_hit(0, 30001), crash_hit(1500, 30002), crash_hit(1600, 30003, guid=40, dummy=FAR)]
    rows = rng.encounter_rng(log(*events), MANIFEST, ANALYSIS)["massive_crash"]
    assert [(row["side"], row["units_hit"]) for row in rows] == [("raid_wide", 2), ("far", 1)]


def test_rule_appears_only_for_its_boss_or_when_it_fired():
    assert rng.encounter_rng(log(), MANIFEST, ANALYSIS)["massive_crash"] == []
    other = {"routes": [{"route_node_id": "x", "kind": "boss", "source_entry": 43296}]}
    assert "massive_crash" not in rng.encounter_rng(log(), other, None)
    fired = rng.encounter_rng(log(*raid_wide_cast(0)), None, None)["massive_crash"][0]
    assert fired["side"] == "raid_wide" and fired["at_sec"] is None and fired["raid_size"] == 10


def test_attach_writes_both_places_and_never_raises(monkeypatch):
    report = {"combat_log": log(*raid_wide_cast(0)), "combat_analysis": json.loads(json.dumps(ANALYSIS))}
    result = rng.attach_encounter_rng(report, MANIFEST)
    assert report["encounter_rng"] is result and report["combat_analysis"]["encounter_rng"] is result

    def explode(*args):
        raise RuntimeError("bug")
    monkeypatch.setattr(rng, "encounter_rng", explode)
    report = {"combat_analysis": {"encounters": []}}
    result = rng.attach_encounter_rng(report, MANIFEST)
    assert result["status"] == "error" and result["error"] == "RuntimeError: bug"
    assert rng.scoreboard_summary(result, "harness") is None


def test_scoreboard_summary_and_run_dir_recompute(tmp_path):
    (tmp_path / "report.json").write_text(json.dumps({"completion_reason": "x"}))
    (tmp_path / "validation_route_manifest.json").write_text(json.dumps(MANIFEST))
    (tmp_path / "combat_analysis.json").write_text(json.dumps(ANALYSIS))
    (tmp_path / "combat_log.json").write_text(json.dumps(log(*raid_wide_cast(99_500))))
    assert rng.rng_from_run_dir(tmp_path) == {"basis": "combat_log_recomputed", "massive_crash": [
        {"side": "raid_wide", "side_basis": "source_position", "at_sec": 99.5, "players_hit": 9, "units_hit": 11}]}
    harness = rng.encounter_rng(log(), MANIFEST, ANALYSIS)
    (tmp_path / "report.json").write_text(json.dumps({"encounter_rng": harness}))
    assert rng.rng_from_run_dir(tmp_path) == {"basis": "harness", "massive_crash": []}
    (tmp_path / "combat_log.json").unlink()
    assert rng.rng_from_run_dir(tmp_path, report={}) is None


@pytest.mark.parametrize("position,side", [((-288.59, -14.8472), "raid_wide"), ((-289.3, -14.2), "raid_wide"),
                                           ((-294.736, -11.431), "far"), ((-290.0, -16.0), "far")])
def test_position_rule_uses_the_scripts_one_yard_test(position, side):
    assert rng.side_from_position(rng.RULES["massive_crash"], 47330, *position) == side
    assert rng.side_from_position(rng.RULES["massive_crash"], 41570, *position) is None
