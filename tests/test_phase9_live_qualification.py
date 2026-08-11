from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml.build_phase9_pairwise_matrix import build_matrix
from tools.bot_ml.build_phase9_serial_run_plan import build_plan
from tools.bot_ml.verify_phase9_pairwise_matrix import verify


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
POLICY = ROOT / "experiments/configs/stonecore_phase9_pair_policy_v1.json"
MATRIX = ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json"


TARGETED_EXCLUSIONS = [
    "arcane_mage",
    "beast_mastery_hunter",
    "destruction_warlock",
    "enhancement_shaman",
    "frost_mage",
    "protection_warrior",
    "subtlety_rogue",
]


def test_phase9_live_qualification_matches_targeted_25h_roster(tmp_path: Path) -> None:
    matrix = build_matrix(TARGETS, POLICY)
    assert matrix["canonical_target_count"] == 31
    assert matrix["target_count"] == 24
    assert matrix["qualification_excluded_targets"] == TARGETED_EXCLUSIONS
    assert matrix["uncovered_pair_count"] == 0
    assert not (set(TARGETED_EXCLUSIONS) & set(matrix["serial_target_union"]))
    assert {
        row["ordered_party"][0] for row in matrix["serial_canaries"]
    } == {"blood_death_knight", "feral_druid_tank", "protection_paladin"}
    assert matrix["serial_canary_count"] == 7
    assert all(
        {"marksmanship_hunter", "survival_hunter"}
        & set(row["ordered_party"])
        for row in matrix["serial_canaries"]
    )

    generated = tmp_path / "matrix.json"
    generated.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = verify(TARGETS, POLICY, generated)
    assert report["passed"] is True


def test_phase9_serial_plan_covers_targeted_specs_and_protection_regression() -> None:
    plan = build_plan(
        MATRIX,
        ROOT / "artifacts/all_spec_program/test_phase9_live_qualification_plan",
        ROOT / "artifacts/all_spec_program/test_phase9_live_qualification_identity.json",
        "phase9-live-qualification-test",
        "phase9-serial-canary",
    )
    assert plan["canonical_target_count"] == 31
    assert plan["qualification_excluded_targets"] == TARGETED_EXCLUSIONS
    assert plan["target_union_count"] == 24
    assert not (set(TARGETED_EXCLUSIONS) & set(plan["target_union"]))
    assert plan["attempts"][3]["ordered_party"] == [
        "protection_paladin",
        "restoration_druid",
        "elemental_shaman",
        "feral_druid_dps",
        "survival_hunter",
    ]
    assert len(plan["attempts"]) == 7
