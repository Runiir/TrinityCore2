"""CAP-004: identity readers consume only the declared offline asset closure."""
import copy
import hashlib
import json
import shutil
import types
import sys
from pathlib import Path

import pytest

from tools.bot_ml import build_validation_provisioning as builder
from tools.raid_program import capture_runtime_acceptance as acceptance
from tests import test_phase1_raid_foundation_capture as capture_fixture

MAIN = Path(__file__).resolve().parents[1]
PROFILES = ("blackwing_descent_10n", "blackwing_descent_10n_magmaw_diagnostic")


def test_frozen_identity_and_actual_capture_with_declared_offline_assets(tmp_path, monkeypatch):
    # The baseline is the actual native provisioning projection, not a second
    # hand-written gear oracle or a relabeled historical runtime observation.
    config_path = MAIN / "experiments/configs/validation_provisioning_cata_001.json"
    config = builder.load_config_with_bwd_diagnostic_shards(
        config_path, builder.DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE
    )
    native = builder.apply_gear_profiles(config, builder.load_gear_profiles(
        MAIN / "dataset/validation_gear_profiles/profiles.json",
        dbc_dir=MAIN / "data/dbc/enUS",
    ))
    original = acceptance._provisioned_bwd_bots
    with monkeypatch.context() as baseline_patch:
        baseline_patch.setattr(acceptance, "_provisioned_bwd_bots", lambda profile: next(
            row["bots"] for row in native["scenarios"] if row["id"] == profile
        ))
        baseline = {profile: acceptance._expected_identity_by_slot(profile) for profile in PROFILES}
    assert acceptance._provisioned_bwd_bots is original

    cold = tmp_path / "source"
    paths = [
        "experiments/configs/validation_provisioning_cata_001.json",
        "experiments/configs/all_spec_targets_cata_p4_v1.json",
        "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json",
        "experiments/configs/wowsims_cata_p4_gear_profiles.json",
        "dataset/validation_gear_profiles/profiles.json",
        "sql/old/4.3.4/TDB00_to_TDB01_updates/world/096_item_template.sql",
    ]
    manifest = json.loads((MAIN / "experiments/configs/runtime_asset_closure_manifest_v1.json").read_text())
    offline = next(row for row in manifest["asset_classes"] if row["id"] == "offline_provisioning_dbc")
    assert len(offline["expected_files"]) == 10
    for row in offline["expected_files"]:
        source = MAIN / row["path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row["sha256"]
        paths.append(row["path"])
    for relative in paths:
        target = cold / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MAIN / relative, target)
    assert (MAIN / "data/dbc/enUS/SkillLineAbility.dbc").is_file()
    assert not (cold / "data/dbc/enUS/SkillLineAbility.dbc").exists()
    assert len(list((cold / "data/dbc/enUS").iterdir())) == 10
    monkeypatch.chdir(cold)
    monkeypatch.setattr(acceptance, "ROOT", cold)
    monkeypatch.setattr(builder, "REPO_ROOT", cold)
    monkeypatch.setattr(builder, "DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE", cold / paths[2])

    # Load a fresh native socket module with the frozen source location. This
    # resets its default DBC root and caches; the warm native baseline cannot
    # accidentally make the historical materialization control pass.
    module_name = "tools.bot_ml.wowsims_gear_binding"
    isolated = types.ModuleType(module_name)
    isolated.__file__ = str(cold / "tools/bot_ml/wowsims_gear_binding.py")
    isolated.__package__ = "tools.bot_ml"
    exec(compile((MAIN / "tools/bot_ml/wowsims_gear_binding.py").read_text(),
                 isolated.__file__, "exec"), isolated.__dict__)
    with monkeypatch.context() as historical_patch:
        historical_patch.setitem(sys.modules, module_name, isolated)
        with pytest.raises(FileNotFoundError) as missing:
            builder.apply_gear_profiles(config, builder.load_gear_profiles(
                cold / "dataset/validation_gear_profiles/profiles.json"
            ))
        assert Path(missing.value.filename) == cold / "data/dbc/enUS/SkillLineAbility.dbc"

    for profile in PROFILES:
        assert len(acceptance.expected_bwd_10n_roster(profile)) == 10
        assert acceptance._expected_identity_by_slot(profile) == baseline[profile]
        assert acceptance._expected_identity_by_slot(profile) == baseline[profile]
    status = capture_fixture.accepted_status()
    assert acceptance._identity_manifest_rejections(status["raid_runtime"]) == []
    status["raid_runtime"]["roster"][0]["name"] = "WrongIdentity"
    assert acceptance._identity_manifest_rejections(status["raid_runtime"])

    # Reuse the real controller transport fixture. Its real acceptance predicate
    # repeatedly sees nonterminal native statuses; completion is never forced true.
    live_dir = tmp_path / "capture"
    live_dir.mkdir()
    capture_fixture.test_execute_capture_run_retains_native_combat_event_delta_before_terminal_full(
        live_dir, monkeypatch
    )


@pytest.mark.parametrize("mutation", ["missing_profile", "conflicting_alias", "malformed_equipment"])
def test_frozen_identity_rejects_malformed_canonical_gear(monkeypatch, mutation):
    config = builder.load_config_with_bwd_diagnostic_shards(
        MAIN / "experiments/configs/validation_provisioning_cata_001.json",
        builder.DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE,
    )
    config = copy.deepcopy(config)
    bot = next(row for row in config["scenarios"] if row["id"] == PROFILES[0])["bots"][0]
    if mutation == "missing_profile":
        bot["gear_profile_id"] = bot["gear_profile"] = "missing-profile"
        bot.setdefault("canonical_setup", {})["gear_profile_id"] = "missing-profile"
    elif mutation == "conflicting_alias":
        bot["gear_profile"] = "conflicting-profile"
    else:
        bot["equipment"] = [{"slot": True, "entry": 123}]
    monkeypatch.setattr(builder, "load_config_with_bwd_diagnostic_shards", lambda *args: config)
    with pytest.raises(ValueError, match="frozen BWD identity manifest unavailable for blackwing_descent_10n:"):
        acceptance._expected_identity_by_slot(PROFILES[0])


def test_declared_one_tank_roster_preserves_slot_identity_and_rejects_role_drift(monkeypatch):
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    expected = acceptance.expected_bwd_10n_roster(profile)
    assert expected[0] == ("raid_tank_1", "dps", 11, "balance_druid")
    assert expected[1] == ("raid_tank_2", "tank", 6, "blood_death_knight")
    assert [row[1] for row in expected].count("tank") == 1
    assert {row[0] for row in expected} == set(acceptance._expected_identity_by_slot(profile))
    bots = copy.deepcopy(acceptance._provisioned_bwd_bots(profile))
    bots[0]["role"] = "tank"
    monkeypatch.setattr(acceptance, "_provisioned_bwd_bots", lambda _: bots)
    with pytest.raises(ValueError, match="provisioning roster is invalid"):
        acceptance.expected_bwd_10n_roster(profile)


def test_actual_roster_rejections_accepts_declared_one_tank_and_rejects_old_composition():
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    expected = acceptance.expected_bwd_10n_roster(profile)
    identities = acceptance._expected_identity_by_slot(profile)
    runtime = {"roster": []}
    for index, (slot, role, class_id, spec) in enumerate(expected):
        identity = identities[slot]
        runtime["roster"].append({
            "slot": index, "roster_slot_id": slot, "lease_role_slot": slot,
            "subgroup": index // 5, "role": role, "class_id": class_id,
            "class_spec": spec, "guid": identity["character_guid"],
            "account_id": identity["account_id"], "account": identity["account"],
            "name": identity["name"], "talents": list(identity["talents"]),
            "glyphs": list(identity["glyphs"]), "active": True, "lease_owned": True,
            "gear_identity": f"fixture_{slot}", "gear_identity_manifest": {"items": [
                {**item, "guid": 500000 + index * 100 + item["slot"],
                 "gem_item_ids": list(item["gem_item_ids"])} for item in identity["gear"]
            ]},
        })
    assert acceptance._roster_rejections(runtime, profile) == []
    runtime["roster"][0]["role"] = "tank"
    rejected = acceptance._roster_rejections(runtime, profile)
    assert "exact_10n_role_composition" in rejected
    assert "exact_frozen_bwd_10n_roster_identity" in rejected
