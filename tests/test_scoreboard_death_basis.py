"""Round 2 (BWD 10N) scoreboard death basis: encounter-scoped reconciliation, the native death
signal conflict, and target-declared boss-window death exemptions (Chimaeron Mortality, user
decision 2026-09-27). Encounter-generic; Magmaw's accepted verdict stays byte-identical."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.raid_program.scoreboard_core import load_target
from tools.raid_program.scoreboard_deaths import (
    ENCOUNTER_RECONCILED_BASIS, ExemptionConfigError, death_exemptions, exemption_start,
)
from tools.raid_program.scoreboard_record import death_evidence
from tools.raid_program.scoreboard_verdict import _encounter_verdict, _Reasons, evaluate_target

ROOT = Path(__file__).resolve().parents[1]
NODE = "bwd.test.encounter"
BOSS = 43296


def lethal(at, target, node=NODE, before=500, source_entry=None):
    source_entry = source_entry if source_entry is not None else (BOSS if node == NODE else 1)
    return {"kind": "damage", "timestamp_ms": at, "route_node_id": node, "target_guid": target,
            "target_name": f"bot{target}", "actor_guid": 0, "source_name": "Boss", "spell_name": "Melee",
            "source_entry": source_entry, "source_guid": 900 if source_entry == BOSS else 77,
            "amount": before, "landed_damage_observation": {"target_health_before_damage": before}}


def boss_hit(at, before, amount, maximum=1000, spell=0, guid=900):
    return {"kind": "damage", "timestamp_ms": at, "route_node_id": NODE, "target_guid": guid, "target_entry": BOSS,
            "actor_guid": 1, "source_guid": 1, "amount": amount, "spell_id": spell,
            "landed_damage_observation": {"target_health_before_damage": before, "target_max_health": maximum}}


def write_run(path: Path, events, *, dropped=0, trash_mismatches=3, encounter_mismatches=0,
              encounter_killed=1, members=None):
    hostiles = [{"route_node_id": "bwd.test.trash", "target_entry": 1}] * trash_mismatches
    hostiles += [{"route_node_id": NODE, "target_entry": BOSS}] * encounter_killed
    mismatches = [{"route_node_id": "bwd.test.trash", "flagged": True}] * trash_mismatches
    mismatches += [{"route_node_id": NODE, "flagged": True}] * encounter_mismatches
    analysis = {"encounters": [{"route_node_id": NODE, "first_at_ms": 10_000, "last_at_ms": 20_000,
                                "actors": [{"actor_guid": guid} for guid in range(1, 11)]}],
                "killed_hostile_damage_reconciliation": {
                    "mismatch_count": len(mismatches), "mismatches": mismatches, "hostiles": hostiles}}
    path.mkdir(parents=True, exist_ok=True)
    (path / "combat_analysis.json").write_text(json.dumps(analysis))
    (path / "combat_log.json").write_text(json.dumps({"recent_events": events, "recent_events_dropped": dropped}))
    if members is not None:
        runtime = {"native_recovery": {"members": members}}
        (path / "report.json").write_text(json.dumps({"status": {"raid_runtime": runtime}}))
    return path


# --- item 5: encounter-scoped basis --------------------------------------------------------------------

def test_trash_mismatches_do_not_make_the_encounter_deaths_unknown(tmp_path):
    n = 4
    events = [lethal(5_000, 1, node="bwd.test.trash")]  # retained trash event before the window
    events += [lethal(11_000 + index * 100, 2 + index) for index in range(n)]
    run = write_run(tmp_path, events, dropped=5896)
    result = death_evidence(run, NODE, route_deaths=0 + 7)  # route count disagrees with the combat log
    assert result["boss_window_deaths"] == n
    assert result["death_basis"] == ENCOUNTER_RECONCILED_BASIS
    scoped = result["encounter_reconciliation"]
    assert scoped["mismatch_count"] == 3 and scoped["encounter_mismatch_count"] == 0 and scoped["reconciled"]


def test_a_boss_kill_before_the_first_party_hit_is_not_certified_from_a_truncated_ring(tmp_path):
    # Astra round-2 review: the boss kills a member at 9 s, the party first hits at 10 s (the DPS
    # window start) and the ring dropped the 9 s lethal event. The oldest retained event is on the
    # encounter node, so the death-accounting interval is not covered: unknown, not 0.
    party_hit = boss_hit(10_000, 1000, 10)
    run = write_run(tmp_path, [party_hit, lethal(12_000, 3)], dropped=5)
    result = death_evidence(run, NODE, 2)
    assert result["boss_window_deaths"] is None
    coverage = result["encounter_reconciliation"]
    assert coverage["window_retained"] is False and coverage["earliest_retained_route_node_id"] == NODE
    # The same encounter with an earlier node's event retained before the pull is covered.
    run = write_run(tmp_path / "covered", [lethal(5_000, 1, node="bwd.test.trash", source_entry=1),
                                           lethal(9_000, 2), party_hit, lethal(12_000, 3)], dropped=5)
    result = death_evidence(run, NODE, 7)
    assert result["boss_window_deaths"] == 2 and result["death_basis"] == ENCOUNTER_RECONCILED_BASIS


def test_encounter_basis_fails_closed(tmp_path):
    events = [lethal(11_000, 2)]
    # an encounter mismatch
    run = write_run(tmp_path / "a", [lethal(5_000, 1, node="bwd.test.trash"), *events], dropped=9,
                    encounter_mismatches=1)
    assert death_evidence(run, NODE, 7)["boss_window_deaths"] is None
    # dropped events reach into the window (oldest retained event is after the window start)
    run = write_run(tmp_path / "b", events, dropped=9)
    result = death_evidence(run, NODE, 7)
    assert result["boss_window_deaths"] is None and not result["encounter_reconciliation"]["window_retained"]
    # nothing was killed on the encounter node: a vacuous zero is not a reconciliation
    run = write_run(tmp_path / "c", [lethal(5_000, 1, node="bwd.test.trash"), *events], dropped=9,
                    encounter_killed=0)
    assert death_evidence(run, NODE, 7)["death_basis"] == "combat_log_lethal_damage_unreconciled"


def test_whole_run_reconciliation_is_unchanged(tmp_path):
    run = write_run(tmp_path, [lethal(5_000, 1, node="bwd.test.trash"), lethal(11_000, 2)])
    result = death_evidence(run, NODE, 2)
    assert result["death_basis"] == "combat_log_lethal_damage" and result["boss_window_deaths"] == 1
    assert "encounter_reconciliation" not in result and "native_death_signal" not in result
    assert death_evidence(run, NODE, 0) == {"boss_window_deaths": 0, "death_basis": "no_route_deaths", "deaths": []}


def test_death_signal_conflict(tmp_path):
    silent = [{"guid": guid, "death_sequence": 0, "resurrection_sequence": 0} for guid in range(1, 11)]
    run = write_run(tmp_path / "a", [lethal(11_000, 2)], members=silent)
    result = death_evidence(run, NODE, 1)
    assert result["death_signal_conflict"] is True
    assert result["native_death_signal"]["basis"] == "wipe_scoped_death_sequence"
    counted = [{"guid": guid, "death_sequence": 0, "native_death_count": int(guid == 2),
                "native_resurrection_count": int(guid == 2)} for guid in range(1, 11)]
    run = write_run(tmp_path / "b", [lethal(11_000, 2)], members=counted)
    result = death_evidence(run, NODE, 1)
    assert result["death_signal_conflict"] is False
    assert result["native_death_signal"] == {"basis": "native_life_edges", "members": 10, "deaths": 1,
                                             "resurrections": 1}


# --- item 6: Mortality exemption -------------------------------------------------------------------

def chimaeron_target():
    return load_target(ROOT, "blackwing_descent_10n_chimaeron")


def test_chimaeron_target_declares_the_mortality_exemption():
    [mortality] = death_exemptions(chimaeron_target())
    assert mortality["id"] == "mortality" and mortality["record_key"] == "mortality_deaths"
    assert mortality["spell_ids"] == [82890, 82934] and mortality["boss_entries"] == [BOSS]
    assert mortality["health_pct_at_most"] == 20 and mortality["source"] == "user decision 2026-09-27"
    assert chimaeron_target()["max_boss_window_deaths"] == 0


def test_deaths_after_mortality_do_not_count_but_deaths_before_do(tmp_path):
    target = chimaeron_target()
    events = [boss_hit(10_500, 1000, 700), lethal(12_000, 3),          # before Mortality: counts
              boss_hit(14_000, 300, 120), lethal(15_000, 4), lethal(16_000, 5)]  # 18%: Mortality
    run = write_run(tmp_path, events)
    result = death_evidence(run, NODE, 3, target)
    assert result["boss_window_deaths"] == 1 and result["mortality_deaths"] == 2
    assert result["boss_window_death_exemptions"]["mortality"] == {
        "record_key": "mortality_deaths", "deaths": 2, "started_at_ms": 14_000, "marker": "boss_health_at_most_20_pct",
        "intervals": [{"started_at_ms": 14_000, "ended_at_ms": 16_000, "marker": "boss_health_at_most_20_pct"}]}
    assert [death.get("exemption") for death in result["deaths"]] == [None, "mortality", "mortality"]


def test_mortality_spell_marker_and_no_marker(tmp_path):
    target = chimaeron_target()
    events = [boss_hit(13_000, 900, 10, spell=82890), lethal(13_500, 4)]
    assert exemption_start(events, death_exemptions(target)[0]) == {"started_at_ms": 13_000, "marker": "spell_82890"}
    run = write_run(tmp_path / "a", events)
    assert death_evidence(run, NODE, 1, target)["boss_window_deaths"] == 0
    # No marker in the log: nothing is exempt.
    run = write_run(tmp_path / "b", [boss_hit(10_500, 1000, 100), lethal(13_500, 4)])
    result = death_evidence(run, NODE, 1, target)
    assert result["boss_window_deaths"] == 1 and result["mortality_deaths"] == 0
    assert result["boss_window_death_exemptions"]["mortality"]["started_at_ms"] is None


def test_mortality_does_not_carry_into_the_next_pull(tmp_path):
    # Astra round-2 review: a wipe at 19% must not exempt a death at 90% on the next pull.
    target = chimaeron_target()
    events = [boss_hit(10_500, 250, 60), lethal(11_000, 3), lethal(11_500, 4),     # pull 1: Mortality, wipe
              # 60 s of recovery with no boss event, then pull 2 (the boss reset to full health)
              boss_hit(71_500, 1000, 100), lethal(72_000, 5),                   # 90%: counts
              boss_hit(80_000, 250, 60), lethal(81_000, 6)]                     # pull 2 Mortality: exempt
    run = write_run(tmp_path, events)
    result = death_evidence(run, NODE, 4, target)
    assert result["mortality_deaths"] == 3 and result["boss_window_deaths"] == 1
    assert [death.get("exemption") for death in result["deaths"]] == ["mortality", "mortality", None, "mortality"]
    intervals = result["boss_window_death_exemptions"]["mortality"]["intervals"]
    assert [(row["started_at_ms"], row["ended_at_ms"]) for row in intervals] == [(10_500, 11_500), (80_000, 81_000)]
    # A reset without a gap (evade to full health) also ends the attempt.
    events = [boss_hit(10_500, 250, 60), boss_hit(12_000, 1000, 50), lethal(13_000, 5)]
    result = death_evidence(write_run(tmp_path / "evade", events), NODE, 1, target)
    assert result["boss_window_deaths"] == 1 and result["mortality_deaths"] == 0
    # A respawned boss object is a new attempt too.
    events = [boss_hit(10_500, 250, 60), boss_hit(12_000, 200, 5, guid=901)]
    result = death_evidence(write_run(tmp_path / "respawn", events + [lethal(11_000, 5)]), NODE, 1, target)
    assert [row["started_at_ms"] for row in result["boss_window_death_exemptions"]["mortality"]["intervals"]] \
        == [10_500, 12_000]


def test_unreconciled_exempt_count_is_unknown(tmp_path):
    run = write_run(tmp_path, [boss_hit(10_500, 250, 60), lethal(13_500, 4)], dropped=9)
    result = death_evidence(run, NODE, 5, chimaeron_target())
    assert result["boss_window_deaths"] is None and result["mortality_deaths"] is None


def test_verdict_passes_mortality_deaths_and_reports_them():
    target = chimaeron_target()
    kill = {"kill_id": "k", "native_clear": True, "encounter": {"encounter_window_party_dps": 1.0,
                                                                  "duration_sec": 1.0},
            "boss_window_deaths": 0, "mortality_deaths": 2, "route_deaths": 2}
    reasons = _Reasons()
    verdict = _encounter_verdict(target, [kill], [kill], None, reasons)
    assert "boss_window_deaths" not in verdict["reasons"] and verdict["mortality_deaths"] == 2
    before = dict(kill, boss_window_deaths=1)
    verdict = _encounter_verdict(target, [before], [before], None, _Reasons())
    assert "boss_window_deaths" in verdict["reasons"]
    legacy = {key: value for key, value in kill.items() if key != "mortality_deaths"}
    assert _encounter_verdict(target, [legacy], [legacy], None, _Reasons())["mortality_deaths"] is None


def test_exemption_config_is_validated():
    with pytest.raises(ExemptionConfigError):
        death_exemptions({"boss_window_death_exemptions": [{"id": "x", "record_key": "boss_window_deaths",
                                                             "spell_ids": [1]}]})
    with pytest.raises(ExemptionConfigError):
        death_exemptions({"boss_window_death_exemptions": [{"id": "x", "record_key": "x_deaths"}]})
    with pytest.raises(ExemptionConfigError):
        death_exemptions({"boss_window_death_exemptions": [{"id": "x", "record_key": "x_deaths",
                                                             "health_pct_at_most": 20}]})
    assert death_exemptions({}) == []


def test_magmaw_accepted_verdict_has_no_exemption_fields():
    magmaw = load_target(ROOT, "blackwing_descent_10n_magmaw")
    assert "boss_window_death_exemptions" not in magmaw
    verdict = evaluate_target(ROOT, "blackwing_descent_10n_magmaw", "b5-d1898555")
    assert verdict["status"] == "pass" and "mortality_deaths" not in verdict["encounter"]
