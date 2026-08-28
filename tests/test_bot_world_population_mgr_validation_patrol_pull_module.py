from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationPatrolPull.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


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
        "member->GetGroup() == bot->GetGroup()",
        "member->GetMap() == bot->GetMap()",
        "member != bot",
        'memberRoster->second.Role == \"tank\"',
    ):
        assert marker in selector


def test_hunter_patrol_preparation_orders_growl_misdirection_before_pull():
    text = MODULE.read_text()
    hunter_preparation = text.index("if (hunterPullOwner)")
    growl_disable = text.index("pet->ToggleAutocast(growlInfo, false)",
                               hunter_preparation)
    engagement_observation = text.index(
        "bool const sourceEngaged = isValidationCohortCombatLinked(source);",
        hunter_preparation,
    )
    misdirection = text.index(
        "TryCastFriendlySpell(bot, tank,", engagement_observation)
    ranged_pull = text.index("ResolveProfileCombatAction(", misdirection)

    assert growl_disable < engagement_observation
    assert engagement_observation < misdirection < ranged_pull
    assert text.index("validation_route_patrol_wait_for_misdirection",
                      misdirection) < ranged_pull


def test_hunter_patrol_disables_only_native_growl_autocast():
    text = MODULE.read_text()
    hunter_preparation = text.index("if (hunterPullOwner)")
    misdirection = text.index("HUNTER_MISDIRECTION_SPELL_ID", hunter_preparation)
    pet_setup = text[hunter_preparation:misdirection]

    assert "HUNTER_PET_GROWL_SPELL_ID = 2649" in text
    assert "growlInfo->IsAutocastable()" in pet_setup
    assert "pet->HasSpell(\n                    HUNTER_PET_GROWL_SPELL_ID)" in pet_setup
    assert "pet->ToggleAutocast(growlInfo, false)" in pet_setup
    assert "charmInfo->SetSpellAutocast(growlInfo, false)" in pet_setup
    assert '"pet_growl_autocast_disabled"' in pet_setup
    assert "Bite and all" in text


def test_hunter_pet_edge_is_closed_before_unengaged_gate():
    text = MODULE.read_text()
    hunter_preparation = text.index("if (hunterPullOwner)")
    attack_stop = text.index("pet->AttackStop()", hunter_preparation)
    end_pet_reference = text.index("referenceItr->second->EndCombat()",
                                  attack_stop)
    engagement_observation = text.index(
        "bool const sourceEngaged = isValidationCohortCombatLinked(source);",
        end_pet_reference,
    )

    assert attack_stop < end_pet_reference < engagement_observation
    assert "pet->CombatStop" not in text[hunter_preparation:engagement_observation]


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
