from pathlib import Path

from tools.bot_ml.build_validation_provisioning import load_wdbc_values


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_native_action_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrNativeAction.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::ExecuteNativeActionIntent" in text
    assert "ExecuteNativeActionIntent" in HEADER.read_text()


def test_native_action_method_is_not_left_in_monolith():
    assert "BotWorldPopulationMgr::ExecuteNativeActionIntent" not in SOURCE.read_text()


def test_native_action_keeps_typed_resurrection_and_session_boundaries():
    text = MODULE.read_text()
    for marker in (
        "resolveCombatResTarget",
        "declineCombatResIntent",
        "BotNativeAction::CombatResApproach",
        "BotNativeAction::CombatResCast",
        "BotNativeAction::CombatResAccept",
        "CancelRemovableShapeshifts",
        "HandleResurrectResponseOpcode",
        "HandleUseItemOpcode",
        "HandlePetActionHelper",
        "native_area_trigger_submitted",
        "native_gossip_select_submitted",
    ):
        assert marker in text


def test_vehicle_action_uses_the_controlled_vehicle_and_live_declared_target():
    text = MODULE.read_text()
    start = text.index(
        "else if constexpr (std::is_same_v<T, BotNativeAction::VehicleAction>)"
    )
    end = text.index(
        "else if constexpr (std::is_same_v<T, BotNativeAction::PetCommand>)",
        start,
    )
    action = text[start:end]

    assert "bot->GetVehicleBase()" in action
    assert "vehicle->IsInWorld()" in action
    assert "vehicle->IsAlive()" in action
    assert "vehicle->IsVehicle()" in action
    assert "client->IsAllowedToMove(vehicle)" in action
    assert "action.Target.IsEmpty()" in action
    assert "target->IsInWorld()" in action
    assert "target->IsAlive()" in action
    assert "vehicleCreature->HasSpell(action.SpellId)" in action
    assert "vehicle->CastSpell(target, action.SpellId, false)" in action
    assert "bot->CastSpell(target, action.SpellId, false)" not in action
    assert "native_vehicle_action_rejected_result_" in action
    assert "SPELL_FAILED_NOT_READY" in action
    assert "GetRemainingCooldown(spellInfo)" in action
    assert "GetRemainingGlobalCooldown(spellInfo)" in action
    assert '"_cooldown_ms_"' in action
    assert '"_gcd_ms_"' in action

    assert action.index("bot->GetVehicleBase()") < action.index(
        "vehicle->CastSpell(target, action.SpellId, false)"
    )
    assert action.index("action.Target.IsEmpty()") < action.index(
        "ObjectAccessor::GetUnit(*bot, action.Target)"
    )


def test_magmaw_hook_vehicle_spells_use_cooldown_without_a_global_cooldown():
    dbc = ROOT / "data/dbc/enUS"
    spell_rows = {
        int(row[0]): row
        for row in load_wdbc_values(
            dbc / "Spell.dbc",
            "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii",
        )
    }
    cooldown_rows = {
        int(row[0]): row
        for row in load_wdbc_values(dbc / "SpellCooldowns.dbc", "diii")
    }

    for spell_id in (77917, 77941):
        spell = spell_rows[spell_id]
        cooldown = cooldown_rows[int(spell[37])]
        assert cooldown[1:] == [0, 6000, 0]
