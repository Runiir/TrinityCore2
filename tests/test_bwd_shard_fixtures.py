from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.raid_program.bwd_shard_fixtures import (
    CANONICAL_ROSTER_SLOT_IDS,
    CANONICAL_SCENARIO_ID,
    LIVE_IDENTITY_FIELDS,
    build_diagnostic_provisioning_config,
    build_shard_fixture,
    validate_readback,
    validate_shard_fixture,
)
from tools.bot_ml.build_validation_provisioning import build_account_insert_sql


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_provisioning_cata_001.json"
FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _valid_readback(fixture: dict) -> list[dict]:
    rows = []
    for shard_index, shard in enumerate(fixture["shards"], 1):
        identities = {field: shard_index * 1000 + offset for offset, field in enumerate(LIVE_IDENTITY_FIELDS, 1)}
        for bot in shard["bots"]:
            rows.append(
                {
                    "shard_id": shard["shard_id"],
                    "name": bot["name"],
                    "account_id": bot["account_id"],
                    "character_guid": bot["character_guid"],
                    "account": bot["account"],
                    "pool_tag": bot["pool_tag"],
                    "roster_slot_id": bot["roster_slot_id"],
                    "runtime_profile_id": bot["runtime_profile_id"],
                    "evidence_namespace": bot["evidence_namespace"],
                    "map_id": 669,
                    "difficulty": "normal_10man",
                    "certifies_predecessors": False,
                    "live_identities": identities,
                }
            )
    return rows


def test_tracked_fixture_is_exactly_six_disjoint_2_3_5_shards():
    fixture = _fixture()
    assert validate_shard_fixture(fixture, _config()) == {
        "all_passed": True,
        "diagnostic_bot_count": 60,
        "shard_count": 6,
    }
    assert [len(shard["bots"]) for shard in fixture["shards"]] == [10] * 6
    assert [shard["role_counts"] for shard in fixture["shards"]] == [{"tank": 2, "healer": 3, "dps": 5}] * 6
    assert len({bot["account_id"] for shard in fixture["shards"] for bot in shard["bots"]}) == 60
    assert len({bot["character_guid"] for shard in fixture["shards"] for bot in shard["bots"]}) == 60
    assert len({bot["name"] for shard in fixture["shards"] for bot in shard["bots"]}) == 60
    assert len({shard["pool_tag"] for shard in fixture["shards"]}) == 6


def test_fixture_clones_canonical_profile_inputs_and_preserves_canonical_config():
    config = _config()
    before = json.dumps(config, sort_keys=True)
    fixture = build_shard_fixture(config)
    merged = build_diagnostic_provisioning_config(config, fixture)
    assert json.dumps(config, sort_keys=True) == before
    assert len([row for row in merged["scenarios"] if row["id"] == CANONICAL_SCENARIO_ID]) == 1
    assert len([row for row in merged["scenarios"] if row.get("diagnostic_only")]) == 6
    canonical = next(row for row in config["scenarios"] if row["id"] == CANONICAL_SCENARIO_ID)
    for shard in fixture["shards"]:
        for source, clone in zip(canonical["bots"], shard["bots"], strict=True):
            for field in ("class", "class_spec", "role", "race", "level", "glyphs"):
                assert clone[field] == source[field]
            assert clone["account"] != source["account"]
            assert clone["name"] != source["name"]
            assert clone["pool_tag"] == shard["pool_tag"]
            assert clone["runtime_profile_id"] == shard["runtime_profile_id"]
            assert clone["canonical_setup"]["class_spec"] == source["class_spec"]
            assert clone["canonical_setup"]["talent_build_id"] == source["class_spec"]
            assert clone["canonical_setup"]["glyph_ids"] == source["glyphs"]


def test_merged_diagnostic_accounts_are_explicitly_allocated_but_instance_ids_are_absent():
    config = _config()
    merged = build_diagnostic_provisioning_config(config)
    account_sql = build_account_insert_sql(merged)
    assert "INSERT INTO `auth`.`account` (`id`, `username`, `salt`, `verifier`" in account_sql
    assert "VALUES (20001, 'BWDMGWA01'" in account_sql
    for scenario in merged["scenarios"]:
        requirements = scenario.get("live_identity_requirements")
        if requirements is not None:
            assert requirements["fixture_values"] is None


def test_nefarian_requires_all_predecessors_and_native_upper_ledge_descent():
    nefarian = next(row for row in _fixture()["shards"] if row["boss_key"] == "nefarian")
    assert nefarian["predecessor_state"]["precompleted_boss_entries"] == [41570, 42166, 41378, 41442, 43296]
    assert nefarian["predecessor_state"]["certifies_predecessors"] is False
    assert nefarian["predecessor_state"]["upper_ledge_start"] is True
    assert nefarian["predecessor_state"]["requires_native_descent_before_engagement"] is True
    assert nefarian["live_identity_requirements"]["fixture_values"] is None


@pytest.mark.parametrize("field", ["account_id", "character_guid", "account", "name", "roster_slot_id", "evidence_namespace"])
def test_fixture_rejects_duplicate_identity_fields(field: str):
    fixture = _fixture()
    fixture["shards"][1]["bots"][0][field] = fixture["shards"][0]["bots"][0][field]
    with pytest.raises(ValueError, match=f"duplicate_{field}"):
        validate_shard_fixture(fixture)


def test_fixture_rejects_duplicate_pool_tag_and_empty_pool():
    duplicate = _fixture()
    duplicate["shards"][1]["pool_tag"] = duplicate["shards"][0]["pool_tag"]
    with pytest.raises(ValueError, match="duplicate_pool_tag"):
        validate_shard_fixture(duplicate)

    empty = _fixture()
    empty["shards"][0]["bots"] = []
    with pytest.raises(ValueError, match="shard_bot_count"):
        validate_shard_fixture(empty)


def test_fixture_rejects_precompleted_kill_certification_or_preallocated_instance_ids():
    fixture = _fixture()
    fixture["shards"][0]["predecessor_state"]["certifies_predecessors"] = True
    with pytest.raises(ValueError, match="predecessor_contract"):
        validate_shard_fixture(fixture)
    fixture = _fixture()
    fixture["shards"][0]["live_identity_requirements"]["fixture_values"] = {"group_id": 1}
    with pytest.raises(ValueError, match="live_identity_must_be_runtime_only"):
        validate_shard_fixture(fixture)


def test_readback_requires_every_identity_and_distinct_live_setup_ids():
    fixture = _fixture()
    rows = _valid_readback(fixture)
    report = validate_readback(fixture, rows)
    assert report["all_passed"] is True
    assert report["readback_rows"] == 60
    assert report["shards"] == 6

    missing = rows[:-1]
    assert validate_readback(fixture, missing)["all_passed"] is False
    duplicate_identity = copy.deepcopy(rows)
    duplicate_identity[-1]["live_identities"] = duplicate_identity[0]["live_identities"]
    failed = validate_readback(fixture, duplicate_identity)
    assert failed["all_passed"] is False
    assert any(row["check"] == "live_identity_not_distinct" for row in failed["failures"])


def test_readback_rejects_wrong_profile_or_forbidden_predecessor_claim():
    rows = _valid_readback(_fixture())
    rows[0]["runtime_profile_id"] = "blackwing_descent_10n"
    rows[1]["certifies_predecessors"] = True
    failed = validate_readback(_fixture(), rows)
    checks = {row["check"] for row in failed["failures"]}
    assert "readback_identity" in checks
    assert "readback_predecessor_certification" in checks


def test_each_shard_has_all_canonical_roster_slots():
    fixture = _fixture()
    for shard in fixture["shards"]:
        assert {bot["canonical_roster_slot_id"] for bot in shard["bots"]} == set(CANONICAL_ROSTER_SLOT_IDS)
