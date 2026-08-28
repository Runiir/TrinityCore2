import json
from pathlib import Path

from tools.bot_ml.build_validation_provisioning import build_character_insert_sql


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationPatrolPull.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
PROVISIONING = ROOT / "experiments/configs/validation_provisioning_cata_001.json"


def test_validation_patrol_pull_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationPatrolPull.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::TryValidationRoutePatrolPull" in text
    assert "TryValidationRoutePatrolPull" in HEADER.read_text()


def test_validation_patrol_pull_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "TryValidationRoutePatrolPull(state, bot, power, stage, activity" in text
    assert "sourcePathKeepsFutureEncountersSafe" not in text


def test_validation_patrol_pull_keeps_native_pull_contract():
    text = MODULE.read_text()
    for marker in (
        "ranged_patrol_to_anchor",
        "patrol_pull_contract_unresolved",
        "sourcePathKeepsFutureEncountersSafe",
        "ValidationRoutePatrolPullOwnerRosterSlot",
        "ordinary_ranged_pull_submitted",
        "validation_route_patrol_wait_for_tank_threat",
        "SetAllOffenseSuppressed",
    ):
        assert marker in text


def test_hunter_patrol_pull_resolves_a_live_same_group_tank():
    text = MODULE.read_text()
    tank_selection = text.index("Player* tank = nullptr;")
    tank_selection_end = text.index("if (!tank)", tank_selection)
    selector = text[tank_selection:tank_selection_end]

    for marker in (
        "member->IsInWorld()",
        "member->IsAlive()",
        "bot->GetGroup()",
    ):
        assert marker in selector
    assert "member != bot" in selector or "member == bot" in selector
    assert (
        "member->GetGroup() == bot->GetGroup()" in selector
        or "member->GetGroup() != bot->GetGroup()" in selector
    )
    assert (
        "member->GetMap() == bot->GetMap()" in selector
        or "member->GetMap() != bot->GetMap()" in selector
    )
    assert (
        'memberRoster->second.Role == "tank"' in selector
        or 'memberRoster->second.Role != "tank"' in selector
    )


def test_missing_selected_tank_roster_fails_closed_without_map_at():
    text = MODULE.read_text()
    tank_selection = text.index("Player* tank = nullptr;")
    hunter_preparation = text.index("if (hunterPullOwner", tank_selection)
    selector = text[tank_selection:hunter_preparation]

    assert ".at(" not in selector
    assert "tankRosterSlotIndex = memberRoster->second.SlotIndex" in selector
    assert "selectedTankRoster = Cohort().Raid.RosterByGuid.find(" in selector
    missing = selector.index("selectedTankRoster == Cohort().Raid.RosterByGuid.end()")
    assert selector.index("patrol_pull_selected_tank_roster_missing", missing) > missing
    missing_absolute = tank_selection + missing
    assert text.index("return hold(", missing_absolute) < hunter_preparation


def test_missing_source_victim_roster_fails_closed_without_map_at():
    text = MODULE.read_text()
    victim = text.index("Player* sourceVictim = source->GetVictim()")
    bot_roster = text.index("auto const botRoster", victim)
    engaged_handoff = text[victim:bot_roster]

    assert ".at(" not in engaged_handoff
    assert "sourceVictimRoster = sourceVictim" in engaged_handoff
    missing = engaged_handoff.index(
        "sourceVictimRoster == Cohort().Raid.RosterByGuid.end()")
    assert engaged_handoff.index("patrol_pull_source_victim_roster_missing", missing) > missing
    assert engaged_handoff.index("return hold(", missing) < len(engaged_handoff)


def test_patrol_valid_roster_uses_captured_slots_and_roles():
    text = MODULE.read_text()

    assert ".at(" not in text
    assert "memberRoster->second.SlotIndex >= tankRosterSlotIndex" in text
    assert "sourceVictimRoster->second.Role == \"tank\"" in text
    assert "validation_route_patrol_wait_for_tank_threat" in text
    assert "validation_route_patrol_misdirection" in text


def test_hunter_patrol_observes_growl_off_before_misdirection_and_pull():
    text = MODULE.read_text()
    hunter_preparation = text.index("if (hunterPullOwner)")
    growl_observation = text.index("bool growlAutocastOff", hunter_preparation)
    growl_gate = text.index("if (!growlAutocastOff)", growl_observation)
    engagement_observation = text.index(
        "bool const sourceEngaged = isValidationCohortCombatLinked(source);",
        hunter_preparation,
    )
    misdirection = text.index(
        "TryCastFriendlySpell(bot, tank,", engagement_observation)
    ranged_pull = text.index("ResolveProfileCombatAction(", misdirection)

    assert growl_observation < growl_gate < engagement_observation
    assert engagement_observation < misdirection < ranged_pull
    assert "validation_route_patrol_wait_for_growl_off" in text[growl_gate:engagement_observation]
    assert text.index("validation_route_patrol_wait_for_misdirection",
                      misdirection) < ranged_pull


def test_hunter_patrol_never_mutates_admitted_pet_autocast_identity():
    text = MODULE.read_text()
    hunter_preparation = text.index("if (hunterPullOwner)")
    misdirection = text.index("HUNTER_MISDIRECTION_SPELL_ID", hunter_preparation)
    pet_setup = text[hunter_preparation:misdirection]

    assert "HUNTER_PET_GROWL_SPELL_ID = 2649" in text
    assert "growlInfo->IsAutocastable()" in pet_setup
    assert "pet->HasSpell(\n                    HUNTER_PET_GROWL_SPELL_ID)" in pet_setup
    assert "GetPetAutoSpellOnPos(index)" in pet_setup
    assert "patrol_pull_growl_autocast_not_off" in pet_setup
    assert "pet->ToggleAutocast" not in pet_setup
    assert "SetSpellAutocast" not in pet_setup
    assert "Bite and all" in text


def test_hunter_patrol_leaves_native_pet_attack_edges_untouched():
    text = MODULE.read_text()
    assert "pet->AttackStop()" not in text
    assert "referenceItr->second->EndCombat()" not in text


def test_hunter_provisioning_persists_growl_disabled_before_admission():
    config = json.loads(PROVISIONING.read_text(encoding="utf-8"))
    bwd = next(row for row in config["scenarios"]
               if row["id"] == "blackwing_descent_10n")
    hunter = next(bot for bot in bwd["bots"]
                  if bot.get("class_spec") == "marksmanship_hunter")
    pet = hunter["pet"]
    growl = next(spell for spell in pet["spells"]
                 if isinstance(spell, dict) and spell["id"] == 2649)
    assert growl["active"] == 129
    assert pet["actionbar"].split()[6:8] == ["129", "2649"]

    sql = build_character_insert_sql({
        "pet_guid_base": 8700000,
        "scenarios": [{
            "id": "bwd_test",
            "start_position": {"map_id": 669, "x": 0, "y": 0, "z": 0},
            "bots": [{
                "account": "A",
                "name": "Hunter",
                "role": "dps",
                "class_spec": "marksmanship_hunter",
                "race": 1,
                "class": 3,
                "level": 85,
                "pet": pet,
            }],
        }],
    })
    assert "VALUES (8700002, 2649, 129)" in sql
    assert "129 2649 1 0 1 0" in sql


def test_engaged_patrol_releases_this_bot_to_the_ordinary_action_queue():
    text = MODULE.read_text()
    engaged = text.index("if (!sourceEngaged)")
    handoff = text.index("enrollValidationRoutePackMember(source, true);")
    tank_gate = text.index("if (!botIsTank && !tankOwned)")
    release = text.index("SetAllOffenseSuppressed(", tank_gate)

    # Anchor staging and the pre-pull path guard are strictly unengaged work.
    assert engaged < text.index("float const anchorDistance", engaged)
    assert text.index("MoveBotToPoint(state, bot", engaged) < handoff

    # The engaged handoff may chase to the declared radius and wait for tank
    # threat, but it must not submit a healer/profile action itself.
    assert handoff < text.index("float const sourceAnchorDistance", handoff)
    assert text.index("sourceAnchorDistance", handoff) < tank_gate < release
    assert "tryRouteGroupHeal" not in text[handoff:]
    assert "ExecuteProfileCombatAction" not in text[handoff:]
    assert text[release:].strip().endswith("return false;\n}")


def test_engaged_patrol_does_not_reanchor_after_source_engagement():
    text = MODULE.read_text()
    engaged = text.index("if (!sourceEngaged)")
    anchor_move = text.index("validation_route_patrol_anchor_move")
    chase = text.index("validation_route_patrol_chase_to_anchor")

    assert anchor_move > engaged
    assert anchor_move < chase
    assert "validation_route_patrol_anchor_move" not in text[chase:]
