"""Round-1 validation neutrality: the accepted Magmaw 10N roster and every
legacy generated artifact stay byte-identical while the raid-shard plan,
loadouts and readbacks are added beside them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.bot_ml.build_validation_provisioning import (
    account_commands,
    apply_gear_profiles,
    build_account_insert_sql,
    build_character_insert_sql,
    gem_item_enchant_map,
    load_config,
    load_config_with_bwd_diagnostic_shards,
    load_gear_profiles,
    scenario_report,
)
from tools.bot_ml.build_validation_scenario_manifests import build_manifests, diagnostic_rosters_by_scenario, load_json
from tools.bot_ml.common import stable_hash
from tools.bot_ml.validate_validation_provisioning import validate_payloads
from tools.raid_program.bwd_shard_fixtures import build_shard_fixture, validate_shard_fixture

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_provisioning_cata_001.json"
FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
GEAR = ROOT / "dataset/validation_gear_profiles/profiles.json"
DBC = ROOT / "data/dbc/enUS"
PROVISIONING_OUT = ROOT / "dataset/validation_provisioning"
SCENARIOS_OUT = ROOT / "dataset/validation_scenarios"
MAGMAW = "blackwing_descent_10n_magmaw_diagnostic"
# Captured before any round-1 change from the committed generators and DVC gear profiles.
MAGMAW_CHARACTER_SQL_SHA256 = "e121498aa4a1e2d43a72aa422f6a2bc3113d430c34771485fcf197faab602d7c"
MAGMAW_ACCOUNT_SQL_SHA256 = "689fc5fd368cc4dc8e19c689471e579c80d1af762747fcc7b6f510fd66d114e7"


def _lock_inputs_current(stage: str, skip: set[str]) -> bool:
    """True when every non-code input of a DVC stage still matches dvc.lock (the outputs are comparable)."""
    lock = yaml.safe_load((ROOT / "dvc.lock").read_text(encoding="utf-8"))
    for dep in lock["stages"][stage]["deps"]:
        path = ROOT / dep["path"]
        if dep["path"] in skip or dep["path"].startswith(("tools/", "dataset/")) or not path.is_file():
            continue
        if hashlib.md5(path.read_bytes()).hexdigest() != dep["md5"]:
            return False
    return True


def _legacy_config() -> dict[str, Any]:
    return apply_gear_profiles(load_config_with_bwd_diagnostic_shards(CONFIG, FIXTURE), load_gear_profiles(GEAR))


needs_gear = pytest.mark.skipif(not GEAR.is_file() or not (DBC / "Item-sparse.db2").is_file(),
                                reason="DVC gear profiles or client DBCs not hydrated")


def test_legacy_shard_fixture_is_regenerated_byte_identically():
    fixture = build_shard_fixture(json.loads(CONFIG.read_text(encoding="utf-8")))
    assert json.dumps(fixture, indent=2, sort_keys=True) + "\n" == FIXTURE.read_text(encoding="utf-8")
    assert validate_shard_fixture(fixture) == {"all_passed": True, "diagnostic_bot_count": 60, "shard_count": 6}
    magmaw = fixture["shards"][0]
    assert [bot["character_guid"] for bot in magmaw["bots"]] == list(range(30001, 30011))
    assert [bot["account_id"] for bot in magmaw["bots"]] == list(range(20001, 20011))


def test_default_provisioning_config_contains_no_raid_shard_characters():
    merged = load_config_with_bwd_diagnostic_shards(CONFIG, FIXTURE)
    bots = [bot for scenario in merged["scenarios"] for bot in scenario["bots"]]
    assert len(bots) == 110
    assert not any(bot.get("loadout") for bot in bots)
    assert not any(str(scenario["id"]).endswith("_c0_diagnostic") for scenario in merged["scenarios"])


@needs_gear
def test_magmaw_scoped_provisioning_sql_is_unchanged():
    config = _legacy_config()
    sql = build_character_insert_sql(config, None, gem_item_enchant_map(DBC), DBC, scenario_ids=[MAGMAW])
    assert hashlib.sha256(sql.encode()).hexdigest() == MAGMAW_CHARACTER_SQL_SHA256
    selected = {**config, "scenarios": [row for row in config["scenarios"] if row["id"] == MAGMAW]}
    assert hashlib.sha256(build_account_insert_sql(selected).encode()).hexdigest() == MAGMAW_ACCOUNT_SQL_SHA256
    assert "talentGroupsCount`, `activeTalentGroup`" in sql and ", 1, 0, '" in sql
    for guid in range(30001, 30011):
        assert f"SELECT {guid}, a.`id`" in sql


@needs_gear
@pytest.mark.skipif(not (PROVISIONING_OUT / "provision_characters.sql").is_file(), reason="DVC output absent")
def test_full_legacy_provisioning_outputs_match_the_locked_dvc_outputs():
    if not _lock_inputs_current("validation_provisioning", {"experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"}):
        pytest.skip("validation_provisioning inputs changed since the last DVC reproduction")
    config = _legacy_config()
    gems = gem_item_enchant_map(DBC)
    expected = {
        "account_commands.txt": account_commands(config),
        "provision_accounts.sql": build_account_insert_sql(config),
        "provision_characters.sql": build_character_insert_sql(config, None, gems, DBC),
        "report.json": json.dumps(scenario_report(config), indent=2, sort_keys=True, default=str) + "\n",
    }
    for name, text in expected.items():
        assert (PROVISIONING_OUT / name).read_text(encoding="utf-8") == text, name
    manifest = json.loads((PROVISIONING_OUT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_hash"] == stable_hash(config)


@needs_gear
@pytest.mark.skipif(not (ROOT / "dataset/validation_provisioning_verification/report.json").is_file(), reason="DVC output absent")
def test_legacy_payload_verification_is_unchanged():
    if not _lock_inputs_current("validation_provisioning_verify", {"experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"}):
        pytest.skip("validation_provisioning_verify inputs changed since the last DVC reproduction")
    config = _legacy_config()
    failures, evidence = validate_payloads(config, DBC, None)
    locked = json.loads((ROOT / "dataset/validation_provisioning_verification/report.json").read_text(encoding="utf-8"))
    assert failures == []
    # gem_catalog_count needs the hotfix database; every offline field is identical.
    assert {k: v for k, v in evidence.items() if k != "gem_catalog_count"} == {
        k: v for k, v in locked["payload_evidence"].items() if k != "gem_catalog_count"}


def _old_diagnostic_rosters(fixture: dict) -> dict:
    """The pre-round-1 implementation (six shards of ten), kept as a reference."""
    rosters = {}
    for shard in fixture.get("shards", []):
        rosters[str(shard["scenario_id"])] = [
            {"roster_slot_id": str(bot.get("canonical_roster_slot_id") or ""), "guid": int(bot.get("character_guid") or 0),
             "name": str(bot.get("name") or ""), "role": str(bot.get("role") or ""),
             "class_spec": str(bot.get("class_spec") or "")} for bot in shard["bots"]]
    assert len(rosters) == 6 and all(len(rows) == 10 for rows in rosters.values())
    return rosters


def test_generalized_diagnostic_rosters_match_the_legacy_reader():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert diagnostic_rosters_by_scenario(fixture) == _old_diagnostic_rosters(fixture)
    assert diagnostic_rosters_by_scenario(None) == {}
    broken = dict(fixture, shard_count=5)
    with pytest.raises(ValueError, match="diagnostic_shard_roster_count"):
        diagnostic_rosters_by_scenario(broken)
    short = json.loads(FIXTURE.read_text(encoding="utf-8"))
    short["shards"][0]["bots"].pop()
    with pytest.raises(ValueError, match="diagnostic_shard_roster_shape"):
        diagnostic_rosters_by_scenario(short)
    with pytest.raises(ValueError, match="diagnostic_shard_fixture_schema"):
        diagnostic_rosters_by_scenario({"schema": "other", "shards": []})


def test_raid_shard_plan_rosters_bind_beside_the_legacy_fixture():
    from tests.test_raid_shard_plan import _plan
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    plan = _plan()
    rosters = diagnostic_rosters_by_scenario(fixture, [plan])
    assert len(rosters) == 12
    chimaeron = rosters["blackwing_descent_10n_chimaeron_c0_diagnostic"]
    assert [row["role"] for row in chimaeron].count("tank") == 2
    assert {row["roster_slot_id"] for row in chimaeron} >= {"druid", "shaman", "death_knight"}
    with pytest.raises(ValueError, match="diagnostic_shard_roster_duplicate_scenario"):
        diagnostic_rosters_by_scenario(fixture, [plan, plan])


@pytest.mark.skipif(not (SCENARIOS_OUT / "validation_routes.jsonl").is_file(), reason="DVC output absent")
def test_validation_scenario_manifests_are_unchanged():
    if not _lock_inputs_current("validation_scenarios", set()):
        pytest.skip("validation_scenarios inputs changed since the last DVC reproduction (package D edits)")
    manifests = build_manifests(
        load_json(ROOT / "experiments/configs/validation_scenarios_cata_001.json"),
        load_json(PROVISIONING_OUT / "report.json"),
        load_json(ROOT / "dataset/validation_provisioning_verification/report.json"),
        load_json(FIXTURE))
    for name in ("validation_scenarios", "validation_routes", "validation_mechanics"):
        text = "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in manifests[name])
        assert (SCENARIOS_OUT / f"{name}.jsonl").read_text(encoding="utf-8") == text, name


def test_scenario_catalog_keeps_the_legacy_bwd_10n_rosters():
    from tools.raid_program.scenario_catalog import discover, resolve
    encounter = resolve(ROOT, "implement magmaw 10n bots")
    found = discover(ROOT, encounter)
    assert [actor["actor_id"] for actor in found["roster"]["actors"]] == [str(guid) for guid in range(30001, 30011)]
    assert found["roster"]["status"] == "declared_diagnostic_roster_requires_current_readback"
    assert not any("raid_compositions" in key for key in found["sources"])


def test_scenario_catalog_binds_a_declared_composition_for_encounters_without_legacy_shards(tmp_path):
    import shutil
    from tools.raid_program.scenario_catalog import composition_roster
    target = tmp_path / "experiments/configs"
    (target / "raid_compositions").mkdir(parents=True)
    composition = json.loads((ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json").read_text())
    composition["mode"] = "10H"
    (target / "raid_compositions/bwd_10h.json").write_text(json.dumps(composition))
    shutil.copy(ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json", target)
    roster = composition_roster(tmp_path, "blackwing_descent", "10H", "omnotron_defense_system")
    assert roster["scenario_id"] == "blackwing_descent_10h_omnotron_c0_diagnostic"
    assert [actor["actor_id"] for actor in roster["actors"]][:2] == ["11101001", "11101002"]
    assert next(actor for actor in roster["actors"] if actor["slot"] == "druid")["class_spec"] == "feral_druid_tank"
    assert composition_roster(tmp_path, "blackwing_descent", "25N", "magmaw") is None
    assert load_config(CONFIG)["scenarios"]  # the legacy config is untouched by the composition
