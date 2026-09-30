"""Magmaw 10N tier-11 WCL references (round 3) for the canonical c0 shard.

The legacy target, its WCL manifest and cast timelines stay byte-identical: the accepted
b5-d1898555 verdict pins their sha256. The canonical roster variant takes its references from the
separate T11 files below (through the roster-variant sidecar).
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"
T11_MANIFEST = FOLDER / "magmaw_wcl_dps_reference_t11_v1.json"
T11_TIMELINES = FOLDER / "magmaw_wcl_cast_timelines_t11_v1.json"
LEGACY_TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_magmaw.json"
LEGACY_VERDICT = ROOT / "artifacts/cata_raid_program/verdicts/blackwing_descent_10n_magmaw-b5-d1898555-7fcea04e9dd3.json"

T11_IDS = [
    "MxFq7TRbvnjGY1hJ-fight22", "fDP4rMTd8GCjKNqn-fight30", "yq3nVTPJC19mzgwx-fight1",
    "RtPXnbZxFkpacw1h-fight6", "fTCjtgrnzm4HRwXP-fight27", "mRGwYjb8gnQ9BaXf-fight6",
    "YcLpPHZgtzyWQGRX-fight17",
]
# Per-spec medians reported by the round-3 extraction (~/.cache/wcl_t11_refs/SUMMARY.md, Magmaw).
EXPECTED_MEDIANS = {
    "blood_death_knight": 17717.4, "balance_druid": 20436.1, "survival_hunter": 27409.7,
    "fire_mage": 23395.9, "retribution_paladin": 23552.25, "assassination_rogue": 25287.95,
    "elemental_shaman": 23683.1, "demonology_warlock": 20650.95,
}
CANONICAL_GATED = set(EXPECTED_MEDIANS)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_t11_manifest_holds_only_in_band_10n_kills_with_the_reported_medians():
    manifest = json.loads(T11_MANIFEST.read_text())
    assert manifest["schema"] == "magmaw_wcl_dps_reference_v1"
    refs = manifest["references"]
    assert [ref["id"] for ref in refs] == T11_IDS
    values: defaultdict[str, list[float]] = defaultdict(list)
    for ref in refs:
        assert ref["mode"] == "10N" and ref["kill"] is True
        assert 352.0 <= ref["item_level"] <= 366.0 and ref["in_item_level_band"] is True
        assert ref["after_hotfix_cutoff_2025_02_20"] is False
        assert ref["phase_coverage"]["mangle_happened"] and ref["phase_coverage"]["exposed_head_damaged"]
        assert not ref["deaths"]
        for spec, dps in ref["actor_dps"].items():
            values[spec].append(float(dps))
        for key in ref.get("excluded_actor_dps") or {}:
            spec, _, name = key.partition(":")
            assert name and name not in ref["actor_names"].get(spec, [])
    medians = {spec: statistics.median(dps) for spec, dps in values.items()}
    assert set(medians) >= CANONICAL_GATED
    for spec, expected in EXPECTED_MEDIANS.items():
        assert medians[spec] == pytest.approx(expected, abs=0.01)
        assert len(values[spec]) >= 3, spec


def test_t11_cast_timelines_cover_every_gated_canonical_spec_from_matched_kills():
    timelines = json.loads(T11_TIMELINES.read_text())
    assert timelines["schema"] == "magmaw_wcl_cast_timelines_v1"
    assert timelines["reference_id"] in T11_IDS
    actors = list(timelines["actors"])
    for extra in timelines.get("additional_references") or []:
        assert extra["reference_id"] in T11_IDS and extra["duration_sec"] > 0
        actors.extend(extra["actors"])
    specs = {actor["class_spec"] for actor in actors}
    assert specs >= CANONICAL_GATED
    for actor in actors:
        assert actor["casts"], actor["actor_id"]
        times = [cast["t"] for cast in actor["casts"]]
        assert times == sorted(times) and times[0] >= 0.0


def test_legacy_magmaw_target_and_references_stay_pinned_by_the_accepted_verdict():
    if not LEGACY_VERDICT.is_file():
        pytest.skip("accepted Magmaw verdict not hydrated")
    verdict = json.loads(LEGACY_VERDICT.read_text())
    target = json.loads(LEGACY_TARGET.read_text())
    assert verdict["target_sha256"] == _sha(LEGACY_TARGET)
    assert verdict["wcl_manifest_sha256"] == _sha(ROOT / target["wcl_reference_manifest"])
    assert verdict["wcl_timelines_sha256"] == _sha(ROOT / target["wcl_cast_timelines"])
    assert target["matched_reference_ids"] == ["Y8ajQ7dbmKMG1RZy-fight22"]
    assert target["wcl_reference_manifest"] != T11_MANIFEST.relative_to(ROOT).as_posix()
