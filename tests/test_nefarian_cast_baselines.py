"""Nefarian's End WCL cast baselines: every gated DPS spec has an eligible cast timeline.

Round 3 finding 9: after the tier-11 references replaced the old ones, Fire mage, Elemental shaman and
Assassination rogue had no eligible cast timeline, so the comparator could give them no per-spell cadence
rows. GPT-6.1 Sol's 2026-09-30 capture (four matched kills) supplies them.
"""
from __future__ import annotations

import json
import re
import tarfile
from collections import defaultdict
from pathlib import Path

import pytest

from tools.bot_ml.compare_magmaw_timelines import (
    REFERENCE_ID_KEY, _load_wcl_actors, _reference_actor_key, normalize_ability)
from tools.raid_program import scoreboard_core as scoreboard
from tools.raid_program.scoreboard_record import timeline_reference_exclusions, write_timeline

ROOT = Path(__file__).resolve().parents[1]
ENCOUNTERS = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"
TARGET_PATH = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_nefarian.json"
TIMELINES = ENCOUNTERS / "nefarian_wcl_cast_timelines_v1.json"
DPS = ENCOUNTERS / "nefarian_wcl_dps_reference_v1.json"
ARCHIVE = ROOT / "artifacts/cata_raid_program/wcl_round3_nefarian_casts_bwd10n_20260930.tar.gz"
ARCHIVE_MEMBER = "nefarian_wcl_casts_r3fix/nefarian_casts_r3fix.json"
NODE = "bwd.nefarian.encounter"

# The four matched kills of the Sol capture, in the DPS manifest's reference order, and the actors read.
SOL_REFERENCES = {
    "Z186QkDJrHATNcVW-fight48": {"Nelendil": "fire_mage", "Stealthmob": "assassination_rogue"},
    "8vxjXMR9fzgbJKBa-fight29": {"Quiim": "fire_mage", "Ungir": "elemental_shaman",
                                 "Ruggekrabber": "assassination_rogue"},
    "FBvRDV7qHdYQpmxa-fight33": {"Reggiefire": "fire_mage", "Stabcont": "assassination_rogue"},
    "p9Kb2tRF7VwBQPcn-fight18": {"Rafikee": "fire_mage", "Begemoth": "elemental_shaman"},
}
SOL_SPECS = ("fire_mage", "elemental_shaman", "assassination_rogue")
# The comparator uses the first eligible actor of a spec in file order (main reference, then additional_references).
FIRST_BASELINE = {"fire_mage": ("Nelendil", "Z186QkDJrHATNcVW-fight48"),
                  "elemental_shaman": ("Ungir", "8vxjXMR9fzgbJKBa-fight29"),
                  "assassination_rogue": ("Stealthmob", "Z186QkDJrHATNcVW-fight48")}
KEY_ABILITIES = {"fire_mage": ("Fireball", "Living Bomb", "Fire Blast"),
                 "elemental_shaman": ("Lightning Bolt", "Lava Burst", "Flame Shock"),
                 "assassination_rogue": ("Mutilate", "Mutilate Off-Hand", "Rupture")}
# A spec is confirmed by its defining abilities and by the absence of the other trees' abilities.
REQUIRED = {"fire_mage": ("Living Bomb", "Combustion", "Fireball", "Scorch", "Hot Streak"),
            "elemental_shaman": ("Lava Burst", "Lightning Bolt", "Flame Shock", "Earth Shock", "Thunderstorm",
                                 "Elemental Mastery"),
            "assassination_rogue": ("Mutilate", "Mutilate Off-Hand", "Vendetta", "Cold Blood", "Rupture",
                                    "Slice and Dice")}
FORBIDDEN = {"fire_mage": ("Frostbolt", "Arcane Blast", "Arcane Missiles", "Ice Lance", "Deep Freeze"),
             "elemental_shaman": ("Stormstrike", "Lava Lash", "Riptide", "Chain Heal", "Earth Shield"),
             "assassination_rogue": ("Sinister Strike", "Revealing Strike", "Killing Spree", "Adrenaline Rush",
                                     "Shadow Dance", "Hemorrhage", "Shadowstep")}


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _target() -> dict:
    return _load(TARGET_PATH)


def _gated_specs(target: dict) -> set[str]:
    """Specs of the roster that carry a WCL DPS target (healers and the exempt Feral tank do not)."""
    healers, exempt = scoreboard.healer_roles(target), scoreboard.dps_gate_exempt_specs(target)
    return {row["spec"] for row in scoreboard.roster(target).values()
            if row["role"] not in healers and not scoreboard.is_dps_gate_exempt(exempt, row["spec"], row["role"])}


def _eligible_baselines(target: dict) -> dict[str, list[dict]]:
    """Actors the comparator can use as a cast baseline: a matched reference, not excluded, with casts."""
    manifest, actors = _load_wcl_actors(ROOT / target["wcl_cast_timelines"])
    excluded = timeline_reference_exclusions(ROOT, target)
    matched = set(target["matched_reference_ids"])
    eligible: dict[str, list[dict]] = defaultdict(list)
    for actor in actors:
        reference_id = actor.get(REFERENCE_ID_KEY) or manifest["reference_id"]
        if reference_id in matched and _reference_actor_key(actor) not in excluded and actor.get("casts"):
            eligible[actor["class_spec"]].append(actor)
    return eligible


def _sol_actors() -> list[tuple[dict, dict]]:
    """(additional reference, actor) for every actor of the four Sol references."""
    document = _load(TIMELINES)
    return [(reference, actor) for reference in document["additional_references"]
            if reference["reference_id"] in SOL_REFERENCES for actor in reference["actors"]]


def test_every_gated_dps_spec_has_an_eligible_nefarian_cast_baseline() -> None:
    target = _target()
    gated = _gated_specs(target)
    assert {"fire_mage", "elemental_shaman", "assassination_rogue"} <= gated
    assert "feral_druid_tank" not in gated
    eligible = _eligible_baselines(target)
    assert sorted(spec for spec in gated if not eligible[spec]) == []
    names = {spec: sorted(actor["source_name"] for actor in eligible[spec]) for spec in SOL_SPECS}
    # The Néawen (385) and Roiisoleil (387) rows of cYg4 stay out: the DPS manifest excludes them.
    assert names == {"fire_mage": ["Nelendil", "Quiim", "Rafikee", "Reggiefire"],
                     "elemental_shaman": ["Begemoth", "Ungir"],
                     "assassination_rogue": ["Ruggekrabber", "Stabcont", "Stealthmob"]}
    assert "Néawen" not in {actor["source_name"] for actors in eligible.values() for actor in actors}


def test_sol_references_are_matched_kills_with_the_manifests_duration_and_values() -> None:
    document, dps = _load(TIMELINES), _load(DPS)
    manifest = {ref["id"]: ref for ref in dps["references"]}
    band = dps["item_level_band"]
    ids = [reference["reference_id"] for reference in document["additional_references"]]
    assert ids == ["cYg4C93QNdqKfPF1-fight18", *SOL_REFERENCES]
    assert set(ids) | {document["reference_id"]} <= set(manifest)
    assert _target()["matched_reference_ids"] == [ref["id"] for ref in dps["references"]]
    for reference in document["additional_references"]:
        reference_id = reference["reference_id"]
        if reference_id not in SOL_REFERENCES:
            continue
        report, fight = reference_id.split("-fight")
        expected = manifest[reference_id]
        assert expected["reference_class"] == "matched_item_level_band" and expected["in_item_level_band"] is True
        assert band["min"] <= expected["item_level"] <= band["max"]
        assert reference["url"] == f"https://classic.warcraftlogs.com/reports/{report}?fight={fight}&type=casts&view=events"
        assert reference["duration_sec"] == expected["duration_sec"]
        assert {actor["source_name"]: actor["class_spec"] for actor in reference["actors"]} == SOL_REFERENCES[reference_id]
        roster = {row["name"]: row for row in expected["roster"]}
        for actor in reference["actors"]:
            name, spec = actor["source_name"], actor["class_spec"]
            # observed_dps is the DPS manifest's own value for the same actor, and that actor is a counted one.
            assert actor["observed_dps"] == roster[name]["dps"] == expected["actor_dps"][spec], (reference_id, name)
            assert expected["actor_names"][spec] == [name]
            assert f"{spec}:{name}" not in expected["excluded_actor_dps"]
            assert 347 <= roster[name]["item_level"] <= 371
            assert actor["actor_id"] == f"{report}-source{actor['source_id']}" and actor["role"] == "dps"
            assert list(actor) == ["actor_id", "class_spec", "observed_dps", "source_id", "source_name", "role", "casts"]


def test_sol_casts_are_complete_ordered_and_inside_the_fight() -> None:
    actors = _sol_actors()
    assert len(actors) == 9
    for reference, actor in actors:
        casts, duration = actor["casts"], reference["duration_sec"]
        label = (reference["reference_id"], actor["source_name"])
        assert len(casts) >= 100, label  # a whole fight of casts, not a capped first page
        assert all(list(cast) == ["ability", "t", "target"] for cast in casts), label
        assert all(isinstance(cast["t"], float) and 0.0 <= cast["t"] <= duration for cast in casts), label
        assert [(cast["t"], cast["ability"]) for cast in casts] == sorted((cast["t"], cast["ability"]) for cast in casts)
        # Cast-time suffixes and cancel markers stay out of ability names (the comparator would rewrite them).
        assert all(normalize_ability(cast["ability"]) == cast["ability"] and cast["ability"] for cast in casts), label
        assert not any(re.search(r"\d\s*sec\b|Cancel", cast["ability"]) for cast in casts), label
        # The fight is covered to its end: the last cast falls within 3 s of the kill, the first within 6 s of the pull.
        assert duration - casts[-1]["t"] < 3.0 and casts[0]["t"] < 6.0, label
        assert "cast_time_sec" not in json.dumps(casts) and "Begin Cast" not in json.dumps(casts)


def test_sol_actors_are_the_specs_they_are_listed_as() -> None:
    for reference, actor in _sol_actors():
        names = {cast["ability"] for cast in actor["casts"]}
        spec = actor["class_spec"]
        label = (reference["reference_id"], actor["source_name"], spec)
        assert [ability for ability in REQUIRED[spec] if ability not in names] == [], label
        if spec == "fire_mage":
            assert names & {"Pyroblast", "Pyroblast!"}, label
        assert sorted(names & set(FORBIDDEN[spec])) == [], label


def test_source_note_and_coverage_note_cite_the_capture() -> None:
    document = _load(TIMELINES)
    for text in (document["source_note"], document["timeline_coverage_note"]):
        assert all(cited in text for cited in ("GPT-6.1 Sol", "2026-09-30", "13 page loads"))
        assert "nefarian_casts_r3fix.json" in text
        assert "wcl_round3_nefarian_casts_bwd10n_20260930.tar.gz" in text
    assert "have no cast timelines yet" not in document["timeline_coverage_note"]
    for reference, _ in _sol_actors():
        joined = " ".join(reference["limitations"])
        assert "GPT-6.1 Sol" in joined and "13 page loads" in joined and "2026-09-30" in joined
        assert "complete and uncapped" in joined


def _damage(guid: int, ms: int, name: str) -> dict:
    return {"kind": "damage", "route_node_id": NODE, "target_entry": 41376, "actor_guid": guid,
            "timestamp_ms": ms, "spell_id": 1, "spell_name": name, "originated_amount": 1000}


def _bot_run(tmp_path: Path, bots: list[tuple[int, str, str]], duration: float, events: list[dict]) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "report.json").write_text(json.dumps({"run_id": "nefarian-baselines", "bots": [
        {"guid": guid, "bot_name": spec, "role": role, "class_spec": spec} for guid, role, spec in bots]}))
    (run_dir / "combat_analysis.json").write_text(json.dumps({"encounters": [{
        "route_node_id": NODE, "first_at_ms": 1000, "duration_sec": duration,
        "actors": [{"actor_guid": guid, "actor_role": role, "actor_name": spec, "encounter_window_dps": 1}
                   for guid, role, spec in bots]}]}))
    (run_dir / "combat_log.json").write_text(json.dumps({"recent_events": events}))
    return run_dir


def test_comparator_gives_the_gated_specs_per_spell_cadence_rows(tmp_path: Path) -> None:
    target = _target()
    bots = [(40001, "dps", "fire_mage"), (40002, "dps", "elemental_shaman"), (40003, "dps", "assassination_rogue"),
            (40004, "tank", "blood_death_knight")]
    events = [_damage(40001, 2000, "Fireball"), _damage(40002, 2000, "Lightning Bolt"),
              _damage(40003, 2000, "Mutilate"), _damage(40004, 2000, "Heart Strike")]
    run_dir = _bot_run(tmp_path, bots, 400.0, events)  # longer than every reference: the whole fight is compared
    output = write_timeline(run_dir, ROOT / target["wcl_cast_timelines"], tmp_path / "timeline.json", NODE,
                            timeline_reference_exclusions(ROOT, target))
    assert output is not None
    result = json.loads(output.read_text())
    rows = {row["bot_guid"]: row for row in result["actors"]}
    manifest = _load(TIMELINES)
    fights = {reference["reference_id"]: reference for reference in manifest["additional_references"]}
    assert rows[40004]["comparison_status"] == "comparable"  # the main reference's Blood DK is unchanged
    for guid, spec in ((40001, "fire_mage"), (40002, "elemental_shaman"), (40003, "assassination_rogue")):
        row, (name, reference_id) = rows[guid], FIRST_BASELINE[spec]
        assert row["comparison_status"] == "comparable", spec
        assert row["reference_source_name"] == name and row["reference_fight_id"] == reference_id
        assert row["reference_common_window_sec"] == fights[reference_id]["duration_sec"]
        assert row["dps_comparison_status"] != "missing_wcl_reference"
        assert not any("No same-class/spec WCL cast timeline" in text for text in row["comparison_limitations"])
        reference_actor = next(actor for actor in fights[reference_id]["actors"] if actor["source_name"] == name)
        assert row["wcl"]["completed_casts"] == len(reference_actor["casts"])
        summary = {item["ability"]: item for item in row["wcl"]["ability_summary"]}
        for ability in KEY_ABILITIES[spec]:
            expected = [cast["t"] for cast in reference_actor["casts"] if cast["ability"] == ability]
            assert len(expected) >= 2, (spec, ability)
            cadence = summary[ability]  # the per-spell cadence row
            assert cadence["cast_count"] == len(expected)
            assert (cadence["first_t"], cadence["last_t"]) == (expected[0], expected[-1])
            assert cadence["max_gap_sec"] == round(max(b - a for a, b in zip(expected, expected[1:])), 3) > 0.0
        diffs = {item["ability"]: item for item in row["ability_diffs"]}
        bot_ability = {"fire_mage": "Fireball", "elemental_shaman": "Lightning Bolt",
                       "assassination_rogue": "Mutilate"}[spec]
        assert diffs[bot_ability]["wcl_completed_casts"] > 0 and diffs[bot_ability]["bot_landed_damage_events"] == 1


def test_sol_actors_match_the_completed_cast_rows_of_the_archived_capture() -> None:
    if not ARCHIVE.is_file():
        pytest.skip("Sol capture archive not hydrated (dvc pull)")
    with tarfile.open(ARCHIVE) as archive:
        member = archive.extractfile(ARCHIVE_MEMBER)
        assert member is not None
        capture = json.loads(member.read().decode("utf-8"))
    raw = {(f"{reference['report']}-fight{reference['fight']}", actor["source_name"]): actor
           for reference in capture["references"] for actor in reference["actors"]}
    assert capture["page_loads"] == 13 and capture["blockers"] == [] and len(raw) == 9
    for reference, actor in _sol_actors():
        source = raw[(reference["reference_id"], actor["source_name"])]
        assert source["complete"] is True and source["cap_reached"] is False
        assert source["source_id"] == actor["source_id"] and source["class_spec"] == actor["class_spec"]
        assert float(str(source["observed_dps"]).replace(",", "")) == actor["observed_dps"]
        completed = sorted(((row["t"], row["ability"], row["target"]) for row in source["casts"]
                            if row["event_type"] == "Cast"))
        assert completed == sorted((cast["t"], cast["ability"], cast["target"]) for cast in actor["casts"])
