"""The WCL cast-timeline comparison on non-Magmaw raid targets (scoreboard write_timeline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml.compare_magmaw_timelines import compare_timelines
from tools.raid_program.scoreboard_record import write_timeline


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _damage(node: str, entry: int, guid: int, ms: int, amount: int, name: str = "Strike") -> dict:
    return {"kind": "damage", "route_node_id": node, "target_entry": entry, "actor_guid": guid,
            "timestamp_ms": ms, "spell_id": 1, "spell_name": name, "originated_amount": amount}


def _run(tmp_path: Path, node: str, duration: float, bots: list[tuple[int, str, str]], events: list[dict]) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write(run_dir / "report.json", {"run_id": "encounter-timeline", "bots": [
        {"guid": guid, "bot_name": spec, "role": role, "class_spec": spec} for guid, role, spec in bots]})
    _write(run_dir / "combat_analysis.json", {"encounters": [{
        "route_node_id": node, "first_at_ms": 1000, "duration_sec": duration,
        "actors": [{"actor_guid": guid, "actor_role": role, "actor_name": spec, "encounter_window_dps": 1}
                   for guid, role, spec in bots]}]})
    _write(run_dir / "combat_log.json", {"recent_events": events})
    return run_dir


def test_atramedes_target_compares_on_its_own_node(tmp_path: Path) -> None:
    node = "bwd.atramedes.encounter"
    run_dir = _run(tmp_path, node, 10.0, [(30001, "tank", "blood_death_knight"), (30002, "dps", "fire_mage")], [
        _damage(node, 41442, 30001, 1500, 400, "Heart Strike"),
        _damage(node, 41442, 30002, 1200, 900, "Fireball"),
        _damage(node, 41807, 30002, 2200, 300, "Fireball"),  # an add of this node still counts
        _damage("bwd.magmaw.encounter", 41570, 30002, 2500, 5000),  # another node never counts
        _damage(node, 0, 30002, 2600, 7000),  # a non-creature target never counts
    ])
    manifest = tmp_path / "atramedes_wcl_cast_timelines_v1.json"
    _write(manifest, {"schema": "wcl_cast_timelines_v1", "reference_id": "MxFq7TRbvnjGY1hJ-fight32",
                      "duration_sec": 12.0, "target_scope": "Atramedes",
                      "actors": [{"actor_id": "wcl-blood", "class_spec": "blood_death_knight",
                                  "casts": [{"t": 0.5, "ability": "Heart Strike"}]}]})

    # The Magmaw-only default is exactly what silently dropped these diagnostics.
    with pytest.raises(ValueError, match="no bwd.magmaw.encounter encounter"):
        compare_timelines(run_dir, manifest)

    output = write_timeline(run_dir, manifest, tmp_path / "timeline.json", node)
    assert output is not None
    result = json.loads(output.read_text())
    assert result["scope"]["route_node_id"] == node
    assert result["reference"]["target_scope"] == "Atramedes"
    actors = {row["bot_guid"]: row for row in result["actors"]}
    assert actors[30001]["comparison_status"] == "comparable"
    assert actors[30002]["comparison_status"] == "missing_wcl_reference"
    assert actors[30002]["bot_common_window_damage"] == 1200
    assert actors[30002]["bot_common_window_dps"] == 120.0
    assert "reference_fight_id" not in actors[30001]


def test_nefarian_target_reads_additional_references_with_their_own_duration(tmp_path: Path) -> None:
    node = "bwd.nefarian.encounter"
    run_dir = _run(tmp_path, node, 15.0, [
        (30001, "tank", "blood_death_knight"), (30002, "tank", "feral_druid_tank"),
        (30003, "dps", "retribution_paladin")], [
        _damage(node, 41376, 30001, 2000, 100),
        _damage(node, 41270, 30002, 2000, 200),
        _damage(node, 41270, 30002, 8000, 300),  # t = 7.0, inside the additional fight's 8 s
        _damage(node, 41376, 30002, 13000, 400),  # t = 12.0, past it
    ])
    manifest = tmp_path / "nefarian_wcl_cast_timelines_v1.json"
    _write(manifest, {
        "schema": "wcl_cast_timelines_v1", "reference_id": "MxFq7TRbvnjGY1hJ-fight35", "duration_sec": 20.0,
        "target_scope": "Onyxia, Nefarian and Chromatic Prototypes",
        "actors": [{"actor_id": "main-blood", "class_spec": "blood_death_knight",
                    "casts": [{"t": 1.0, "ability": "Death Strike"}, {"t": 16.0, "ability": "Death Strike"}]}],
        "additional_references": [{
            "reference_id": "cYg4C93QNdqKfPF1-fight18", "duration_sec": 8.0,
            "actors": [
                {"actor_id": "extra-feral", "class_spec": "feral_druid_tank", "observed_dps": 3042.7,
                 "casts": [{"t": 1.0, "ability": "Mangle"}, {"t": 7.5, "ability": "Maul"},
                           {"t": 9.0, "ability": "Lacerate"}]},
                {"actor_id": "extra-blood", "class_spec": "blood_death_knight",
                 "casts": [{"t": 1.0, "ability": "Heart Strike"}]},
            ]}],
    })

    output = write_timeline(run_dir, manifest, tmp_path / "timeline.json", node)
    assert output is not None
    actors = {row["bot_guid"]: row for row in json.loads(output.read_text())["actors"]}

    feral = actors[30002]
    assert feral["comparison_status"] == "comparable"
    assert feral["reference_actor_id"] == "extra-feral"
    assert feral["reference_fight_id"] == "cYg4C93QNdqKfPF1-fight18"
    assert feral["reference_common_window_sec"] == 8.0
    assert feral["wcl_observed_dps_window_sec"] == 8.0
    assert feral["wcl"]["completed_casts"] == 2  # the 9.0 s cast is past its own 8 s fight
    assert feral["bot_common_window_damage"] == 500
    assert feral["bot_common_window_dps"] == 62.5

    blood = actors[30001]  # the main fight's actor stays the spec's reference
    assert blood["reference_actor_id"] == "main-blood"
    assert blood["wcl_observed_dps_window_sec"] == 20.0
    assert blood["wcl"]["completed_casts"] == 1  # min(bot 15 s, main 20 s)
    assert "reference_fight_id" not in blood

    assert actors[30003]["comparison_status"] == "missing_wcl_reference"


def test_real_non_magmaw_manifests_load_every_reference_actor() -> None:
    from tools.bot_ml.compare_magmaw_timelines import REFERENCE_DURATION_KEY, _load_wcl_actors
    root = Path(__file__).resolve().parents[1] / "experiments/configs/cata_raid_encounters/blackwing_descent"
    manifest, actors = _load_wcl_actors(root / "nefarian_wcl_cast_timelines_v1.json")
    extra = [actor for actor in actors if REFERENCE_DURATION_KEY in actor]
    assert len(actors) == len(manifest["actors"]) + len(extra)
    assert {actor[REFERENCE_DURATION_KEY] for actor in extra} == {
        reference["duration_sec"] for reference in manifest["additional_references"]}
    assert "feral_druid_tank" in {actor["class_spec"] for actor in extra}


def test_an_actor_excluded_from_dps_is_never_the_cast_baseline(tmp_path: Path) -> None:
    node = "bwd.nefarian.encounter"
    run_dir = _run(tmp_path, node, 20.0, [(30001, "dps", "survival_hunter")],
                   [_damage(node, 41376, 30001, 2000, 100)])
    manifest = tmp_path / "nefarian_wcl_cast_timelines_v1.json"
    _write(manifest, {"reference_id": "MxFq7TRbvnjGY1hJ-fight35", "duration_sec": 30.0, "actors": [
        {"actor_id": "MxFq7TRbvnjGY1hJ-source1", "class_spec": "survival_hunter", "source_name": "Jägamara",
         "casts": [{"t": 1.0, "ability": "Auto Shot"}]},
        {"actor_id": "MxFq7TRbvnjGY1hJ-source3", "class_spec": "survival_hunter", "source_name": "Lachina",
         "casts": [{"t": 1.0, "ability": "Explosive Shot"}, {"t": 2.0, "ability": "Arcane Shot"}]}]})
    excluded = frozenset({("MxFq7TRbvnjGY1hJ", "Jägamara")})
    output = write_timeline(run_dir, manifest, tmp_path / "timeline.json", node, excluded)
    result = json.loads(output.read_text())
    assert result["actors"][0]["reference_actor_id"] == "MxFq7TRbvnjGY1hJ-source3"
    assert result["scope"]["excluded_reference_actors"] == ["MxFq7TRbvnjGY1hJ/Jägamara"]


def test_real_targets_derive_cast_exclusions_from_their_dps_references() -> None:
    from tools.raid_program.scoreboard_record import timeline_reference_exclusions
    root = Path(__file__).resolve().parents[1]
    targets = root / "experiments/configs/raid_targets"
    nefarian = json.loads((targets / "blackwing_descent_10n_nefarian.json").read_text())
    assert {("MxFq7TRbvnjGY1hJ", "Jägamara"), ("MxFq7TRbvnjGY1hJ", "Wongelrainer"),
            ("farY2cm8JMTB1jGh", "Mojov")} <= timeline_reference_exclusions(root, nefarian)
    maloriak = json.loads((targets / "blackwing_descent_10n_maloriak.json").read_text())
    assert ("VL3fW9wNm2PRJDYt", "Labraizz") in timeline_reference_exclusions(root, maloriak)
    magmaw = json.loads((targets / "blackwing_descent_10n_magmaw.json").read_text())
    assert timeline_reference_exclusions(root, magmaw) == frozenset()  # Magmaw's accepted output is unchanged


def test_ranked_gaps_use_each_supplemental_actors_own_window() -> None:
    from tools.raid_program.scoreboard_record import ranked_gaps
    actors = [{"actor_id": "1", "name": "Feral", "spec": "feral_druid_tank", "role": "tank",
               "encounter_window_dps": 100.0},
              {"actor_id": "2", "name": "Blood", "spec": "blood_death_knight", "role": "tank",
               "encounter_window_dps": 100.0}]
    timeline = {"comparison_window": {"common_window_sec": 120.0}, "actors": [
        {"bot_guid": 1, "reference_common_window_sec": 60.0, "wcl": {"completed_casts": 30}},
        {"bot_guid": 2, "wcl": {"completed_casts": 30}}]}
    gaps = {gap["actor_id"]: gap for gap in ranked_gaps(
        actors, {"feral_druid_tank": 200.0, "blood_death_knight": 200.0}, timeline, set())}
    assert gaps["1"]["wcl_casts_per_minute"] == 30.0  # 30 casts over its own 60 s fight window
    assert gaps["2"]["wcl_casts_per_minute"] == 15.0  # the main reference keeps the top-level 120 s
