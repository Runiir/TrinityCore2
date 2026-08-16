from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest

from tools.bot_ml.build_wowsims_reference_requests import (
    DEFAULT_OUTPUT_PATH,
    REQUIRED_REQUIREMENTS,
    RESULT_ACCEPTED,
    RESULT_PENDING,
    TALENT_DBC_SNAPSHOT_DIR,
    ReferenceRequestError,
    _read_hashed_json,
    build_manifest,
    canonical_sha256,
    parse_upstream_suite,
    pending_catalog_projection,
    request_by_spec,
    request_condition_projection,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built_manifest() -> dict:
    return build_manifest(root=ROOT)


def _row(manifest: dict, target_spec: str = "frost_death_knight") -> dict:
    return next(row for row in manifest["requests"] if row["target_spec"] == target_spec)


def test_builds_exactly_16_unique_pending_requests(built_manifest: dict) -> None:
    rows = built_manifest["requests"]
    assert built_manifest["request_count"] == len(rows) == 16
    assert len({row["target_spec"] for row in rows}) == 16
    assert {row["result"]["status"] for row in rows} == {RESULT_PENDING}
    assert all(row["result"]["dps"] is None for row in rows)
    assert all(row["comparison_manifest"]["reference_dps"] is None for row in rows)


def test_requests_pin_live_fixture_and_not_legacy_denominators(
    built_manifest: dict,
) -> None:
    fixture_sha = built_manifest["fixture_contract_sha256"]
    assert built_manifest["fixture_contract_path"].endswith(
        "phase8_calibration_fixture_contract_v1.materialized.json"
    )
    for row in built_manifest["requests"]:
        request = row["request"]
        assert request["fixture_contract_sha256"] == fixture_sha
        assert request["sim_options"] == {
            "iterations": 2000,
            "random_seed": 101,
            "debug": False,
            "is_test": True,
        }
        assert request["encounter"]["duration_seconds"] == 300
        assert request["encounter"]["duration_variation_seconds"] == 0
        assert request["fixture_target"]["level"] == 88
        assert request["fixture_target"]["armor"] == 11977
        assert request["fixture_target"]["creature_type_name"] == "mechanical"
        assert request["item_swap"] == {"enabled": False, "items": []}
        assert row["source_contract"]["upstream_results"]["usage"].startswith(
            "provenance_only"
        )


def test_every_request_and_projection_is_content_addressed(
    built_manifest: dict,
) -> None:
    for row in built_manifest["requests"]:
        assert row["source_contract_sha256"] == canonical_sha256(
            row["source_contract"]
        )


def test_talent_strings_roundtrip_to_exact_target_spell_ids(
    built_manifest: dict,
) -> None:
    for row in built_manifest["requests"]:
        talents = row["request"]["player"]["talents"]
        assert sum(value["rank"] for value in talents["decoded_talents"]) == 41
        assert talents["active_spell_ids"] == sorted(
            value["spell_id"] for value in talents["decoded_talents"]
        )
        authority = talents["translation_authority"]
        assert authority["schema"] == "trinity_cata_talent_string_dbc_roundtrip_v1"
        assert set(authority["source_file_sha256"]) == {
            "Talent.dbc",
            "TalentTab.dbc",
            "TalentTreePrimarySpells.dbc",
        }
        assert row["request_sha256"] == canonical_sha256(row["request"])
        comparison = row["comparison_manifest"]
        assert comparison["source_setup_sha256"] == canonical_sha256(
            comparison["source_setup"]
        )
        projection = request_condition_projection(row["request"])
        assert comparison["source_setup"] == projection["source_setup"]
        assert (
            comparison["request_condition_projection_sha256"]
            == projection["projection_sha256"]
        )


def test_talent_translation_uses_checked_in_snapshot_bytes() -> None:
    assert TALENT_DBC_SNAPSHOT_DIR.relative_to(ROOT).as_posix() == (
        "experiments/configs/wowsims_cata_p4_talent_sources"
    )
    assert {path.name for path in TALENT_DBC_SNAPSHOT_DIR.iterdir()} == {
        "Talent.dbc",
        "TalentTab.dbc",
        "TalentTreePrimarySpells.dbc",
    }


def test_generated_result_validation_joins_nested_artifacts_by_resolved_path() -> None:
    source = inspect.getsource(
        __import__(
            "tools.bot_ml.build_wowsims_reference_requests",
            fromlist=["_validate_generated_result"],
        )._validate_generated_result
    )
    assert "receipt_path.resolve() == promoted_path.resolve()" in source
    assert 'nested_artifact_matches("native_result")' in source


def test_requirements_cover_exact_static_and_runtime_facts(
    built_manifest: dict,
) -> None:
    for row in built_manifest["requests"]:
        requirements = row["comparison_manifest"]["requirements"]
        by_id = {requirement["id"]: requirement for requirement in requirements}
        assert set(by_id) == set(REQUIRED_REQUIREMENTS)
        assert by_id["gear_manifest"]["planned_path"].startswith("reference.")
        assert by_id["race"]["planned_path"] == "target.provisioning_bot.race"
        assert by_id["glyphs"]["planned_equals"] == row["request"]["player"][
            "glyphs"
        ]["item_ids"]
        assert by_id["glyphs"]["equals"] == row["request"]["player"]["glyphs"][
            "runtime_identity"
        ]
        assert (
            by_id["prepull_setup"]["planned_path"]
            == "fixture.runtime_expected.prepull_setup"
        )
        assert by_id["prepull_setup"]["path"] == "runtime.prepull_setup_projection"
        assert "external_windows" not in by_id
        assert "simulator_options" not in by_id
        classification = row["request"]["player"][
            "simulator_option_leaf_classification"
        ]
        assert classification["unclassified"] == []
        assert set(classification["atomic_runtime_requirements"].values()) <= set(
            REQUIRED_REQUIREMENTS
        )
        assert (
            by_id["heroism"]["equals"]
            == row["request"]["runtime_expected"]["heroism"]
        )
        assert (
            by_id["prepull_setup"]["equals"]["external_windows"]
            == row["request"]["runtime_expected"]["prepull_setup"][
                "external_windows"
            ]
        )
        assert all(
            "planned_equals" in requirement and "equals" in requirement
            for requirement in requirements
        )


def test_upstream_selector_is_parsed_from_checked_source() -> None:
    source = (
        ROOT
        / "experiments/configs/wowsims_cata_p4_gear_sources/marksmanship_hunter.test.go"
    ).read_text(encoding="utf-8")
    parsed = parse_upstream_suite(source)
    assert parsed["suite_name"] == "TestMM"
    assert parsed["legacy_tokens"]["gear_label"] == "preraid_mm"
    assert parsed["legacy_tokens"]["rotation_label"] == "mm"
    assert len(parsed["character_suite_config_sha256"]) == 64


def test_request_by_spec_rejects_unknown_and_returns_unique(
    built_manifest: dict,
) -> None:
    assert request_by_spec(built_manifest, "fire_mage")["target_spec"] == "fire_mage"
    with pytest.raises(ReferenceRequestError, match="request_not_unique"):
        request_by_spec(built_manifest, "not_a_spec")


def test_duplicate_target_is_rejected(built_manifest: dict) -> None:
    spoofed = copy.deepcopy(built_manifest)
    spoofed["requests"][-1]["target_spec"] = spoofed["requests"][0]["target_spec"]
    with pytest.raises(ReferenceRequestError, match="request_duplicate"):
        validate_manifest(spoofed, root=ROOT, verify_generated_artifacts=False)


def test_comparison_cannot_launder_different_request_conditions(
    built_manifest: dict,
) -> None:
    spoofed = copy.deepcopy(built_manifest)
    row = _row(spoofed)
    row["comparison_manifest"]["source_setup"]["race"] = 99
    row["comparison_manifest"]["source_setup_sha256"] = canonical_sha256(
        row["comparison_manifest"]["source_setup"]
    )
    with pytest.raises(ReferenceRequestError, match="request_comparison_projection"):
        validate_manifest(spoofed, root=ROOT, verify_generated_artifacts=False)


def test_requirement_cannot_launder_different_runtime_value(
    built_manifest: dict,
) -> None:
    spoofed = copy.deepcopy(built_manifest)
    row = _row(spoofed)
    requirement = next(
        value
        for value in row["comparison_manifest"]["requirements"]
        if value["id"] == "duration"
    )
    requirement["equals"] = 299
    with pytest.raises(ReferenceRequestError, match="requirement_not_projected"):
        validate_manifest(spoofed, root=ROOT, verify_generated_artifacts=False)


def test_talent_string_cannot_be_relabelled_with_old_decoded_spells(
    built_manifest: dict,
) -> None:
    spoofed = copy.deepcopy(built_manifest)
    row = _row(spoofed)
    row["request"]["player"]["talents"]["talent_string"] = "0-0-0"
    row["request_sha256"] = canonical_sha256(row["request"])
    row["comparison_manifest"]["request_sha256"] = row["request_sha256"]
    row["result"]["artifacts"]["request_contract_sha256"] = row["request_sha256"]
    with pytest.raises(ReferenceRequestError, match="talent_point_count"):
        validate_manifest(spoofed, root=ROOT, verify_generated_artifacts=False)


def test_fake_generated_result_with_hex_placeholders_is_rejected(
    built_manifest: dict,
) -> None:
    spoofed = copy.deepcopy(built_manifest)
    row = _row(spoofed)
    row["result"]["status"] = RESULT_ACCEPTED
    row["result"]["result_key"] = "fake"
    row["result"]["dps"] = 999999.0
    row["result"]["authority_scope"] = "offline_denominator_only"
    row["result"]["live_fixture_join_status"] = "pending_physical_raw_capture"
    row["comparison_manifest"]["result_status"] = RESULT_ACCEPTED
    row["comparison_manifest"]["reference_result_key"] = "fake"
    row["comparison_manifest"]["reference_dps"] = 999999.0
    for artifact in row["result"]["artifacts"].values():
        if isinstance(artifact, dict):
            artifact["path"] = "does/not/exist.json"
            artifact["sha256"] = "a" * 64
            if "byte_count" in artifact:
                artifact["byte_count"] = 1
    with pytest.raises(ReferenceRequestError, match="generation_receipt_missing"):
        validate_manifest(spoofed, root=ROOT)


def test_hashed_artifact_rejects_symlink_even_when_bytes_match(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real.json"
    real.write_text('{"ok":true}\n', encoding="utf-8")
    linked = tmp_path / "linked.json"
    linked.symlink_to(real)
    with pytest.raises(ReferenceRequestError, match="symlink_forbidden"):
        _read_hashed_json(
            tmp_path,
            {
                "path": linked.name,
                "sha256": canonical_sha256({"not": "the file hash"}),
                "byte_count": real.stat().st_size,
            },
            "artifact",
        )


def test_partial_generated_cohort_is_rejected(built_manifest: dict) -> None:
    spoofed = copy.deepcopy(built_manifest)
    row = _row(spoofed)
    row["result"]["status"] = RESULT_ACCEPTED
    row["result"]["result_key"] = "generated:partial"
    row["result"]["dps"] = 1.0
    row["result"]["authority_scope"] = "offline_denominator_only"
    row["result"]["live_fixture_join_status"] = "pending_physical_raw_capture"
    row["comparison_manifest"]["result_status"] = RESULT_ACCEPTED
    row["comparison_manifest"]["reference_result_key"] = "generated:partial"
    row["comparison_manifest"]["reference_dps"] = 1.0
    with pytest.raises(
        ReferenceRequestError,
        match="mixed_pending_and_generated_reference_cohort_forbidden",
    ):
        validate_manifest(spoofed, root=ROOT, verify_generated_artifacts=False)


def test_generated_result_cannot_claim_live_fixture_authority(
    built_manifest: dict,
) -> None:
    spoofed = copy.deepcopy(built_manifest)
    row = _row(spoofed)
    row["result"].update(
        {
            "status": RESULT_ACCEPTED,
            "result_key": "generated:scope-spoof",
            "dps": 1.0,
            "authority_scope": "live_fixture_certified",
            "live_fixture_join_status": "passed_without_raw_capture",
        }
    )
    row["comparison_manifest"].update(
        {
            "result_status": RESULT_ACCEPTED,
            "reference_result_key": "generated:scope-spoof",
            "reference_dps": 1.0,
        }
    )
    with pytest.raises(ReferenceRequestError, match="generated_result_scope"):
        validate_manifest(spoofed, root=ROOT, verify_generated_artifacts=False)


def test_pending_catalog_projection_removes_generated_numeric_authority(
    built_manifest: dict,
) -> None:
    promoted = copy.deepcopy(built_manifest)
    for row in promoted["requests"]:
        row["result"].update(
            {
                "status": RESULT_ACCEPTED,
                "result_key": f"generated:{row['target_spec']}",
                "dps": 1.0,
                "authority_scope": "offline_denominator_only",
                "live_fixture_join_status": "pending_physical_raw_capture",
                "publication_domain": {"untrusted": "must be removed"},
            }
        )
        row["comparison_manifest"].update(
            {
                "result_status": RESULT_ACCEPTED,
                "reference_result_key": f"generated:{row['target_spec']}",
                "reference_dps": 1.0,
            }
        )
    assert pending_catalog_projection(promoted) == built_manifest


def test_checked_manifest_is_current(built_manifest: dict) -> None:
    checked = json.loads(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))
    assert checked == built_manifest
