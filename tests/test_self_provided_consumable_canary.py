import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUEST_CATALOG = (
    REPO_ROOT / "experiments/configs/wowsims_cata_dps_reference_requests_v1.json"
)


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    return text[start_index : text.index(end, start_index)]


def test_self_provided_requests_disable_every_external_condition() -> None:
    catalog = json.loads(REQUEST_CATALOG.read_text(encoding="utf-8"))

    assert catalog["reference_class"] == "self_provided_baseline"
    assert catalog["request_count"] == 16
    for row in catalog["requests"]:
        request = row["request"]
        native = request["native_request"]
        assert request["reference_class"] == "self_provided_baseline"
        assert native["party_buffs"] == {}
        assert native["individual_buffs"] == {}
        assert all(value is False for value in native["raid_buffs"].values())
        assert all(value is False for value in native["target_debuffs"].values())
        assert native["professions"] == [
            "ProfessionUnknown",
            "ProfessionUnknown",
        ]
        assert native["consumables"]["tinker_id"] == 0


def test_affliction_request_binds_exact_food_flask_and_two_potion_uses() -> None:
    catalog = json.loads(REQUEST_CATALOG.read_text(encoding="utf-8"))
    affliction = next(
        row for row in catalog["requests"]
        if row["target_spec"] == "affliction_warlock"
    )["request"]
    native = affliction["native_request"]
    expected = affliction["runtime_expected"]

    assert native["consumables"] == {
        "battle_elixir_id": 0,
        "conjured_id": 0,
        "explosive_id": 0,
        "flask_id": 58086,
        "food_id": 62671,
        "guardian_elixir_id": 0,
        "pot_id": 58091,
        "prepot_id": 58091,
        "tinker_id": 0,
    }
    assert expected["flask"] == {
        "item_id": 58086,
        "item_spell_id": 79470,
        "observed_aura_spell_id": 79470,
    }
    assert expected["food"] == {
        "item_id": 62671,
        "item_spell_id": 87587,
        "observed_aura_spell_id": 87547,
    }
    assert expected["prepot"] == {
        "item_id": 58091,
        "item_spell_id": 79476,
        "observed_aura_spell_id": 79476,
        "use_count": 1,
    }
    assert expected["combat_potion"] == {
        "item_id": 58091,
        "item_spell_id": 79476,
        "observed_aura_spell_id": 79476,
        "use_count": 1,
    }


def test_native_self_provided_path_uses_inventory_without_injecting_auras() -> None:
    reference = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
    )
    ensure = _between(
        reference,
        "bool BotWorldPopulationMgr::EnsureCalibrationSelfProvidedConsumables",
        "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions",
    )
    apply_conditions = _between(
        reference,
        "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions",
        "void BotWorldPopulationMgr::ObserveCalibrationReferenceConditions",
    )
    native_action = _source(
        "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"
    )
    use_item = _between(
        native_action,
        "std::is_same_v<T, BotNativeAction::UseItem>",
        "std::is_same_v<T, BotNativeAction::ReleaseSpirit>",
    )

    assert "AddAura" not in ensure
    assert "SetCount" not in ensure
    assert "DestroyItem" not in ensure
    assert "ExecuteNativeActionIntent" in ensure
    assert "PreUseItemCount > receipt.PostUseItemCount" in ensure
    assert "IsReady(spellInfo, receipt.ItemId)" in ensure
    assert "receipt.NextRetryAtMs = nowMs + 30000" in ensure
    assert apply_conditions.index("if (IsSelfProvidedCalibrationBaseline())") < (
        apply_conditions.index("AddAura")
    )
    assert "HandleUseItemOpcode" in use_item
    assert "AddAura" not in use_item
    assert "SetCount" not in use_item
    assert "DestroyItem" not in use_item


def test_prepot_runs_after_the_only_pre_score_cooldown_reset() -> None:
    reset = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReset.cpp"
    )
    reference = _source(
        "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
    )
    ensure = _between(
        reference,
        "bool BotWorldPopulationMgr::EnsureCalibrationSelfProvidedConsumables",
        "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions",
    )

    assert reset.index("bot->GetSpellHistory()->ResetAllCooldowns();") < (
        reset.index("metrics.PreScoreCooldownResetComplete = true;")
    )
    assert ensure.index("if (!metrics.PreScoreCooldownResetComplete)") < (
        ensure.index("submit(metrics.PrepotConsumable)")
    )
    assert "&& metrics.PreScoreCooldownResetComplete)\n            continue;" in reset


def test_runner_requires_an_explicit_exclusive_self_provided_mode() -> None:
    runner = _source("tools/bot_ml/run_live_bot_validation.py")

    assert "--calibration-self-provided-baseline" in runner
    assert (
        "args.calibration_reference_conditions and "
        "args.calibration_self_provided_baseline"
    ) in runner
    assert (
        '"BotWorld.CombatCalibration.SelfProvidedBaseline"'
        in runner
    )


def test_evidence_identity_builder_can_bind_the_self_provided_server() -> None:
    builder = _source(
        "tools/bot_ml/build_phase8_evidence_identity_manifest.py"
    )

    assert '"--calibration-self-provided-baseline"' in builder
    assert (
        "calibration_reference_conditions="
        "not calibration_self_provided_baseline"
    ) in builder
    assert (
        "calibration_self_provided_baseline="
        "calibration_self_provided_baseline"
    ) in builder
