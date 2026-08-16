from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MELEE_INTENT = ROOT / "src/server/game/Bots/BotMeleeAutoAttackIntent.h"
NATIVE_INTENT = ROOT / "src/server/game/Bots/BotNativeActionIntent.h"
ACTION_ARBITER = ROOT / "src/server/game/Bots/BotActionArbiter.h"
EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
BOT_MGR = ROOT / "src/server/game/Bots/BotMgr.cpp"
BOT_CONTROLLER = ROOT / "src/server/game/Bots/BotController.cpp"


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def code_only(body: str) -> str:
    body = re.sub(r"//.*", "", body)
    return re.sub(r"/\*.*?\*/", "", body, flags=re.S)


FORBIDDEN_LIVE_MUTATIONS = (
    "SetFullHealth(",
    "SetFullPower(",
    "SetHealth(",
    "SetPower(",
    "ResurrectPlayer(",
    "TeleportTo(",
    "NearTeleportTo(",
    "CombatStop(",
    "CombatStopWithPets(",
    "SetInCombatWith(",
    "AddThreat(",
    "ClearAllThreat(",
    "SetReactState(",
    "SetEnchantment(",
    "Unit::Kill(",
    "DealDamage(",
    "Respawn(",
    "SpawnGroupSpawn(",
    "SummonCreature(",
    "SetData(",
    "DoAction(",
    "TRIGGERED_IGNORE_POWER_COST",
    "->AddQuest(",
    "->CompleteQuest(",
    "->RewardQuest(",
    "ModifyMoney(",
    "StoreLootItem(",
    "DurabilityRepairAll(",
)


def test_live_autonomy_functions_do_not_mutate_native_game_state() -> None:
    world = WORLD.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    controller = BOT_CONTROLLER.read_text(encoding="utf-8")
    live_functions = (
        function_body(world, "void BotWorldPopulationMgr::UpdateBot"),
        function_body(world, "BotWorldPopulationMgr::DeathRecoveryResult BotWorldPopulationMgr::RecoverDeadBot"),
        function_body(world, "bool BotWorldPopulationMgr::TryNativeCorpseRun"),
        function_body(world, "BotWorldPopulationMgr::QuestActionResult BotWorldPopulationMgr::TryQuesting"),
        function_body(world, "bool BotWorldPopulationMgr::TryValidationRouteObjective"),
        function_body(world, "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent"),
        function_body(world, "BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics"),
        function_body(world, "BotWorldPopulationMgr::DungeonTrashActionResult BotWorldPopulationMgr::TryDungeonTrash"),
        function_body(world, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup"),
        function_body(world, "bool BotWorldPopulationMgr::TryEnsureCombatTotems"),
        function_body(world, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState*"),
        function_body(executor, "BotActionResult BotActionExecutor::ExecuteCombat"),
        function_body(executor, "BotActionExecutor::LootResult BotActionExecutor::AutoLoot"),
        function_body(executor, "BotEconomyActionResult BotActionExecutor::VendorTrash"),
        function_body(executor, "BotEconomyActionResult BotActionExecutor::Repair"),
        function_body(controller, "void BotController::Update"),
    )

    for body in map(code_only, live_functions):
        for forbidden in FORBIDDEN_LIVE_MUTATIONS:
            assert forbidden not in body, forbidden
        for forbidden_command_path in (
            "ChatHandler(",
            "ParseCommands(",
            "ExecuteCommand(",
            "HandleCommand(",
        ):
            assert forbidden_command_path not in body, forbidden_command_path


def test_native_player_handlers_are_the_only_progression_boundaries() -> None:
    world = WORLD.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")

    corpse_run = function_body(world, "bool BotWorldPopulationMgr::TryNativeCorpseRun")
    assert "BotNativeAction::ReleaseSpirit" in corpse_run
    assert "BotNativeAction::ReclaimCorpse" in corpse_run

    quest_accept = function_body(world, "bool SubmitNativeQuestAccept")
    quest_reward = function_body(world, "bool SubmitNativeQuestReward")
    assert "HandleQuestgiverAcceptQuestOpcode" in quest_accept
    assert "HandleQuestgiverChooseRewardOpcode" in quest_reward

    loot = function_body(executor, "BotActionExecutor::LootResult BotActionExecutor::AutoLoot")
    for handler in (
        "HandleLootOpcode",
        "HandleLootMoneyOpcode",
        "HandleAutostoreLootItemOpcode",
        "HandleLootReleaseOpcode",
    ):
        assert handler in loot

    combat = function_body(executor, "BotActionResult BotActionExecutor::ExecuteCombat")
    assert "HandlePetActionHelper" in combat
    assert "TRIGGERED_IGNORE_POWER_COST" not in combat

    native_intents = function_body(
        world,
        "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent",
    )
    for allowed_player_boundary in (
        "MoveBotToPoint",
        "CastSpell",
        "HandlePetActionHelper",
        "HandleSpellClick",
        "HandleGameObjectUseOpcode",
        "HandleAreaTriggerOpcode",
        "HandleGossipHelloOpcode",
        "HandleGossipSelectOptionOpcode",
        "HandleRepopRequestOpcode",
        "HandleReclaimCorpseOpcode",
    ):
        assert allowed_player_boundary in native_intents
    melee_reconcile = function_body(
        world, "void BotWorldPopulationMgr::ResolveAndReconcileMeleeAutoAttack"
    )
    assert "bot->Attack(target, true)" in melee_reconcile
    assert "bot->AttackStop()" in melee_reconcile


def test_login_does_not_promote_stabled_pets_or_restore_resources() -> None:
    source = BOT_MGR.read_text(encoding="utf-8")
    login = function_body(source, "Player* BotMgr::LoadCharacterAsBotSession")
    for forbidden in (
        "UPDATE character_pet",
        "SetFullHealth(",
        "SetFullPower(",
        "SetPower(",
        "SetHealth(",
    ):
        assert forbidden not in login
    assert "provisioning must assign a valid active pet" in login


def test_hunter_admission_observes_exact_ordinary_pet_without_manufacturing_state() -> None:
    source = WORLD.read_text(encoding="utf-8")
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
        encoding="utf-8"
    )
    observer = function_body(source, "bool ObserveActiveOrdinaryHunterPet")
    declared_spec = function_body(source, "bool LoadedBotMatchesDeclaredSpec")
    pinned_pet = function_body(source, "bool LoadedBotMatchesPinnedHunterPet")
    admission = function_body(
        source, "void BotWorldPopulationMgr::EnsureValidationCohortGroup"
    )

    for token in (
        "stored->Type != HUNTER_PET",
        "pet->getPetType() != HUNTER_PET",
        "pet->IsPermanentPetFor",
        "GetPetNumber() != stored->PetId",
        "pet->GetEntry() != stored->CreatureId",
        "petSpell.state != PETSPELL_REMOVED",
        "petSpell.type != PETSPELL_FAMILY",
        "observed.Spellbook == expectedSpellbook",
        "observed.PetId == expectedPetId",
        "observed.PetEntry == expectedPetEntry",
    ):
        assert token in observer or token in pinned_pet
    assert "!activeObservationOnly" in admission
    assert "!LoadedBotMatchesPinnedHunterPet(bot, slot.ClassSpec)" in admission
    for field in (
        "PetIdentityPresent",
        "PetId",
        "PetEntry",
        "PetSpellbook",
        "PetSpellbookSha256",
    ):
        assert field in header
    for receipt_key in (
        r'\"pet_identity_present\"',
        r'\"pet_id\"',
        r'\"pet_entry\"',
        r'\"pet_spellbook\"',
        r'\"pet_spellbook_sha256\"',
    ):
        assert receipt_key in source
    observed_admission = code_only(observer + declared_spec + pinned_pet + admission)
    for forbidden in (
        "addSpell(",
        "learnSpell(",
        "ToggleAutocast(",
        "SummonPet(",
        "LoadPetData(",
        "DELETE FROM `pet_spell`",
        "DELETE ps FROM `pet_spell`",
        "INSERT INTO `pet_spell`",
        "ChatHandler(",
        "ExecuteCommand(",
    ):
        assert forbidden not in observed_admission


def test_active_hunter_pet_identity_is_reconciled_against_catalog_and_frozen_receipt() -> None:
    source = WORLD.read_text(encoding="utf-8")
    admission = function_body(
        source, "void BotWorldPopulationMgr::EnsureValidationCohortGroup"
    )
    active = admission[
        admission.index("if (activeObservationOnly)") : admission.index(
            "if (members.empty())"
        )
    ]

    for token in (
        "admission.AdmissionReceiptByGuid.find",
        "ObserveActiveOrdinaryHunterPet(bot, observedPet)",
        "ResolveExpectedHunterPetIdentity(",
        "observedPet.PetId == expectedPetId",
        "observedPet.PetEntry == expectedPetEntry",
        "observedPet.Spellbook == expectedSpellbook",
        "observedPet.SpellbookSha256",
        "frozenPet.PetId == observedPet.PetId",
        "frozenPet.PetEntry == observedPet.PetEntry",
        "frozenPet.PetSpellbook == observedPet.Spellbook",
        "frozenPet.PetSpellbookSha256 == observedPet.SpellbookSha256",
        '"validation_active_hunter_pet_receipt_missing"',
        '"validation_active_hunter_pet_missing"',
        '"validation_active_hunter_pet_canonical_identity_drift"',
        '"validation_active_hunter_pet_admission_identity_drift"',
        "MarkValidationCohortViolation(*invalidState, invalidBot, invalidReason)",
    ):
        assert token in active

    # Active reconciliation is observation-only: it can close the action gate
    # through the existing terminal-violation path, but cannot repair the pet.
    for forbidden in (
        "addSpell(",
        "learnSpell(",
        "ToggleAutocast(",
        "SummonPet(",
        "LoadPetData(",
        "TryCastFriendlySpell(",
        "DELETE FROM `pet_spell`",
        "INSERT INTO `pet_spell`",
    ):
        assert forbidden not in code_only(active)


def test_certifying_routes_use_server_owned_manifest_entrance_placement() -> None:
    source = WORLD.read_text(encoding="utf-8")
    ensure_population = function_body(
        source, "void BotWorldPopulationMgr::EnsurePopulation"
    )
    placement = function_body(
        source, "bool BotWorldPopulationMgr::ResolveSpawnPlacement"
    )
    manifest_start = ensure_population.index(
        "placement.Source = \"server_route_manifest_entrance\""
    )
    provision = ensure_population.index("ProvisionWorldBot", manifest_start)
    assert manifest_start < provision
    validation_guard = placement.index(
        "if (Cohort().Config.ValidationRouteEnable)"
    )
    generic_modes = placement.index("std::string mode", validation_guard)
    assert "return false;" in placement[validation_guard:generic_modes]
    assert "ResolveSavedSpawnPlacement" not in placement[validation_guard:generic_modes]


def test_server_provisioning_is_separate_from_active_bot_actions() -> None:
    world = WORLD.read_text(encoding="utf-8")
    manager = BOT_MGR.read_text(encoding="utf-8")
    ensure_population = function_body(
        world, "void BotWorldPopulationMgr::EnsurePopulation"
    )
    update_bot = function_body(world, "void BotWorldPopulationMgr::UpdateBot")
    provision = function_body(manager, "Player* BotMgr::ProvisionWorldBot(")
    provision_grouped = function_body(
        manager, "Player* BotMgr::ProvisionWorldBotInGroup("
    )
    login = function_body(manager, "Player* BotMgr::LoadCharacterAsBotSession")

    assert "ProvisionWorldBot(" in ensure_population
    assert "ProvisionWorldBotInGroup(" in ensure_population
    assert "ProvisionWorldBot(" not in update_bot
    assert "ProvisionWorldBotInGroup(" not in update_bot
    assert "_worldBots.insert(botGuid);" in provision
    assert "_worldBots.insert(botGuid);" in provision_grouped
    assert provision.index("LoadBotFromPool(") < provision.index("_worldBots.insert(botGuid);")
    assert provision_grouped.index("LoadBotFromPool(") < provision_grouped.index(
        "_worldBots.insert(botGuid);"
    )

    difficulty_guard = login.index(
        "if (provisionedDungeonDifficulty != NoProvisionedDungeonDifficulty)"
    )
    difficulty_set = login.index("bot->SetDungeonDifficulty(", difficulty_guard)
    placement_guard = login.index("if (placement)", difficulty_set)
    admission = login.index("Map::PlayerCannotEnter(", placement_guard)
    map_admission = login.index("destinationMap->CannotEnter(bot)", admission)
    relocate = login.index("bot->Relocate(", map_admission)
    assert difficulty_guard < difficulty_set < placement_guard < admission < map_admission < relocate


def test_activation_barrier_and_native_recovery_cannot_reprovision_or_reinsert() -> None:
    world = WORLD.read_text(encoding="utf-8")
    formation = function_body(
        world, "void BotWorldPopulationMgr::EnsureValidationCohortGroup"
    )
    update_bot = function_body(world, "void BotWorldPopulationMgr::UpdateBot")
    reattach = function_body(
        world, "bool BotWorldPopulationMgr::TryReattachValidationBot"
    )
    corpse_run = function_body(world, "bool BotWorldPopulationMgr::TryNativeCorpseRun")

    assert "raid.ServerProvisioningComplete" in formation
    assert "raid.BotActionsEnabled" in formation
    # Identity is frozen by the inert server transaction before the action
    # gate opens; UpdateBot still rejects every action until the gate commits.
    assert formation.index("state.ValidationCohortLocked = true;") < formation.index(
        "raid.BotActionsEnabled = true;"
    )
    assert "ValidationCohortLocked" in update_bot
    for body in (update_bot, reattach, corpse_run):
        assert "ProvisionWorldBot(" not in body
        assert "ProvisionWorldBotInGroup(" not in body
        assert "AddPlayerToMap(" not in body
        assert "Relocate(" not in body
        assert "TeleportTo(" not in body
        assert "NearTeleportTo(" not in body


def test_combat_reservation_precedes_release_and_validation_self_res() -> None:
    world = WORLD.read_text(encoding="utf-8")
    update_bot = function_body(world, "void BotWorldPopulationMgr::UpdateBot")
    planner = function_body(
        world, "void BotWorldPopulationMgr::ReconcileNativeBattleResDecisions"
    )
    combat_res_builder = function_body(
        world, "BotWorldPopulationMgr::BuildCombatResNativeActionCandidate"
    )
    native_executor = function_body(
        world,
        "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent",
    )

    reservation = update_bot.index("bool const combatResReservationPresent")
    reservation_wait = update_bot.index("if (battleResReserved)", reservation)
    self_res = update_bot.index("TryNativeSelfResurrection", reservation_wait)
    recovery_dispatch = update_bot.index("RecoverDeadBot(state, bot)", self_res)
    assert reservation < reservation_wait < self_res < recovery_dispatch
    recovery = function_body(
        world, "BotWorldPopulationMgr::DeathRecoveryResult BotWorldPopulationMgr::RecoverDeadBot"
    )
    assert 'mode == "native_corpse_run"' in recovery
    assert "TryNativeCorpseRun(state, bot, result)" in recovery
    assert "if (!Cohort().Config.ValidationRouteEnable" in update_bot[
        reservation_wait:recovery_dispatch
    ]
    for decision in (
        '"reserved_approach"',
        '"reserved_cast_submitted"',
        '"declined_out_of_combat"',
        '"declined_no_usable_combat_res"',
        '"declined_low_recovery_utility"',
        '"declined_lower_priority"',
    ):
        assert decision in planner
    assert "NativeBattleResOwnerGuid" in planner
    assert "NativeBattleResSpellId" in planner
    assert "CurrentCombatResOwnerUsable" in combat_res_builder
    assert 'candidate.Id.Strategy = "typed_combat_res"' in combat_res_builder
    assert "BotNativeAction::CombatResApproach" in combat_res_builder
    assert "BotNativeAction::CombatResCast" in combat_res_builder
    assert "BotNativeAction::CombatResAccept" in combat_res_builder
    assert "HandleResurrectResponseOpcode" in native_executor
    assert "TryNativePartyResurrection" not in world


def test_certifying_native_recovery_is_receipt_bound_and_bounded() -> None:
    world = WORLD.read_text(encoding="utf-8")
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
        encoding="utf-8"
    )
    corpse_run = function_body(world, "bool BotWorldPopulationMgr::TryNativeCorpseRun")
    recovery = function_body(
        world,
        "BotWorldPopulationMgr::DeathRecoveryResult BotWorldPopulationMgr::RecoverDeadBot",
    )
    raw = function_body(world, "std::string BotWorldPopulationMgr::BuildRawJson")
    terminal = function_body(world, "bool BotWorldPopulationMgr::FailValidationAttemptOnce")
    recovery_receipt = function_body(
        world, "std::string BotWorldPopulationMgr::BuildNativeRecoveryEpisodeJson"
    )
    update = function_body(world, "void BotWorldPopulationMgr::UpdateBot")

    for field in (
        "NativeRecoveryEpisodeAttemptId",
        "NativeRecoveryEpisodeRouteGeneration",
        "NativeRecoveryEpisodeWipeGeneration",
        "NativeRecoveryEpisodeDeathOrdinal",
        "NativeRecoveryEpisodePhase",
        "NativeRecoveryEpisodeStartedMs",
        "NativeRecoveryEpisodeLastProgressMs",
        "NativeRecoveryEpisodeDistanceTarget",
        "NativeRecoveryEpisodeBestDistance",
        "NativeRecoveryMovementRetryCount",
        "NativeRecoveryReleaseRejectionCount",
        "NativeRecoveryEntranceUnavailableCount",
        "NativeRecoveryEntranceRejectionCount",
        "NativeRecoveryReclaimRejectionCount",
        "NativeRecoveryEntranceRequired",
        "NativeRecoveryEntranceObserved",
        "NativeRecoveryEntranceAvailable",
    ):
        assert field in header
        assert field in recovery_receipt

    assert "BuildNativeRecoveryEpisodeJson(state)" in raw
    assert "BuildNativeRecoveryEpisodeJson(&reporterState)" in terminal
    assert "if (!result.empty())" in recovery
    assert "recovery.Result = result;" in recovery

    assert "NativeRecoveryNoProgressMs = 30000" in corpse_run
    assert "MaximumEntranceUnavailableObservations = 3" in corpse_run
    assert "MaximumEntranceRejections = 3" in corpse_run
    assert "MaximumMovementRejections = 5" in corpse_run
    assert "MaximumReclaimRejections = 5" in corpse_run
    assert 'terminal("native_entrance_unavailable")' in corpse_run
    assert 'terminal("native_runback_no_progress")' in corpse_run
    assert "FailValidationAttemptOnce(state, bot, reason" in corpse_run
    assert "ResolveNativeValidationEntrance" in corpse_run
    assert "BotNativeAction::Move" in corpse_run
    assert "BotMovementArbitration::Owner::Recovery" in corpse_run
    assert "BotMovementArbitration::Priority::Recovery" in corpse_run
    assert "BotNativeAction::ReleaseSpirit" in corpse_run
    assert "BotNativeAction::AreaTrigger" in corpse_run
    assert "BotNativeAction::ReclaimCorpse" in corpse_run
    assert "GetMotionMaster()->MovePoint" not in corpse_run
    assert "HandleRepopRequestOpcode" not in corpse_run
    assert "HandleAreaTriggerOpcode" not in corpse_run
    assert "HandleReclaimCorpseOpcode" not in corpse_run
    assert "ResurrectPlayer" not in corpse_run
    assert "TeleportTo(" not in corpse_run
    assert "NearTeleportTo(" not in corpse_run
    # DeadTimer remains a scheduling cadence only. Episode timestamps survive
    # each retry and therefore close the attempt before the outer watchdog.
    assert "state.DeadTimer = 0;" in update
    assert "state.NativeRecoveryEpisodeLastProgressMs" in corpse_run
    assert "nowMs - state.NativeRecoveryEpisodeLastProgressMs" in corpse_run
    # The former BWD-only direct movement fork must not bypass the shared
    # configured entrance (Stonecore 6196 in the checked-in route receipt).
    assert "if (Cohort().Config.ValidationRouteEnable && Cohort().Config.AllowRaids)" not in update
    scenario_manifest = (
        ROOT / "experiments/configs/validation_scenarios_cata_001.json"
    ).read_text(encoding="utf-8")
    assert '"area_trigger_id": 6196' in scenario_manifest
    assert '"source_map_id": 646' in scenario_manifest
    assert '"target_map_id": 725' in scenario_manifest


def test_combat_res_owner_usability_is_shared_and_live_reconciled() -> None:
    world = WORLD.read_text(encoding="utf-8")
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
        encoding="utf-8"
    )
    predicate = function_body(
        world, "bool BotWorldPopulationMgr::CurrentCombatResOwnerUsable"
    )
    planner = function_body(
        world, "void BotWorldPopulationMgr::ReconcileNativeBattleResDecisions"
    )
    update_bot = function_body(world, "void BotWorldPopulationMgr::UpdateBot")
    builder = function_body(
        world, "BotWorldPopulationMgr::BuildCombatResNativeActionCandidate"
    )
    executor = function_body(
        world,
        "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent",
    )
    publisher = function_body(
        world, "void BotWorldPopulationMgr::PublishNativeBattleResDecision"
    )

    assert "bool CurrentCombatResOwnerUsable" in header
    assert 'targetState.NativeBattleResDecision == "reserved_approach"' in predicate
    assert 'targetState.NativeBattleResDecision == "reserved_cast_submitted"' in predicate
    for live_fact in (
        "!owner->IsInWorld()",
        "!owner->IsAlive()",
        "owner->GetMap() != target->GetMap()",
        "owner->GetInstanceId() != target->GetInstanceId()",
        "ownerGroup != targetGroup",
        "owner->IsInSameGroupWith(target)",
        "owner->HasSpell(spellId)",
        "SPELL_ATTR8_ENFORCE_IN_COMBAT_RESSURECTION_LIMIT",
        "HasPowerForSpell(owner, spellInfo)",
        "owner->GetSpellHistory()->IsReady(spellInfo)",
        "owner->HasUnitState(UNIT_STATE_CASTING)",
        "owner->GetSpellHistory()->HasGlobalCooldown(spellInfo)",
        "owner->IsWithinLOSInMap(target)",
        "owner->IsWithinDistInMap(target, resurrectionRange)",
        "PathGenerator path(owner)",
        "PATHFIND_NOPATH",
        "IsNativeCombatResTarget(targetState, target)",
    ):
        assert live_fact in predicate

    # Owner death and map/instance drift are checked again before the dead bot
    # can wait, not merely when the approach reservation is first planned.
    assert 'declineReason = "declined_owner_dead"' in predicate
    assert 'declineReason = "declined_owner_wrong_map"' in predicate
    assert 'declineReason = "declined_owner_wrong_instance"' in predicate
    assert "acceptedApproachIntentCurrent" in predicate
    assert "NativeBattleResApproachIntentDecisionAtMs" in predicate
    assert "NativeBattleResApproachIntentAcceptedUntilMs > nowMs" in predicate
    assert "&& !acceptedApproachIntentCurrent" in predicate
    assert planner.count("CurrentCombatResOwnerUsable(") >= 2
    assert update_bot.count("CurrentCombatResOwnerUsable(") >= 1
    assert builder.count("CurrentCombatResOwnerUsable(") >= 1
    assert executor.count("CurrentCombatResOwnerUsable(") >= 1
    assert "PublishNativeBattleResDecision(" in planner
    assert "PublishNativeBattleResDecision(" in update_bot
    assert "PublishNativeBattleResDecision(" in executor
    assert "acceptedCombatResIntentCurrent" in update_bot
    assert "NativeBattleResApproachIntentAcceptedUntilMs" in update_bot
    assert '"declined_typed_intent_not_current"' in update_bot
    # A planner proposal has no acceptance receipt. Only the exact approach
    # selected by the typed arbiter may briefly coexist with damage GCD/cast.
    assert "NativeBattleResApproachIntentDecisionAtMs = 0" in planner
    assert "NativeBattleResApproachIntentAcceptedUntilMs = 0" in planner
    assert "bool const castResourcesFree" in builder
    assert "inCastEnvelope && castResourcesFree" in builder
    hard_cast_hold = executor.index(
        '"typed_combat_res_waiting_for_active_cast"'
    )
    approach_move = executor.index("MoveBotToPoint(state, bot", hard_cast_hold)
    assert hard_cast_hold < approach_move
    assert "typed_combat_res_cast_resources_pending" in executor

    # Declines clear only bot-owned reservation bookkeeping and publish a
    # typed observation; no resurrection or release state is manufactured.
    assert 'decision.rfind("declined_", 0) == 0' in publisher
    assert "NativeResurrectionPendingUntilMs = 0" in publisher
    assert 'RecordEvent(targetState, target, "battle_res_decision"' in publisher
    for forbidden in (
        "ResurrectPlayer(",
        "TeleportTo(",
        "NearTeleportTo(",
        "SetHealth(",
        "HandleRepopRequestOpcode",
    ):
        assert forbidden not in predicate + publisher


def test_combat_res_scheduler_owns_movement_cast_and_native_acceptance() -> None:
    world = WORLD.read_text(encoding="utf-8")
    intents = (ROOT / "src/server/game/Bots/BotNativeActionIntent.h").read_text(
        encoding="utf-8"
    )
    update = function_body(world, "void BotWorldPopulationMgr::UpdateBot")
    builder = function_body(
        world, "BotWorldPopulationMgr::BuildCombatResNativeActionCandidate"
    )
    executor = function_body(
        world,
        "BotActionArbitration::Outcome BotWorldPopulationMgr::ExecuteNativeActionIntent",
    )
    route = function_body(
        world, "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    trash = function_body(world, "BotWorldPopulationMgr::DungeonTrashActionResult BotWorldPopulationMgr::TryDungeonTrash")
    boss = function_body(world, "BotWorldPopulationMgr::BossMechanicActionResult BotWorldPopulationMgr::TryBossMechanics")

    assert "TryNativePartyResurrection" not in world
    for intent in ("CombatResApproach", "CombatResCast", "CombatResAccept"):
        assert f"struct {intent}" in intents
        assert f"BotNativeAction::{intent}" in builder
        assert f"BotNativeAction::{intent}" in executor
    approach_resources = intents.split(
        "if constexpr (std::is_same_v<T, CombatResApproach>)", 1
    )[1].split("if constexpr", 1)[0]
    assert "return Uses(Resource::Movement);" in approach_resources
    for forbidden_resource in (
        "Resource::GlobalCooldown",
        "Resource::Cast",
        "Resource::Target",
    ):
        assert forbidden_resource not in approach_resources
    assert intents.count("Resource::Movement, Resource::GlobalCooldown") >= 1
    assert "Resource::Cast, Resource::Target" in intents
    assert "Resource::Interaction, Resource::Target" in intents
    assert "candidate.RequiredResources = combatRes->Resources()" in update
    assert "state.DecisionKernel.Submit(std::move(candidate))" in update
    assert "CurrentCombatResOwnerUsable" in builder
    assert "CurrentCombatResOwnerUsable" in executor
    assert "typed_combat_res_cast_resources_pending" in executor
    assert "typed_combat_res_waiting_for_active_cast" in executor
    assert "targetState->NativeBattleResDecisionAtMs != reservationAtMs" in executor
    assert "targetState->NativeBattleResDecisionUntilMs" in executor
    assert "!= reservationUntilMs" in executor

    # Route/boss/trash no longer own a combat-res subroutine. The candidate
    # builder is observation-only; only the typed executor crosses native
    # movement, cast, and response boundaries.
    for monolith in (route, trash, boss):
        assert "TryNativePartyResurrection" not in monolith
    for direct_boundary in (
        "MoveBotToProfileRange",
        "HandleResurrectResponseOpcode",
        "CastSpell(",
    ):
        assert direct_boundary not in builder
    assert "MoveBotToPoint(state, bot" in executor
    assert "bot->CastSpell(target" in executor
    assert "HandleResurrectResponseOpcode(response)" in executor
    assert "ResurrectPlayer(" not in executor


def test_validation_admission_is_monotonic_and_active_population_is_observation_only() -> None:
    world = WORLD.read_text(encoding="utf-8")
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
        encoding="utf-8"
    )
    ensure = function_body(world, "void BotWorldPopulationMgr::EnsurePopulation")
    formation = function_body(
        world, "void BotWorldPopulationMgr::EnsureValidationCohortGroup"
    )
    violation = function_body(
        world, "void BotWorldPopulationMgr::MarkValidationCohortViolation"
    )

    assert "enum class ValidationAdmissionPhase" in header
    assert "Provisioning = 0" in header
    assert "Active = 1" in header
    assert "Terminal = 2" in header
    active_gate = ensure.index(
        "Cohort().ValidationAdmission == ValidationAdmissionPhase::Active"
    )
    provisioning_loop = ensure.index("while (Cohort().Active")
    assert active_gate < provisioning_loop
    active_branch = ensure[active_gate:provisioning_loop]
    assert "EnsureValidationCohortGroup();" in active_branch
    assert "return;" in active_branch
    assert "ValidationAdmissionStarted" in ensure
    assert "validation_admission_reentry_before_activation" in ensure
    assert "ValidationAdmissionBatchSealed" in ensure
    first_validation_gate = ensure.index("if (Cohort().Config.ValidationRouteEnable)")
    first_roster_rejection = ensure.index('rejectPopulation("unsupported_exact_raid_size")')
    assert first_validation_gate < first_roster_rejection
    assert "terminateValidationAdmission(reason);" in ensure[
        first_validation_gate:first_roster_rejection
    ]
    assert "ValidationAdmissionPhase::Active" in formation
    assert "ValidationAdmissionPhase::Terminal" in violation

    assert "if (!activeObservationOnly && !member->GetGroup()" in formation
    assert "if (!activeObservationOnly && raidValidation && !group->isRaidGroup())" in formation
    assert "if (!activeObservationOnly && raidValidation && group->GetMemberGroup" in formation
    assert "if (!activeObservationOnly && role == \"tank\")" in formation


def test_melee_autoattack_is_a_persistent_toggle_independent_of_movement_and_gcd() -> None:
    world = WORLD.read_text(encoding="utf-8")
    lane = MELEE_INTENT.read_text(encoding="utf-8")
    native = NATIVE_INTENT.read_text(encoding="utf-8")
    arbiter = ACTION_ARBITER.read_text(encoding="utf-8")
    reconcile = function_body(
        world, "void BotWorldPopulationMgr::ResolveAndReconcileMeleeAutoAttack"
    )
    submit = function_body(
        world, "bool BotWorldPopulationMgr::SubmitMeleeAutoAttackIntent"
    )
    execute_profile = function_body(
        world, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState*"
    )
    update_bot = function_body(world, "void BotWorldPopulationMgr::UpdateBot")
    move_range = function_body(
        world, "bool BotWorldPopulationMgr::MoveBotToProfileRange"
    )

    assert "StartAttack" not in native
    assert "StopAttack" not in native
    assert "AutoAttackToggle = 1 << 6" in arbiter
    assert "Kind::StartOrSwitch" in lane
    assert "Kind::Stop" in lane
    assert "Kind::Suppress" in lane
    assert "Resource::AutoAttackToggle" in lane
    assert "std::sort(_candidates.begin(), _candidates.end(), Better)" in lane
    assert "KindRank(left.Toggle)" in lane
    assert "state.MeleeAutoAttackLane.Submit" in submit
    assert "bot->AttackStop()" in reconcile
    assert "BotRaidAreaAuthority::IsAllOffenseSuppressed" in reconcile
    assert "BotRaidAreaAuthority::IsProtectedEncounterTarget" in reconcile
    assert reconcile.index("bot->Attack(target, true)") < reconcile.index(
        "bot->IsWithinMeleeRange(target)"
    )
    assert "MoveBotToPoint" not in reconcile
    assert "AttackStop" not in move_range
    assert execute_profile.index('"profile_melee_autoattack"') < execute_profile.index(
        "TryEnsurePersistentCombatSetup"
    )
    assert "ReconcileOnScopeExit meleeAutoAttackReconcile" in update_bot
    assert "ResolveAndReconcileMeleeAutoAttack(state, bot);" in update_bot
    assert "executor.Pull(bot" not in world
    assert "action.MeleeAutoAttackExternallyReconciled = state" in execute_profile
    for field in (
        "melee_auto_attack_intent_owner",
        "melee_auto_attack_intent_kind",
        "melee_auto_attack_intent_reason",
        "melee_auto_attack_outcome",
        "melee_auto_attack_intent_priority",
        "melee_auto_attack_candidate_count",
    ):
        assert field in world
    manager_code = code_only(world)
    assert manager_code.count("bot->Attack(target, true)") == 1
    assert manager_code.count("bot->AttackStop()") == 2
    assert "StopDesiredMeleeAutoAttack" not in manager_code
    assert "ReconcileDesiredMeleeAutoAttack" not in manager_code


def test_fixture_mutations_remain_outside_live_update_paths() -> None:
    source = WORLD.read_text(encoding="utf-8")
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")
    calibration = function_body(source, "void BotWorldPopulationMgr::UpdateCalibrationControlledDamage")
    calibration_start = function_body(source, "std::string BotWorldPopulationMgr::StartCombatCalibration(std::string const& mode")
    calibration_status = function_body(source, "std::string BotWorldPopulationMgr::GetCombatCalibrationJson() const")
    replay = function_body(source, "BotWorldPopulationMgr::ReplayExecutionResult BotWorldPopulationMgr::ExecuteReplayRecord")
    update_bot = function_body(source, "void BotWorldPopulationMgr::UpdateBot")

    # Synthetic mutations are explicit, isolated, and forever non-certifying.
    assert "SetHealth(" in calibration
    assert "ResurrectPlayer(" in replay
    assert "CalibrationFixture" in header
    assert "ReplayFixture" in header
    assert "NonCertifyingAssistance" in header
    assert "!Party().Bots.empty() || Cohort().Config.TargetPopulation != 0" in calibration_start
    assert "BotWorldRuntimeMode::CalibrationFixture" in calibration_start
    assert "Cohort().NonCertifyingAssistance = true" in calibration_start
    assert '\\\"runtime_mode\\\"' in calibration_status
    assert 'RuntimeModeName(Cohort().RuntimeMode)' in calibration_status
    assert '\\\"non_certifying_assistance\\\"' in calibration_status
    assert "BotWorldRuntimeMode::ReplayFixture" in replay
    assert "Cohort().NonCertifyingAssistance = true" in replay
    assert replay.index("BotWorldRuntimeMode::ReplayFixture") < replay.index("ResurrectPlayer(")
    assert "UpdateCalibrationControlledDamage" not in update_bot
    assert "ExecuteReplayRecord" not in update_bot
