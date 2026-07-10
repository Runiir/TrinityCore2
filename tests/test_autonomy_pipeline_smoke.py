from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_COMMANDS = ROOT / "src/server/scripts/Commands/cs_healerbot.cpp"
SERVER_COMMANDS = ROOT / "src/server/scripts/Commands/cs_server.cpp"
BOT_MGR = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
PLAYER_BOT_MGR = ROOT / "src/server/game/Bots/BotMgr.cpp"
PLAYER_BOT_CONTROLLER = ROOT / "src/server/game/Bots/BotController.cpp"
PLAYER_BOT_TYPES = ROOT / "src/server/game/Bots/BotTypes.cpp"
PLAYER_BOT_ACTION_PROFILE = ROOT / "src/server/game/Bots/BotClassSpecActionProfile.cpp"
PLAYER_BOT_EXECUTOR = ROOT / "src/server/game/Bots/BotActionExecutor.cpp"
BOT_MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
PET_CPP = ROOT / "src/server/game/Entities/Pet/Pet.cpp"
STONECORE_ROTATION_SQL = ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql"
BOT_POLICY = ROOT / "src/server/game/Bots/BotTelemetryPolicy.cpp"
BOT_BUFFER = ROOT / "src/server/game/Bots/BotTelemetryBuffer.cpp"
BOT_SEGMENTS = ROOT / "src/server/game/Bots/BotExperimentCoordinator.cpp"
WORLDSERVER_CONF = ROOT / "src/server/worldserver/worldserver.conf.dist"
CHASE_MOVEMENT = ROOT / "src/server/game/Movement/MovementGenerators/ChaseMovementGenerator.cpp"
MAP_CPP = ROOT / "src/server/game/Maps/Map.cpp"
PLAYER_CPP = ROOT / "src/server/game/Entities/Player/Player.cpp"
VALIDATION_SCENARIOS = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
PYTEST_CONFIG = ROOT / "pytest.ini"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
                return source[brace + 1:index]
    raise AssertionError(f"unterminated function body for {signature}")


def assert_ordered(text: str, *needles: str) -> None:
    cursor = -1
    for needle in needles:
        found = text.find(needle, cursor + 1)
        assert found != -1, needle
        cursor = found


def test_validation_scenario_trash_counts_are_descriptive_only():
    from tools.bot_ml.build_validation_scenario_manifests import build_manifests

    config = json.loads(read(VALIDATION_SCENARIOS))
    stonecore = next(scenario for scenario in config["scenarios"] if scenario["id"] == "stonecore_5n")
    trash_steps = [step for step in stonecore["route"] if step["kind"] == "trash"]
    assert all(
        "expected_alive_count" not in step
        if step.get("node_kind") == "discovery_leg"
        else step.get("expected_alive_count") != 0
        for step in trash_steps
    )

    manifest = build_manifests(config, {}, {"all_passed": True})
    generated_trash = [
        route
        for route in manifest["validation_routes"]
        if route["scenario_id"] == "stonecore_5n" and route["node_kind"] in {"trash_cluster", "discovery_leg"}
    ]
    assert generated_trash
    generated_by_step = {route["step"]: route for route in generated_trash}
    assert generated_by_step[2]["cluster_radius_yards"] == 35.0
    assert generated_by_step[2]["expected_alive_count"] == 4
    assert generated_by_step[3]["cluster_radius_yards"] == 0.0
    assert "expected_alive_count" not in generated_by_step[3]
    assert generated_by_step[3]["pack_target_entries"] == []
    assert all(route["expected_alive_count"] == len(route["pack_target_entries"]) for route in generated_trash if route["step"] not in {2, 3})
    assert all(route["expected_alive_count"] > 0 for route in generated_trash if route["node_kind"] == "trash_cluster")
    assert all(route["expected_alive_count_semantics"] == "descriptive_only" for route in generated_trash)
    assert all(route["completion_policy"] == "cluster_clear_after_pull" for route in generated_trash)
    corborus = next(route for route in manifest["validation_routes"] if route["scenario_id"] == "stonecore_5n" and route["label"] == "Corborus")
    assert corborus["add_target_entries"] == [43917]


def test_validation_route_group_focus_reaches_profile_action_without_threat_rewait():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    group_focus_start = route_objective.index("if (Unit* focusTarget = routeGroupFocusTarget())")
    group_focus_end = route_objective.index('if (std::string(GetDungeonRole(bot)) != "tank"\n        && (', group_focus_start)
    group_focus = route_objective[group_focus_start:group_focus_end]
    later_threat_gate = 'if (routeBossTarget && _config.ValidationRouteKind != "boss" && !botIsTank && !routeFocusTankOwned(target))'

    assert_ordered(
        group_focus,
        "target = focusTarget;",
        "if (tryRouteGroupHeal(bot, target))",
        "ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);",
    )
    assert "routeFocusTankOwned(target)" not in group_focus
    assert route_objective.index(later_threat_gate) > group_focus_end


def test_decision_tick_caps_combat_and_validation_before_minimum_floor():
    update_bot = function_body(read(BOT_MGR), "void BotWorldPopulationMgr::UpdateBot")

    assert_ordered(
        update_bot,
        'uint32 decisionTickMs = sConfigMgr->GetIntDefault("BotWorld.DecisionTickMs", 3000);',
        "if (bot->IsInCombat() || _config.ValidationRouteEnable)",
        "decisionTickMs = std::min<uint32>(decisionTickMs, 1000);",
        "state.DecisionTimer = std::max<uint32>(500, decisionTickMs);",
    )


def test_pytest_excludes_generated_orchestrator_worktrees():
    pytest_config = read(PYTEST_CONFIG)
    assert re.search(r"^testpaths\s*=\s*tests$", pytest_config, re.MULTILINE)
    assert re.search(r"^norecursedirs\s*=\s*generated/orchestrator_worktrees$", pytest_config, re.MULTILINE)


def test_validation_route_has_no_forced_teacher_damage_or_expected_empty_terminal():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    assert not re.search(r"\bUnit::(?:Kill|DealDamage)\s*\(", route_objective)
    assert "SetHealth(0" not in route_objective
    assert "JUST_DIED" not in route_objective
    assert "validation_route_teacher_assist" not in route_objective
    assert "trash_cluster_expected_empty" not in route_objective
    assert "&& !_config.ValidationRouteExpectedAliveCount" not in route_objective


def test_server_start_autonomy_enabled_by_default_contract():
    conf = read(WORLDSERVER_CONF)
    commands = read(BOT_COMMANDS)
    server_commands = read(SERVER_COMMANDS)
    startup = function_body(commands, "void OnStartup() override")
    shutdown_initiate = function_body(commands, "void OnShutdownInitiate(ShutdownExitCode /*code*/, ShutdownMask /*mask*/) override")
    shutdown = function_body(commands, "void OnShutdown() override")
    server_exit = function_body(server_commands, "static bool HandleServerExitCommand")

    assert re.search(r"^PlayerBot\.Enable\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.Enable\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.FastExitAfterShutdown\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoStart\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.ProfileManifest\s*=\s*"dataset/bot_runtime_profiles/profiles\.json"$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoStartRecording\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoRecordingWindowMinutes\s*=\s*15$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.TargetPopulation\s*=\s*5$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.PoolTagFilter\s*=\s*""$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.Enable\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.ValidationRoute\.ManifestPath\s*=\s*""$', conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.ValidationRoute\.AdvanceMode\s*=\s*"disabled"$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.TargetEntry\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.ValidationRoute\.AlternateTargetEntries\s*=\s*""$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.ActivationDataId\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.ActivationDataValue\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.ValidationRoute\.ActivationSummonEntry\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r'^BotWorld\.SpawnMode\s*=\s*"resume_or_race_start"$', conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AllowConfiguredCenterFallback\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.UseSavedPosition\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotProgression\.AllowQuesting\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotProgression\.AllowDungeons\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotProgression\.AllowRaids\s*=\s*0$", conf, re.MULTILINE)
    assert re.search(r"^BotLearning\.Enable\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotPolicyModel\.Enable\s*=\s*0$", conf, re.MULTILINE)
    assert "sBotMgr->ResetPoolUseState();" in startup
    assert 'sConfigMgr->GetBoolDefault("BotWorld.AutoStart", false)' in startup
    assert "sBotWorldPopulationMgr->StartAutonomy();" in startup
    assert "EnsurePopulation" not in startup
    assert "SpawnAutonomyBots" not in startup
    assert "StopAutonomy" not in shutdown_initiate
    assert "RemoveAll" not in shutdown_initiate
    assert "ResetPoolUseState" not in shutdown_initiate
    assert "deferred to final shutdown" in shutdown_initiate
    assert "sBotWorldPopulationMgr->Shutdown();" in shutdown
    assert "sBotWorldPopulationMgr->StopAutonomy();" not in shutdown
    assert "sBotMgr->RemoveAll();" in shutdown
    assert "sBotMgr->ResetPoolUseState();" in shutdown
    assert_ordered(
        server_exit,
        "sScriptMgr->OnShutdownInitiate(ShutdownExitCode(SHUTDOWN_EXIT_CODE), ShutdownMask(0));",
        "World::StopNow(SHUTDOWN_EXIT_CODE);",
    )


def test_playerbot_runtime_roles_drive_universal_profile_combat():
    bot_mgr = read(PLAYER_BOT_MGR)
    world_mgr = read(BOT_MGR)
    controller = read(PLAYER_BOT_CONTROLLER)
    role_types = read(PLAYER_BOT_TYPES)
    profiles = read(PLAYER_BOT_ACTION_PROFILE)
    executor = read(PLAYER_BOT_EXECUTOR)

    assert "SELECT cbp.guid, c.account, cbp.role, cbp.class_spec" in bot_mgr
    assert "std::string selectedClassSpec = fields[3].GetString();" in bot_mgr
    assert "Register(owner, bot, botRole, selectedRole, selectedClassSpec" in bot_mgr
    assert "NormalizeBotRole(runtimeRole.empty() ? ToString(role) : runtimeRole)" in controller
    assert "normalized == \"tank\"" in role_types
    assert "normalized == \"healer\"" in role_types
    assert "normalized == \"dps\"" in role_types

    update = function_body(controller, "void BotController::Update")
    assert_ordered(
        update,
        "BotCombatState combatState = BuildCombatState(owner, bot, recentEvents);",
        "_runtimeRole == \"healer\" && TryResolveHealerAction",
        "ResolveProfileCombat(combatDecision, combatState, bot, target)",
    )

    decide = function_body(controller, "BotCombatDecision BotController::DecideSoloCombat")
    assert "CombatArchetypeForClass(state.ClassId, _runtimeRole)" in decide
    assert "GetSoloCombatArchetype(_role) != BotCombatArchetype::RangedCaster" not in decide

    select_profile = function_body(controller, "BotActionCandidate const* BotController::SelectProfileCombatAction")
    assert "_runtimeRole == \"tank\"" in select_profile
    assert "state.NearbyHostileCount >= 2" in select_profile
    assert "candidate.Category == BotCombatActionCategory::Taunt && target && target->GetVictim() == bot" in select_profile
    assert "requires_ally_target" in select_profile

    healer = function_body(controller, "bool BotController::TryResolveHealerAction")
    assert "BotClassSpecActionProfileStore::Build(bot, \"healer\")" in healer
    assert "BotCombatActionCategory::HealFast" in healer
    assert "HolyPaladinResolver" not in healer

    assert "profile.SpecTag = profile.Role == \"healer\" ? \"restoration_or_elemental_generic\" : \"enhancement_or_elemental_generic\";" in profiles
    assert "profile.SpecTag = profile.Role == \"healer\" ? \"holy_disc_generic\" : \"shadow_or_generic\";" in profiles
    assert 'candidate.RejectReason = "target_health_gate";' in world_mgr
    assert 'candidate.RejectReason = "self_health_gate";' in world_mgr
    assert "SELECT class_spec FROM character_bot_pool WHERE guid" in profiles
    assert 'classSpec == "protection_paladin"' in profiles
    assert 'classSpec == "fire_mage"' in profiles
    assert 'classSpec == "marksmanship_hunter"' in profiles
    assert 'classSpec == "enhancement_shaman"' in profiles
    assert "spellInfo->PowerType == POWER_RUNE && spellInfo->RuneCostID" in profiles
    assert "sSpellRuneCostStore.LookupEntry(spellInfo->RuneCostID)" in profiles
    assert "bot->GetRuneCooldown(i)" in profiles
    assert "spellInfo->NeedsComboPoints()" in profiles
    assert "bot->GetComboTarget() != actionTarget->GetGUID()" in profiles
    assert "proc_or_opener" in profiles
    for spell_id in ["53595", "31935", "26573", "53600", "56641", "2643", "8042", "17364", "60103", "421", "2120", "1449"]:
        assert spell_id in profiles

    assert "if (!action.Valid)" in executor
    assert "bot->GetPower(bot->GetPowerType())" in executor
    assert "target != bot && !bot->IsValidAttackTarget(target, spellInfo)" in executor
    assert "spellInfo->PowerType == POWER_RUNE && spellInfo->RuneCostID" in executor
    assert "sSpellRuneCostStore.LookupEntry(spellInfo->RuneCostID)" in executor
    assert "bot->GetRuneCooldown(i)" in executor
    assert "spellInfo->NeedsComboPoints()" in executor
    assert "bot->GetComboTarget() != target->GetGUID()" in executor
    execute_combat = function_body(executor, "BotActionResult BotActionExecutor::ExecuteCombat")
    assert_ordered(
        execute_combat,
        "BotActionResult check = CheckHostileSpell(owner, bot, target, action.SpellId);",
        'action.AutoAttackMode == "melee"',
        "bot->Attack(target, true);",
        "SpellCastResult result = bot->CastSpell(target, action.SpellId, false);",
    )


def test_bwd_validation_roster_has_rotation_profiles():
    sql = read(STONECORE_ROTATION_SQL)
    for spec_tag in [
        "protection_warrior",
        "blood_death_knight",
        "restoration_druid",
        "holy_paladin",
        "discipline_priest",
        "assassination_rogue",
        "affliction_warlock",
        "elemental_shaman",
    ]:
        assert f"'{spec_tag}'" in sql

    for spell_id in ["78", "355", "2565", "45462", "45477", "56222", "8936", "19750", "2061", "1752", "686", "403"]:
        assert re.search(rf", {spell_id}, '", sql)
    assert "'protection_warrior' AND `role`='tank'), 30, 355, 'taunt'" in sql
    assert "'blood_death_knight' AND `role`='tank'), 35, 56222, 'taunt'" in sql
    assert "'blood_death_knight' AND `role`='tank'), 45, 45477, 'threat_build'" in sql
    assert "'protection_warrior' AND `role`='tank'), 35, 2565, 'defensive'" in sql
    assert "'restoration_druid' AND `role`='healer'), 10, 8936, 'heal_fast', 'regrowth,triage,heal', 0, 0.92, 0.75, 1, 1, 0.82" in sql
    assert "'holy_paladin' AND `role`='healer'), 20, 19750, 'heal_fast', 'flash_of_light,triage,heal', 0, 0.94, 0.75, 1, 1, 0.82" in sql
    assert "'discipline_priest' AND `role`='healer'), 20, 2061, 'heal_fast', 'flash_heal,triage,heal', 0, 1.00, 0.85, 1, 1, 0.82" in sql
    update_sql = read(ROOT / "sql/custom/world/2026_07_02_01_bwd_tank_threat_profiles.sql")
    assert "p.`class_id` = 1 AND p.`spec_tag` = 'protection_warrior'" in update_sql
    assert "p.`class_id` = 6 AND p.`spec_tag` = 'blood_death_knight'" in update_sql
    assert "'protection_warrior' AND `role`='tank'), 30, 355, 'taunt'" in update_sql
    assert "'blood_death_knight' AND `role`='tank'), 35, 56222, 'taunt'" in update_sql
    assert "'blood_death_knight' AND `role`='tank'), 45, 45477, 'threat_build'" in update_sql
    healer_update_sql = read(ROOT / "sql/custom/world/2026_07_02_02_bwd_healer_triage_profiles.sql")
    assert "a.`spell_id` = 8936 THEN 0.82" in healer_update_sql
    assert "a.`spell_id` = 635 THEN 0.94" in healer_update_sql


def test_validation_blockers_require_matching_resolution_and_trace_episode_fields():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    blocked = function_body(mgr, "void BotWorldPopulationMgr::MarkBotBlocked")
    unstuck = function_body(mgr, "bool BotWorldPopulationMgr::TryResolveBotBlocker")
    execute_profile = function_body(mgr, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction")
    trace = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionTrace")
    diagnose = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")

    for symbol in [
        "BlockedEpisodeId",
        "BlockedFirstReason",
        "BlockedResolution",
        "BlockedResolvedBy",
        "BlockedResolvedMs",
    ]:
        assert symbol in header

    assert "++state.BlockedEpisodeId" in blocked
    assert "Blocked: \" + state.BlockedFirstReason" in blocked
    assert "reason == resolver" in unstuck
    assert "buff_cast_failed:" in unstuck
    assert "totem_cast_failed:" in unstuck
    assert "cast_succeeded" in unstuck
    assert "hunter_pet_unprovisioned" in unstuck
    assert "hunter_pet_db_row_absent:" in unstuck
    assert "hunter_pet_load_failed:" in unstuck
    assert "hunter_pet_missing" in unstuck
    assert "movement_progress" in unstuck
    assert "TryResolveBotBlocker(*state, bot, \"profile_action_valid\")" in execute_profile
    assert "TryResolveBotBlocker(*state, bot, \"cast_succeeded\")" in execute_profile
    assert "MarkBotUnstuck(*state, bot, action.DebugName.c_str())" not in execute_profile
    assert "entry.BlockedEpisodeId = state.BlockedEpisodeId" in trace
    assert "blocked_first_reason" in diagnose
    assert "blocked_resolution" in diagnose


def test_validation_route_readiness_buffs_party_and_hunter_pet_without_fallbacks():
    mgr = read(BOT_MGR)
    readiness = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteReadiness")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    trash = function_body(mgr, "BotWorldPopulationMgr::DungeonTrashActionResult BotWorldPopulationMgr::TryDungeonTrash")

    for spell_id in ["25780", "31801", "465", "20217", "54428", "13165", "982", "1130", "34477"]:
        assert spell_id in readiness

    for buff_key in [
        "battle_shout_ready",
        "commanding_shout_ready",
        "power_word_fortitude_ready",
        "shadow_protection_ready",
        "horn_of_winter_ready",
        "arcane_brilliance_ready",
        "mark_of_the_wild_ready",
    ]:
        assert buff_key in readiness

    assert "if (!bot || bot->IsInCombat())" in readiness
    assert "_config.ValidationRouteEnable || !bot" not in readiness
    assert "ActiveBuffRequirement" in readiness
    assert "blessing_of_kings_ready" in readiness
    assert "strength_of_earth_totem_ready" not in readiness
    assert "wrath_of_air_totem_ready" not in readiness
    assert "flametongue_totem_ready" not in readiness
    assert "std::string(requirement.PartyWide ? \"missing_party_buff:\" : \"missing_self_buff:\") + requirement.Key" in readiness
    assert "ReadinessRetryUntilMs" in readiness
    assert "ReadinessPartyCoverageSignature" in readiness
    assert "!bot->IsWithinDistInMap(member, maxRange)" in readiness
    assert "state.ReadinessPartyCoverageSignature[attemptKey] == signature" in readiness
    assert "state.ReadinessPartyCoverageSignature[attemptKey] = signature" in readiness
    assert "RecordEvent(state, bot, \"validation_route_readiness\", member, failedReason.c_str()" in readiness
    assert "deferAttempt(attemptKey, failedReason.c_str())" in readiness
    assert "TryReconcileHunterPetDataFromDB" not in mgr
    assert "TrySummonConfiguredHunterPet" not in mgr
    assert "bot->SummonPet(petData->Slot" not in mgr
    assert "TryCastFriendlySpell(bot, bot, 883)" not in readiness
    assert "hunter_pet_load_failed:" in readiness
    assert "hunter_pet_missing" in readiness
    assert "hunter_pet_dead" in readiness
    assert "buff_cast_failed:\" << readyReason << \":spell=\" << spellId << \":target=\"" in readiness
    assert "if (!canAttempt(attemptKey))\n            return true;" in readiness
    assert "validation_route_readiness_misdirection" in readiness
    assert "for (GroupReference* itr = group->GetFirstMember()" in readiness
    assert "hasAnyAura(member, auraIds)" in readiness
    assert "validation_route_readiness_party_buff" in readiness
    assert "TryValidationRouteReadiness(state, bot, target" in route_objective
    assert "TryValidationRouteReadiness(state, bot, groupTarget" in trash
    assert "AttackStop" not in readiness
    assert "CombatStop" not in readiness


def test_headless_bot_spawn_forces_visibility_after_registration():
    bot_mgr = read(PLAYER_BOT_MGR)
    load = function_body(bot_mgr, "Player* BotMgr::LoadCharacterAsBotSession")

    assert_ordered(
        load,
        "bot->GetMap()->AddPlayerToMap(bot)",
        "ObjectAccessor::AddObject(bot)",
        "bot->LoadPetsFromDB(holder->GetPreparedResult(PLAYER_LOGIN_QUERY_LOAD_ALL_PETS))",
        "petData->Active = true",
        "bot->RemoveAurasByType(SPELL_AURA_MOUNTED)",
        "bot->LoadPet()",
        "bot->UpdateObjectVisibility(true)",
        "player->UpdateVisibilityOf(bot)",
        "SetBotCharacterOnline(guid, true)",
    )
    assert "Map::PlayerList const& players = map->GetPlayers()" in load
    assert "session->IsBotSession()" in load
    assert "bot->IsWithinDistInMap(player, bot->GetVisibilityRange())" in load
    assert "PlayerBot pets loaded" in load
    assert "PlayerBot hunter active-slot pet selected" in load
    assert "PlayerBot dismounted before pet load" in load


def test_persistent_pet_guid_uses_creature_entry_not_database_pet_id():
    pet_cpp = read(PET_CPP)
    create = function_body(pet_cpp, "bool Pet::Create(ObjectGuid::LowType")

    assert "Object::_Create(guidlow, Entry, HighGuid::Pet)" in create
    assert "Object::_Create(guidlow, petId, HighGuid::Pet)" not in create
    assert "m_charmInfo->SetPetNumber(petId" in function_body(pet_cpp, "bool Pet::LoadPetData")


def test_shaman_totems_are_combat_entry_setup_without_spam():
    mgr = read(BOT_MGR)
    totems = function_body(mgr, "bool BotWorldPopulationMgr::TryEnsureCombatTotems")
    execute_profile = function_body(mgr, "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction")

    for spell_id in ["8075", "3599", "5394", "8512"]:
        assert spell_id in totems

    assert "bot->IsInCombat()" in totems
    assert "m_SummonSlot" in totems
    assert "totem->IsTotem() && totem->IsAlive()" in totems
    assert "ReadinessRetryUntilMs" in totems
    assert "totem_cast_failed:" in totems
    assert "totem:call_of_elements" in totems
    assert "TryResolveBotBlocker(state, bot, \"call_of_elements\")" in totems
    assert "TryEnsureCombatTotems(*state, bot, target)" in execute_profile


def test_stonecore_rotation_sql_declares_buffs_hunter_builder_and_aoe_gate():
    sql = read(STONECORE_ROTATION_SQL)

    for token in [
        "25780, 'buff', 'righteous_fury",
        "31801, 'buff', 'seal_of_truth",
        "20271, 'builder', 'judgement,threat,requires_seal'",
        "465, 'buff', 'devotion_aura",
        "20217, 'buff', 'blessing_of_kings",
        "13165, 'buff', 'aspect_of_the_hawk",
        "883, 'buff', 'call_pet",
        "34477, 'buff', 'misdirection",
        "56641, 'builder', 'steady_shot,focus_builder",
    ]:
        assert token in sql

    assert "77767, 'builder'" not in sql
    assert "2120, 'aoe', 'flamestrike,aoe', 0.90, 0, 3, 4" in sql
    assert "'judgement,threat,requires_seal', 0.68, 0, 0.55, 0, 0, 4, 1, 0, 1, 1, 31801" in sql


def test_action_profile_hard_masks_enforce_aura_prerequisites():
    profile = read(PLAYER_BOT_ACTION_PROFILE)

    assert 'spell.RequiredSelfAura && !bot->HasAura(spell.RequiredSelfAura)' in profile
    assert 'spell.ForbiddenSelfAura && bot->HasAura(spell.ForbiddenSelfAura)' in profile
    assert 'spell.RequiredTargetAura && actionTarget && !actionTarget->HasAura(spell.RequiredTargetAura)' in profile
    assert 'spell.ForbiddenTargetAura && actionTarget && actionTarget->HasAura(spell.ForbiddenTargetAura)' in profile
    assert 'candidate.RejectReason = "missing_required_self_aura"' in profile


def test_server_start_autonomy_enabled_spawns_from_pool_without_center_requirement():
    mgr = read(BOT_MGR)
    start_autonomy = function_body(mgr, "bool BotWorldPopulationMgr::StartAutonomy")
    shutdown = function_body(mgr, "void BotWorldPopulationMgr::Shutdown")
    update = function_body(mgr, "void BotWorldPopulationMgr::Update")
    ensure_population = function_body(mgr, "void BotWorldPopulationMgr::EnsurePopulation")
    select_candidate = function_body(mgr, "uint32 BotWorldPopulationMgr::SelectPoolCandidateGuid() const")
    resolve_placement = function_body(mgr, "bool BotWorldPopulationMgr::ResolveSpawnPlacement")

    assert 'LoadConfig("always_on_autonomy", overrideConfig);' in start_autonomy
    assert "if (_runtimeMode == BotWorldRuntimeMode::AlwaysOnAutonomy && !overrideConfig && !_runtimeProfileDirty)" in start_autonomy
    assert "return true;" in start_autonomy
    assert "_runtimeMode = BotWorldRuntimeMode::AlwaysOnAutonomy;" in start_autonomy
    assert "_runId = 0;" in start_autonomy
    assert "_experimentId = 0;" in start_autonomy
    assert_ordered(start_autonomy, "_active = true;", "EnsurePopulation();", "return _active;")
    assert "RecordRunStop();" in shutdown
    assert "UPDATE character_bot_pool SET in_use = 0 WHERE guid" in shutdown
    assert "RemoveWorldBot" not in shutdown
    assert "PersistBotPosition" not in shutdown
    assert "spawned_bot_not_loaded" in update
    assert "UPDATE character_bot_pool SET in_use = 0 WHERE guid" in update
    assert "TryReattachValidationBot(*itr, loadedBot, \"population_update_loaded_not_in_world\")" in update
    assert "validation_same_instance_reattach_failed" in update
    assert "validation_artificial_reattach_blocked" not in mgr
    assert "session->HandleMoveWorldportAck();" in function_body(mgr, "bool BotWorldPopulationMgr::TryReattachValidationBot")
    assert "validationBotStillDeciding" in update
    assert "nowMs - itr->LastDecisionTickMs < 15000" in update
    assert "_config.ValidationRouteEnable && itr->SpawnedMs && nowMs - itr->SpawnedMs >= 30000" in update
    assert "BotWorld active bot respawn requested" in update
    assert "_failedSpawnGuids.erase(prunedGuid.GetCounter())" in update
    assert "_validationRouteActivationApplied = false" in update

    assert "uint32 candidateGuid = SelectPoolCandidateGuid();" in ensure_population
    assert 'sBotMgr->SpawnWorldBotAtSavedPosition("any", std::to_string(candidateGuid))' in ensure_population
    assert 'sBotMgr->SpawnWorldBot("any", std::to_string(candidateGuid)' in ensure_population
    assert 'RecordEvent(_bots.back(), bot, "bot_spawned"' in ensure_population
    assert "_config.PoolTagFilter" in select_candidate
    assert "cbp.experiment_tags LIKE" in select_candidate
    assert_ordered(
        resolve_placement,
        "ResolveSavedSpawnPlacement(candidateGuid, placement)",
        "ResolveRaceStartSpawnPlacement(candidateGuid, placement)",
        "ResolveNearPlayerSpawnPlacement(placement)",
        "ResolveConfiguredCenterSpawnPlacement(placement)",
    )
    assert "_config.UseSavedPosition" in resolve_placement
    assert "_config.AllowConfiguredCenterFallback" in resolve_placement
    assert "resume_or_race_start" in resolve_placement
    assert "race_start_only" in resolve_placement


def test_stonecore_bot_instance_bind_does_not_wait_for_client_lock_prompt():
    map_cpp = read(MAP_CPP)
    add_player = function_body(map_cpp, "bool InstanceMap::AddPlayerToMap")

    assert '#include "WorldSession.h"' in map_cpp
    assert "player->GetSession()->IsBotSession()" in add_player
    assert "player->BindToInstance(mapSave, true, EXTEND_STATE_KEEP);" in add_player
    assert_ordered(
        add_player,
        "if (groupBind->perm)",
        "player->GetSession()->IsBotSession()",
        "player->BindToInstance(mapSave, true, EXTEND_STATE_KEEP);",
        "WorldPackets::Instance::PendingRaidLock pendingRaidLock;",
        "player->SetPendingBind(mapSave->GetInstanceId(), 60000);",
    )


def test_validation_bot_reattach_clears_stale_far_teleport():
    mgr = read(BOT_MGR)
    reattach = function_body(mgr, "bool BotWorldPopulationMgr::TryReattachValidationBot")
    update = function_body(mgr, "void BotWorldPopulationMgr::Update")

    assert "validation_artificial_reattach_blocked" not in mgr
    assert "bot->IsBeingTeleportedFar()" in reattach
    assert "destination.GetMapId() == state.ValidationCohortMapId" in reattach
    assert "!destinationInstance || *destinationInstance == state.ValidationCohortInstanceId" in reattach
    assert "session->HandleMoveWorldportAck();" in reattach
    assert "validation same-instance worldport complete" in reattach
    assert "bot->CancelDelayedTeleport();" in reattach
    assert "bot->SetSemaphoreTeleportFar(false);" in reattach
    assert "bot->GetMap()->AddPlayerToMap(bot)" in reattach
    assert "validation_same_instance_reattach_failed" in update


def test_bot_dungeon_summon_rejects_cross_map_detach():
    player_cpp = read(PLAYER_CPP)
    summon = function_body(player_cpp, "void Player::SummonIfPossible")

    assert re.search(
        r"bool Player::TeleportTo\(uint32.*?GetSession\(\)->IsBotSession\(\).*?GetMap\(\)->IsDungeon\(\).*?mapid != GetMapId\(\).*?return false;.*?DisableMgr::IsDisabledFor",
        player_cpp,
        re.DOTALL,
    )
    assert "GetSession()->IsBotSession()" in summon
    assert "GetMap()->IsDungeon()" in summon
    assert "m_summon_location.GetMapId() != GetMapId()" in summon
    assert_ordered(
        summon,
        "m_summon_location.GetMapId() != GetMapId()",
        "m_summon_expire = 0;",
        "return;",
        "TeleportTo(m_summon_location, TELE_TO_NONE, m_summon_instanceId);",
    )


def test_telemetry_policy_smoke_samples_normal_wander_and_keeps_critical_events():
    policy = read(BOT_POLICY)

    assert 'situation == "wander"' in function_body(policy, "bool IsSampleEvent")
    assert "return (sequence % rate) == 0;" in function_body(policy, "bool Sample")
    assert "? config.normalDecisionSampleRate : config.normalEventSampleRate" in policy
    assert "result.writeDecision = sampled;" in policy
    assert "result.writeEvent = sampled;" in policy
    assert "result.importance = BotTelemetryImportance::Drop;" in policy
    assert 'result.reason = "sampled_out";' in policy

    for event_type in ["death", "stuck_detected", "objective_failed"]:
        assert event_type in function_body(policy, "bool IsReplayEvent")
        assert event_type in function_body(policy, "bool IsKeepEvent")

    assert "failure && config.alwaysRecordFailures" in policy
    assert "input.intervention && config.alwaysRecordInterventions" in policy
    assert "input.rare && config.alwaysRecordRareStates" in policy


def test_bot_spawn_lifecycle_dummy_and_ability_objective_surface():
    mgr_header = read(ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h")
    mgr = read(BOT_MGR)
    commands = read(BOT_COMMANDS)
    conf = read(WORLDSERVER_CONF)

    for symbol in [
        "ResolveRaceStartSpawnPlacement",
        "IsValidBotResumePosition",
        "PersistBotPosition",
        "RecordSpawnResolved",
        "IsTrainingDummy",
        "SelectQuestAbilityObjectiveTarget",
        "StopDisallowedDummyCombat",
        "GetBotDebugJson",
    ]:
        assert symbol in mgr_header

    resolve = function_body(mgr, "bool BotWorldPopulationMgr::ResolveSpawnPlacement")
    assert "resume_or_race_start" in resolve
    assert "resume_only" in resolve
    assert "race_start_only" in resolve
    assert "saved_or_near_player" in resolve

    assert "spawn_resolved" in function_body(mgr, "void BotWorldPopulationMgr::RecordSpawnResolved")
    assert "spawn_resume_invalid" in function_body(mgr, "bool BotWorldPopulationMgr::ResolveSavedSpawnPlacement")
    assert "race_start" in function_body(mgr, "bool BotWorldPopulationMgr::ResolveRaceStartSpawnPlacement")
    assert "dummy_target_rejected" in function_body(mgr, "bool BotWorldPopulationMgr::StopDisallowedDummyCombat")

    questing = function_body(mgr, "BotWorldPopulationMgr::QuestActionResult BotWorldPopulationMgr::TryQuesting")
    assert "UseAbilityOnDummy" in questing
    assert "LastQuestProgressBefore" in questing
    assert "LastQuestProgressAfter" in questing
    assert "ability_objective_failed" in questing
    assert "blacklist_target_spell_pair" in questing

    select_safe = function_body(mgr, "Unit* BotWorldPopulationMgr::SelectSafeTarget")
    assert "IsTrainingDummy(target)" in select_safe

    assert '{ "debug",   rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "GetBotDebugJson" in commands
    assert "BotWorld.TrainingDummyEntries = \"\"" in conf
    assert "BotWorld.TeacherQuestKillAssist = 1" in conf


def test_quest_first_portfolio_routing_surface():
    mgr_header = read(ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h")
    mgr = read(BOT_MGR)
    classify = function_body(mgr, "BotWorldPopulationMgr::QuestClassification BotWorldPopulationMgr::ClassifyQuestForBot")
    pickup_search = function_body(mgr, "bool BotWorldPopulationMgr::FindQuestPickupDestination")
    portfolio = function_body(mgr, "BotWorldPopulationMgr::QuestPortfolioPlan BotWorldPopulationMgr::BuildQuestPortfolioPlan")
    questing = function_body(mgr, "BotWorldPopulationMgr::QuestActionResult BotWorldPopulationMgr::TryQuesting")
    supported = function_body(mgr, "bool BotWorldPopulationMgr::HasSimpleSupportedObjective")
    select_objective = function_body(mgr, "Unit* BotWorldPopulationMgr::SelectQuestObjectiveTarget")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::ResolveObjectiveRoutePoint")
    debug = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotDebugJson")
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")

    for symbol in [
        "QuestClassification",
        "QuestRoutePoint",
        "QuestObjectiveBucket",
        "QuestPortfolioPlan",
        "QuestSearchRadiusIndex",
        "QuestSearchDestination",
        "ActiveQuestClusterId",
        "QuestRouteDestination",
        "LastNoQuestReason",
        "LastQuestBucketReason",
        "_validationRouteFocusGuid",
        "_validationRouteFocusEntry",
        "_validationRouteFocusSeenMs",
        "ValidationRouteAlternateTargetEntries",
    ]:
        assert symbol in mgr_header

    assert "HasSimpleSupportedObjective(quest)" in classify
    assert "GetNextQuestInChain()" in classify
    assert "GetNextQuestId()" in classify
    assert "GetBreadcrumbForQuestId()" in classify
    assert "creature_questender" in classify
    assert "gameobject_questender" in classify
    assert "quest->IsSeasonal()" in supported
    assert "QUEST_SPECIAL_FLAGS_KILL" in supported
    assert "UNIT_FLAG_NON_ATTACKABLE" in supported
    assert "ContainsInsensitive(tmpl->Name, \"DND\")" in supported
    assert "IsSimpleOpenWorldQuestMobAssistTarget" in mgr
    assert "objectiveType == BotWorldPopulationMgr::QuestObjectiveType::CollectItem" in mgr
    assert "creature->isElite()" in mgr
    assert "bot->GetMap()->IsDungeon() || bot->GetMap()->IsRaid()" in mgr
    validation_route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    assert "auto isValidationRouteEntry" in validation_route_objective
    assert "_config.ValidationRouteAlternateTargetEntries.begin()" in validation_route_objective
    assert "isValidationRouteScriptTarget(creature)" in validation_route_objective
    script_target_block = validation_route_objective.split("auto isValidationRouteScriptTarget", 1)[1].split("auto isValidationRouteCombatTarget", 1)[0]
    assert 'if (_config.ValidationRouteKind == "boss")' in script_target_block
    assert "isValidationRoutePackEntry(creature->GetEntry())" in script_target_block
    assert "creature->GetExactDist(_config.ValidationRouteX, _config.ValidationRouteY, _config.ValidationRouteZ) <= radius" in script_target_block

    assert "creature_loot_template" in select_objective
    assert "creature_loot_template" in route_objective
    assert "gameobject_loot_template" in route_objective
    assert "creature_loot_spawn" in route_objective
    assert "gameobject_loot_spawn" in route_objective
    assert_ordered(route_objective, "creature_loot_spawn", "quest_poi")

    assert "{ 100.0f, 250.0f, 500.0f, 900.0f, 1500.0f }" in pickup_search
    assert "creature_queststarter" in pickup_search
    assert "gameobject_queststarter" in pickup_search
    assert "ClassifyQuestForBot(bot, quest)" in pickup_search

    assert "constexpr float ClusterRadius = 180.0f;" in portfolio
    assert "ResolveObjectiveRoutePoint(bot, objective, route)" in portfolio
    assert "bucket->Objectives.push_back(objective)" in portfolio

    for event_type in [
        "quest_hub_sweep",
        "quest_pickup_search",
        "quest_bucket_selected",
        "objective_area_selected",
        "chain_step_accepted",
        "chain_step_turnin",
        "complete_quest_db_fallback",
        "target_not_visible_travel_to_spawn",
    ]:
        assert event_type in questing

    assert_ordered(
        questing,
        "bot->CanCompleteQuest(state.QuestWork.ActiveQuestId)",
        "completed_counter_reconciled",
        "_metrics.Kills += delta;",
        "RecordEvent(state, bot, \"mob_killed\", completedTarget, \"quest_counter_reconciled\"",
        "SetQuestWorkPhase(state, \"move_to_turnin\");",
    )
    assert_ordered(
        update_bot,
        "uint32 progressBefore = state.LastQuestProgressBefore ? state.LastQuestProgressBefore : state.QuestWork.ProgressBefore;",
        "BotActionExecutor::LootResult loot = executor.AutoLoot(bot, target);",
        "VerifyQuestObjectiveProgress(state, bot, lootPlan, target, progressBefore, \"kill_or_loot_verified\"",
    )

    assert_ordered(
        questing,
        "ObjectAccessor::GetUnit(*bot, state.QuestWork.SelectedTargetGuid)",
        "selectedMatchesPlan",
        "VerifyQuestObjectiveProgress(state, bot, plan, selectedTarget, before, \"engaged_target_lost\"",
        "RecordQuestEvent(state, bot, \"objective_target_lost\"",
        "if (!objectiveTarget)",
        "objectiveTarget = SelectQuestObjectiveTarget(bot, plan);",
        "state.QuestWork.SelectedTargetGuid = objectiveTarget->GetGUID();",
        "state.TargetGuid = objectiveTarget->GetGUID();",
        "BotClassSpecActionProfileStore::Build(bot, role.c_str())",
        "result.Action = \"move_to_quest_mob\";",
        "BotActionResult pull = executor.Pull(bot, objectiveTarget);",
        "teacher_quest_mob_assist",
        "RecordEvent(state, bot, \"teacher_kill_assist\"",
        "Unit::DealDamage(bot, objectiveTarget, objectiveTarget->GetHealth(), 0, DIRECT_DAMAGE, SPELL_SCHOOL_MASK_NORMAL, nullptr, false);",
    )

    assert "TrySmartGearDecision(state, bot, power, stage, chosenActivity.Activity, situation, action)" in update_bot
    assert "TryValidationRouteObjective(state, bot, power, stage, chosenActivity.Activity, situation, action, target)" in update_bot
    assert "validation_route_prerequisite" in mgr
    assert "off_route_target" in mgr
    assert "routeEngageRange" in mgr
    assert "approach_target" in mgr
    assert "tryRouteGroupHeal" in mgr
    assert "validation_route_group_heal" in mgr
    assert "float maxApproachRange = _config.ValidationRouteEnable && healer->GetMap() && healer->GetMap()->IsRaid() ? 35.0f : 18.0f;" in mgr
    assert "float approachRange = std::max(3.0f, std::min(healRange - 2.0f, maxApproachRange));" in mgr
    assert "healBlockedByCastState = true;" in mgr
    assert "heal_cast_state_pending" in mgr
    assert "validation_route_group_heal_pending" in mgr
    assert "buildRouteHealRaw" in mgr
    assert '\\"selected_heal_spell_id\\"' in mgr
    assert '\\"heal_target_guid\\"' in mgr
    assert '\\"heal_target_health_pct\\"' in mgr
    assert '\\"cast_failure_reason\\"' in mgr
    assert "bool cast = TryCastFriendlySpell(healer, healTarget, bestHeal->SpellId, &castFailureReason);" in mgr
    assert 'RecordEvent(state, healer, "validation_route_group_heal", healTarget, cast ? "ok" : castFailureReason.c_str(), raw.c_str(), semantic.c_str(), healTargetHealthPct, 0, bestHeal->SpellId);' in mgr
    assert "action = cast ? \"validation_route_group_heal\" : \"validation_route_group_heal_failed\";" in mgr
    assert "return cast;" in mgr
    assert "return fail(\"line_of_sight\");" in mgr
    assert "return fail(\"global_cooldown\");" in mgr
    assert "if (spellInfo->CalcCastTime(bot->getLevel()) > 0)" in mgr
    assert "bot->StopMoving();" in mgr
    assert "bot->GetMotionMaster()->MoveIdle();" in mgr
    assert "*failureReason = \"spell_cast_result_\" + std::to_string(uint32(castResult));" in mgr
    assert_ordered(
        validation_route_objective,
        "target = routeTarget;",
        "state.TargetGuid = target->GetGUID();",
        "rememberValidationRouteFocus(target);",
        "if (tryRouteGroupHeal(bot, target))",
        "if (_config.ValidationRouteKind == \"boss\" && tryValidationRouteInterrupt(target, \"route_target_interrupt\"))",
        "ResolvedCombatAction profileAction = ResolveProfileCombatAction(bot, target);",
    )
    assert "requires_ally_target" in mgr
    assert "threat_already_established" in mgr
    assert "routeGroupFocusTarget" in mgr
    assert "bestFocus" in mgr
    assert "voter->GetVictim() == focus" in mgr
    assert 'std::string(GetDungeonRole(member)) == "tank"' in mgr
    assert "auto activeTankFocus" in mgr
    assert "auto tankOwnsFocus" in validation_route_objective
    assert 'if (_config.ValidationRouteKind != "boss" && !tankOwnsFocus(member, focus))' in validation_route_objective
    assert 'if (_config.ValidationRouteKind == "boss" || activeTankFocus(focus))\n                    return focus;' in validation_route_objective
    assert "if (!ownedByTank)" in validation_route_objective
    assert "routeFocusTankOwned" in validation_route_objective
    assert "wait_for_tank_threat" in validation_route_objective
    assert 'if (routeBossTarget && _config.ValidationRouteKind != "boss" && !botIsTank && !routeFocusTankOwned(target))' in validation_route_objective
    assert '"tank_positioning", target, "route_trash_tank_focus"' in validation_route_objective
    rotation_profiles_sql = read(ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql")
    assert "blood_presence,self,tank_stance,mitigation" in rotation_profiles_sql
    assert "death_strike,self_heal,melee,threat" in rotation_profiles_sql
    assert 'if (_config.ValidationRouteKind == "boss" || activeTankFocus(focus))' in mgr
    assert 'if (_config.ValidationRouteKind != "boss" && !memberIsTank)' in mgr
    assert "move_to_validation_route_assist_target" in mgr
    assert "validation_route_prerequisite_assist" in mgr
    assert "assist_focus" in mgr
    assert 'bool routeTrashFocus = _config.ValidationRouteKind != "boss";' in validation_route_objective
    assert 'action = routeTrashFocus ? "validation_route_trash_action" : "validation_route_prerequisite_assist";' in validation_route_objective
    assert 'RecordEvent(state, bot, routeTrashFocus ? "trash_action" : "validation_route_prerequisite"' in validation_route_objective
    assert "for (WorldBotState const& cohortState : _bots)" in mgr
    assert "findCohortAnchor" in function_body(mgr, "Player* BotWorldPopulationMgr::FindDungeonAnchor")
    assert "for (WorldBotState const& state : _bots)" in function_body(mgr, "Player* BotWorldPopulationMgr::FindDungeonAnchor")
    assert "std::string(GetDungeonRole(member)) != \"tank\"" in mgr
    assert "cohort_threat_established" in mgr
    assert "validation_route_regroup" in mgr
    assert "regroup_anchor_no_focus" in mgr
    assert "move_to_validation_route_anchor" in mgr
    assert "hold_anchor_no_focus" in mgr
    assert "validation_route_hold_anchor" in mgr
    assert "follow_anchor_before_prerequisite" in mgr
    assert "hold_anchor_before_prerequisite" in mgr
    assert 'if (_config.ValidationRouteKind == "boss" && std::string(GetDungeonRole(bot)) != "tank")' in validation_route_objective
    assert (
        'if (_config.ValidationRouteKind == "boss")\n'
        '                {\n'
        '                    RecordEvent(state, bot, "validation_route_regroup", anchor, "hold_anchor_before_prerequisite"'
    ) in validation_route_objective
    assert "routeTankFocusGuid" in mgr
    assert "routeTankFocusTarget" in mgr
    assert "rememberValidationRouteFocus" in mgr
    assert "clearValidationRouteKilledFocus" in mgr
    assert "cohortState.ValidationRouteCombatProgressTargetGuid.Clear();" in mgr
    assert "cohortState.ValidationRoutePackProgressTargetGuid.Clear();" in mgr
    assert "cohortState.ValidationRouteAnchorOverrideValid = false;" in mgr
    assert "cohortState.RecentDeathCount = 0;" in mgr
    assert "auto recordValidationRouteTrashKill" in validation_route_objective
    assert "if (!killedTarget || killedTarget->IsAlive() || killedTarget->GetHealth())" in validation_route_objective
    assert "clearValidationRouteKilledFocus(killedTarget->GetGUID());" in mgr
    assert 'RecordEvent(state, bot, "mob_killed", killedTarget' in validation_route_objective
    assert 'if (!creature->IsAlive() || !creature->GetHealth())' in validation_route_objective
    assert 'recordValidationRouteTrashKill(seenRouteTarget, "target_seen_dead")' in validation_route_objective
    assert "activeCohortFocus" in mgr
    assert "member->IsInCombat() || focus->IsInCombat() || focus->GetVictim()" in mgr
    assert "authoritative_focus_state_target_inactive" in mgr
    assert "routeUsableCombatTarget(member->GetVictim())" in mgr
    assert "if (Unit* victim = routeUsableCombatTarget(member->GetVictim()))" in mgr
    assert "routeUsableCombatTarget(ObjectAccessor::GetUnit(*member, cohortState.TargetGuid))" in mgr
    assert "Player* loadedBot = GetLoadedBot(*itr)" in mgr
    assert "loaded_bot_not_in_world" in mgr
    assert "return bot && bot->IsInWorld() ? bot : nullptr;" in function_body(mgr, "Player* BotWorldPopulationMgr::GetBot")
    assert "member->GetVictim()" in mgr
    assert "force_tank_focus" in mgr
    assert "force_last_known_tank_focus" in mgr
    assert "findLastKnownFocusTarget" in mgr
    assert "return nullptr;" in function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    assert "creature->GetEntry() != _validationRouteFocusEntry" in mgr
    assert "auto routeFocusMemoryFresh" in validation_route_objective
    assert "routeFocusMemoryFresh()" in validation_route_objective
    assert "ObjectAccessor::GetUnit(*bot, _validationRouteFocusGuid)" in validation_route_objective
    assert "auto authoritativeRouteFocusActive" in validation_route_objective
    assert "return routeFocusMemoryActive();" in validation_route_objective
    assert "if (_config.ValidationRouteKind != \"boss\")\n                continue;" in validation_route_objective
    assert 'return _config.ValidationRouteKind == "boss" ? nearestMatchingEntry : nullptr;' in validation_route_objective
    assert 'if (_config.ValidationRouteKind != "boss" && !_validationRouteFocusGuid.IsEmpty())' in validation_route_objective
    assert "Unit* rememberedFocus = findLastKnownFocusTarget();" in validation_route_objective
    assert "rememberedFocus = findTrashClusterThreatTarget();" in validation_route_objective
    assert "reject_non_authoritative_focus" in mgr
    assert "follow_anchor_non_authoritative_focus" in mgr
    assert "follow_last_known_tank_focus" in mgr
    assert "hold_last_known_tank_focus" in mgr
    assert "follow_anchor_last_known_tank_focus" in mgr
    assert "validation_route_hold_focus" in mgr
    assert "ValidationRouteUnresolvedFocusHoldCount" in mgr_header
    assert "ValidationRouteCombatNoProgressCount" in mgr_header
    assert "ValidationRouteBossSlowProgressCount" in mgr_header
    assert "_validationRouteBossProgressTargetGuid" in mgr_header
    assert "_validationRouteBossSlowProgressCount" in mgr_header
    assert "bool mechanicProfileRequiresMovement = _config.ValidationRouteMechanicProfile.find(\"movement_check\") != std::string::npos" in validation_route_objective
    assert "bool profileAllowsCastMovement = mechanicProfileRequiresMovement" in validation_route_objective
    assert "&& _config.ValidationRouteMechanicProfile.find(\"movement_check\") != std::string::npos" in validation_route_objective
    assert "&& _config.ValidationRouteMechanicProfile.find(\"ground_danger\") == std::string::npos;" in validation_route_objective
    assert "if (!SpellLooksLikeGroundDanger(castSpell) && !profileAllowsCastMovement)" in validation_route_objective
    assert "for (auto const& [_, application] : bot->GetAppliedAuras())" in validation_route_objective
    assert "effect.Effect == SPELL_EFFECT_PERSISTENT_AREA_AURA" in validation_route_objective
    assert "effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE" in validation_route_objective
    assert "effect.ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE_PERCENT" in validation_route_objective
    assert "if (!persistentPeriodicDamage)" in validation_route_objective
    assert "movementOrigin = aura->GetOwner();" in validation_route_objective
    assert "(movementOrigin ? movementOrigin : caster)->GetAngle(bot)" in validation_route_objective
    assert 'ValidationRouteMechanicProfile.find("adds")' in validation_route_objective
    assert "ValidationRouteAddTargetEntries.empty()" in validation_route_objective
    assert "creature->IsInCombat() || creature->GetVictim()" in validation_route_objective
    assert "ValidationRouteAddTargetEntries.end(), creature->GetEntry()" in validation_route_objective
    assert "BuildBossMechanicFeatures(bot, bossTarget)" not in validation_route_objective
    assert "BotActionResult pull = executor.Pull(bot, add);" in validation_route_objective
    assert "if (result == BotActionResult::NoAction)\n                result = pull;" in validation_route_objective
    assert 'priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 2 : 1);' in validation_route_objective
    assert "priority == bestPriority && healthPct < bestHealthPct" in validation_route_objective
    assert "healthPct == bestHealthPct && guid < bestGuid" in validation_route_objective
    assert "_validationRouteAddFocusGeneration == _validationRouteGeneration" in validation_route_objective
    assert "add = ObjectAccessor::GetUnit(*bot, _validationRouteAddFocusGuid);" in validation_route_objective
    assert "_validationRouteAddFocusGuid = add->GetGUID();" in validation_route_objective
    assert "if (!add)" in validation_route_objective
    assert 'action = "hold_boss_add_focus";' in validation_route_objective
    assert "if (!add->IsAlive() || !add->GetHealth())" in validation_route_objective
    assert 'RecordEvent(state, bot, "boss_add_killed", add, "observed_dead"' in validation_route_objective
    assert 'event == "boss_adds" || event == "boss_add_killed"' in mgr
    assert 'eventName == "boss_add_killed"' in mgr
    assert_ordered(
        validation_route_objective,
        "if (!add->IsAlive() || !add->GetHealth())",
        "_validationRouteAddFocusGuid.Clear();",
        "_validationRouteAddFocusGuid = add->GetGUID();",
    )
    assert 'RecordEvent(state, bot, "boss_adds", add' in validation_route_objective
    assert_ordered(
        validation_route_objective,
        "inspectCaster(preferredTarget);",
        "if (!caster && mechanicProfileRequiresMovement)",
        "if (!caster)\n        {",
        "Position dodge = bot->GetFirstCollisionPosition(8.0f, angle);",
        "if (tryValidationRouteMovementCheck(target))",
        "if (tryValidationRouteAdds())",
        "if (tryRouteGroupHeal(bot, target))",
    )
    assert "bot->GetFirstCollisionPosition(8.0f, angle)" in validation_route_objective
    assert "MoveBotToPoint(state, bot, dodge.GetPositionX(), dodge.GetPositionY(), dodge.GetPositionZ())" in validation_route_objective
    assert "routeHasActiveCombatIntent" in mgr
    assert "state.ValidationRouteAnchorOverrideValid && routeHasActiveCombatIntent" in mgr
    assert "else if (!routeHasActiveCombatIntent && repeatedDeathNearRoute)" in mgr
    assert '_config.ValidationRouteKind == "boss" ? 60000 : 20000' in mgr
    assert "stale_focus_expired" in mgr
    assert "validation_route_recover_stale_focus" in mgr
    assert "findAuthoritativeRouteFocusTarget" in mgr
    assert "teacherAssistAuthoritativeFocus" in validation_route_objective
    assert "assist_unresolved_authoritative_focus" in mgr
    assert "assist_target_search_authoritative_focus" in mgr
    assert "authoritative_focus_guid_not_resolved" in mgr
    assert "authoritative_focus_reference_rejected" in mgr
    assert "authoritative_focus_no_same_map_cohort" in mgr
    assert "unresolved_authoritative_focus_unavailable" in mgr
    assert "validation_route_recover_unresolved_focus" in mgr
    assert "validation_route_teacher_assist" not in validation_route_objective
    assert "validation_route_prerequisite_no_progress" in mgr
    assert "boss_route_no_health_progress" in mgr
    assert "boss_route_slow_progress_teacher_assist" not in validation_route_objective
    assert "_validationRouteBossSlowProgressCount = 0;" in mgr
    assert "++_validationRouteBossSlowProgressCount;" in validation_route_objective
    assert "++state.ValidationRouteBossSlowProgressCount;" in validation_route_objective
    assert_ordered(
        validation_route_objective,
        'RecordEvent(state, bot, routeBossTarget ? (_config.ValidationRouteKind == "boss" ? "boss_action" : "trash_action") : "validation_route_prerequisite"',
        'if (!routeBossTarget)\n            maybeValidationPrerequisiteNoProgressAssist(target, "current_combat_no_health_progress");',
        'if (routeBossTarget && _config.ValidationRouteKind == "boss")\n        {\n            RecordEvent(state, bot, "boss_started"',
        'maybeValidationPrerequisiteNoProgressAssist(target, "boss_route_no_health_progress");\n        }\n        state.WasInCombat = true;',
    )
    assert 'contextText.rfind("route_target_", 0) == 0' in mgr
    assert "recordValidationRouteBossKill" in mgr
    assert "isValidationRouteCombatEntry" in validation_route_objective
    assert "recordDefeatedValidationRouteTarget" in validation_route_objective
    assert 'recordDefeatedValidationRouteTarget(target, "stale_target_seen_dead")' in validation_route_objective
    assert 'recordDefeatedValidationRouteTarget(bot->GetVictim(), "stale_victim_seen_dead")' in validation_route_objective
    assert "if (!candidate || !candidate->IsAlive() || !candidate->GetHealth()" in validation_route_objective
    assert "makeExistingValidationRouteCombatReady" in validation_route_objective
    assert "target_ready_after_activation" in validation_route_objective
    assert "target_seen_activation_target" in validation_route_objective
    assert "boss_route_activation_no_visible_target_teacher_assist" not in validation_route_objective
    assert "validation_route_script_target_dead" in mgr
    assert "target_seen_not_attackable" in mgr
    assert "boss_killed" in mgr
    assert "raid_boss_killed" in mgr
    assert 'uint32 noProgressThreshold = bossRouteNoProgress ? 2 : (_config.ValidationRouteKind == "boss" ? 4 : 12)' in mgr
    assert "validation_route_activation" in mgr
    assert "boss_route_early_activation" in mgr
    assert "boss_route_no_focus_activation_already_applied" in mgr
    assert "boss_route_wait_for_tank_activation" in mgr
    assert "boss_route_no_focus_activation_unavailable" not in mgr
    assert "advance_to_boss_route_no_focus" not in mgr
    assert "hasValidationRouteActivation" in mgr
    assert "routeDistance <= 220.0f" not in validation_route_objective
    assert_ordered(
        validation_route_objective,
        "&& routeDistance <= routeArrivalRadius",
        "&& tryValidationRouteActivation(nullptr, \"boss_route_early_activation\"))",
        "Unit* preAnchorTrashTarget = nullptr;",
        "preAnchorTrashTarget = findTrashClusterThreatTarget();",
        "if (routeDistance > routeArrivalRadius && !preAnchorTrashTarget)",
    )
    assert "ValidationRouteActivationApplied" in mgr_header
    assert "ValidationRouteTargetSearchMissCount" in mgr_header
    assert "reset_stale_boss_activation" not in mgr
    assert "MarkBotBlocked(state, bot, \"boss_route_activation_no_visible_target\")" in mgr
    assert "_validationRouteActivationApplied" in mgr_header
    assert "_validationRouteActivationAttempts" in mgr_header
    assert "_validationRouteActivationApplied = false;" not in function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    assert "if (_validationRouteActivationApplied)" in mgr
    assert "state.ValidationRouteActivationAttempts = _validationRouteActivationAttempts;" in mgr
    assert "_validationRouteActivationApplied = true;" in mgr
    assert "activationTarget->IsAlive() && bot->IsValidAttackTarget(activationTarget)" in mgr
    assert "rememberValidationRouteFocus(activationTarget);" in mgr
    assert "state.TargetGuid = activationTarget->GetGUID();" in mgr
    assert "isValidationRouteScriptTarget(creature)" in mgr
    assert "validation_route_stuck_no_fallback" in mgr
    assert "ValidationRouteOpenerTargetEntry" in mgr_header
    assert "ValidationRouteOpenerSummonEntry" in mgr_header
    assert "ValidationRouteActivationSpawnGroupId" in mgr_header
    assert "ValidationRouteActivationActionEntry" in mgr_header
    assert "ValidationRouteActivationActionId" in mgr_header
    assert "fallback_disabled" in mgr
    assert "markValidationRouteTerminalAfterProgress" in mgr
    assert "RecordEvent(state, bot, \"dungeon_trash_cleared\"" in mgr
    assert "RecordDecision(state, bot, \"validation_route_recovery\", \"validation_route_stuck\"" in mgr
    assert "BotWorld.ValidationRoute.OpenerTargetEntry" in mgr
    assert "BotWorld.ValidationRoute.OpenerSummonEntry" in mgr
    assert "BotWorld.ValidationRoute.ActivationSpawnGroupId" in mgr
    assert "BotWorld.ValidationRoute.ActivationActionEntry" in mgr

    get_dungeon_role = function_body(mgr, "char const* BotWorldPopulationMgr::GetDungeonRole")
    assert_ordered(
        get_dungeon_role,
        "if (roles & lfg::PLAYER_ROLE_HEALER)",
        "std::string botRole = sBotMgr->GetBotRoleName(bot->GetGUID());",
        'CharacterDatabase.PQuery("SELECT role FROM character_bot_pool',
        "if (Group* group = bot->GetGroup())",
        "if (group->GetLfgRoles(bot->GetGUID()) & lfg::PLAYER_ROLE_DAMAGE)",
    )
    assert "BotWorld.ValidationRoute.ActivationActionId" in mgr
    assert "isValidationRouteScriptTarget" in mgr
    assert "candidateOpener && !currentOpener" in mgr
    assert "SpawnGroupSpawn(_config.ValidationRouteActivationSpawnGroupId" in mgr
    assert "creature->AI()->DoAction(_config.ValidationRouteActivationActionId)" in mgr
    assert "bot->SummonCreature(_config.ValidationRouteOpenerSummonEntry" in mgr
    assert "bot->SummonCreature(_config.ValidationRouteTargetEntry, targetPos" not in mgr
    assert "routeTargetActivationFallback" not in mgr
    assert 'if (_config.ValidationRouteKind == "boss" && std::string(GetDungeonRole(bot)) != "tank")' in mgr
    existing_activation = validation_route_objective.split("auto makeExistingValidationRouteCombatReady", 1)[1].split("auto tryValidationRouteActivation", 1)[0]
    assert "SetFaction" not in existing_activation
    assert "RemoveFlag" not in existing_activation
    assert "SetInCombatWith" not in existing_activation
    assert "AttackStart" not in existing_activation
    assert "float routeArrivalRadius =" in mgr
    assert 'float routeArrivalRadius = _config.ValidationRouteKind == "boss" ? 8.0f : 18.0f;' in validation_route_objective
    assert validation_route_objective.count("AttackStop") == 4
    assert validation_route_objective.count("CombatStop") == 4
    assert "ValidationRouteClusterRadiusYards > routeArrivalRadius" not in validation_route_objective
    assert "if (!preAnchorTrashTarget && (discoveryLeg || routeDistance <= routeArrivalRadius))" in validation_route_objective
    assert "_config.ValidationRouteActivationSpawnGroupId" in mgr
    assert "BotWorld.ValidationRoute.ActivationDataId" in mgr
    assert "BotWorld.ValidationRoute.ActivationSummonEntry" in mgr
    assert "activation_applied_no_visible_target" in mgr
    assert "InstanceScript* instance" in mgr
    assert "blocker_path_no_progress" in mgr
    assert "Unit::DealDamage(bot, prerequisiteTarget, damage" not in validation_route_objective
    assert "creature->IsInEvadeMode() || creature->HasUnitState(UNIT_STATE_EVADE)" in mgr
    assert "hasStrictPathToValidationRouteTarget(creature)" in mgr
    assert "isValidationRouteObjectiveTarget" in mgr
    assert 'return _config.ValidationRouteKind == "boss"' in mgr
    assert "isEligibleTrashClusterMob(creature)" in mgr
    assert "markValidationRouteTrashFailed" in mgr
    assert "validation_trash_no_progress" in mgr
    assert "validation_trash_requires_damage_progress" in mgr
    assert "lastCombatAttemptIsSchedulingWait" in mgr
    assert "lastCombatAttemptIsNormalCombatTick" in mgr
    assert "contextIsCombatProgressProbe" in mgr
    assert "lastCombatAttemptTargetsDifferentPackMob" in mgr
    assert 'if (std::string(GetDungeonRole(bot)) != "tank")\n                return false;' in mgr
    assert "isValidationRoutePackEntry(state.LastCombatAttempt.TargetEntry)" in mgr
    assert 'state.LastCombatAttempt.Result == "ok" || lastCombatAttemptIsSchedulingWait()' in mgr
    assert 'contextText.find("path_no_progress") != std::string::npos' in mgr
    assert 'state.LastCombatAttempt.Reason == "global_cooldown"' in mgr
    assert 'state.LastCombatAttempt.Result == "global_cooldown"' in mgr
    assert 'contextIsCombatProgressProbe() && lastCombatAttemptIsNormalCombatTick()' in mgr
    assert 'bot->GetMap() && bot->GetMap()->IsRaid() ? 2' not in mgr
    assert 'RecordCombatAttempt(*state, bot, target, "executor_check", &action, BotActionResult::Ok);' not in mgr
    assert "findTrashClusterThreatTarget" in mgr
    assert "validation_route_stuck_no_fallback" in mgr
    assert "fallback_disabled" in mgr
    assert "state.ValidationRouteAnchorOverrideValid && routeHasActiveCombatIntent && !repeatedDeathNearRoute" in validation_route_objective
    assert 'uint32 routeTargetNoProgressThreshold = _config.ValidationRouteKind == "boss" ? 5 : 20;' in mgr
    assert "_validationRouteFocusGuid.Clear();" in mgr
    assert "state.QuestWork.SelectedTargetGuid.Clear();" in mgr
    assert "regroup_tank_focus_mismatch" in mgr
    assert "follow_anchor_tank_focus_mismatch" in mgr
    assert "hold_anchor_tank_focus_mismatch" in mgr
    assert "nearestMatchingEntry" in mgr
    assert 'return _config.ValidationRouteKind == "boss" ? nearestMatchingEntry : nullptr;' in mgr
    assert "Player* member = GetBot(cohortState)" in function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    assert "SELECT role FROM character_bot_pool WHERE guid" in mgr
    assert 'poolRole.find("tank")' in mgr
    assert "if (routeProximity > 120.0f)" in mgr
    assert 'if (std::string(GetDungeonRole(bot)) != "tank"\n        && (_config.ValidationRouteKind != "boss" || routeDistance <= routeArrivalRadius))' in mgr
    assert_ordered(
        validation_route_objective,
        'if (std::string(GetDungeonRole(bot)) != "tank"\n        && (_config.ValidationRouteKind != "boss" || routeDistance <= routeArrivalRadius))',
        "Unit* preAnchorTrashTarget = nullptr;",
        "MoveBotToPoint(state, bot, routeAnchorX, routeAnchorY, routeAnchorZ);",
    )
    assert_ordered(
        function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective"),
        '&& !(_config.ValidationRouteKind == "boss" && _validationRouteActivationApplied)',
        "MoveBotToPoint(state, bot, anchor->GetPositionX(), anchor->GetPositionY(), anchor->GetPositionZ());",
        'RecordEvent(state, bot, "validation_route_regroup", anchor, "follow_anchor_no_focus"',
        "boss_route_wait_for_tank_activation",
        "action = \"validation_route_hold_anchor\";",
        "RecordEvent(state, bot, \"validation_route_regroup\", anchor, \"hold_anchor_no_focus\"",
    )
    assert_ordered(
        function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective"),
        "target = routeTarget;",
        "float engageRange = routeEngageRange(bot, target, spellId);",
        "action = \"move_to_validation_route_target\";",
        "RecordEvent(state, bot, \"validation_route_target_search\", target, \"approach_target\"",
        "BotActionResult pull = executor.Pull(bot, target);",
        "RecordEvent(state, bot, _config.ValidationRouteKind == \"boss\" ? \"boss_action\"",
    )
    assert 'eventName.rfind("validation_route", 0) == 0' in mgr
    assert "state.LastDecisionHandler = \"smart_loot\";" in update_bot
    assert_ordered(
        mgr,
        "if (!routeTarget && seenRouteTarget)",
        "RecordEvent(state, bot, \"validation_route_prerequisite\"",
        "action = \"validation_route_target_blocked\";",
    )
    assert_ordered(
        update_bot,
        "bool hasNearbyQuestGiver = _config.AllowQuesting && HasNearbySupportedQuestGiver(bot, state);",
        "bool canInterleaveHubProfession = !bot->IsInCombat()",
        "TryValidationRouteObjective(state, bot, power, stage, chosenActivity.Activity, situation, action, target)",
        "else if (canInterleaveHubProfession && TryProfessionMemoryAction(state, bot, power, stage, chosenActivity.Activity, situation, action))",
        "&& !(target && !target->IsAlive())",
        "&& (chosenActivity.Activity == BotProgressionActivity::Questing || hasActiveQuestObjective || _config.QuestFirst || state.NewlyAcceptedQuestId || hasNearbyQuestGiver)",
        "TryQuesting(state, bot, power, stage, chosenActivity.Activity)",
        "TrySmartGearDecision(state, bot, power, stage, chosenActivity.Activity, situation, action)",
        "TryProfessionMemoryAction(state, bot, power, stage, chosenActivity.Activity, situation, action)",
        "else if (!bot->IsInCombat() && chosenActivity.Activity == BotProgressionActivity::VendorRepairTrain)",
    )
    assert "BotGearUpgradeEvaluation evaluation = BotLongTermProgressionBrain::EvaluateGearUpgrade(bot);" in mgr
    assert "lootDecision = evaluation.Upgrade ? \"need_upgrade\" : (evaluation.CanEquip || hasValue ? \"greed_value\" : \"pass_invalid\")" in mgr
    assert "bot->EquipItem(equipDest, item, true);" in mgr
    assert "RecordEvent(state, bot, \"smart_loot_decision\"" in mgr
    assert "RecordGearEvaluation(state, bot, evaluation" in mgr
    assert "std::string(eventType) == \"smart_loot_decision\"" in mgr
    assert "EvaluateGearTemplate(Player const* bot, ItemTemplate const* proto" in read(ROOT / "src/server/game/Bots/BotLongTermProgressionBrain.h")
    progression = read(ROOT / "src/server/game/Bots/BotLongTermProgressionBrain.cpp")
    learning_policy = read(ROOT / "src/server/game/Bots/BotExperienceLearningPolicy.cpp")
    assert "BotLongTermProgressionBrain::EvaluateGearTemplate" in progression
    assert "score.LearnedScore = std::max(-30.0f, std::min(30.0f, learned.Score));" in progression
    assert "float avgReward = Clamp(stats.AvgReward, -25.0f, 25.0f);" in learning_policy
    assert "reward = Clamp(reward, -50.0f, 50.0f);" in learning_policy
    assert "FROM creature_loot_template clt INNER JOIN creature c ON c.id = clt.Entry" in mgr
    assert "FROM gameobject_loot_template glt INNER JOIN gameobject g ON g.id = glt.Entry" in mgr
    assert "smart_loot_candidates" in mgr
    assert "BotLongTermProgressionBrain::EvaluateGearTemplate(bot, proto)" in mgr
    assert "valid_action_mask" in mgr
    assert "RecordDecisionReplay(state, bot, nullptr, \"smart_loot_roll_policy\", lootDecision" in mgr
    assert "TryProfessionMemoryAction(state, bot, power, stage, chosenActivity.Activity, situation, action)" in update_bot
    assert "state.LastDecisionHandler = \"profession_memory\";" in update_bot
    assert "NextProfessionDecisionMs" in mgr_header
    assert "PreferMaterialMemoryAction" in mgr_header
    assert "SELECT source_type, source_entry, recipe_spell_id, item_id, map_id, zone_id, area_id, x, y, z FROM bot_memory_recipe_sources" in mgr
    assert "source\\\":\\\"world_recipe_source_index" in mgr
    assert "FROM creature_trainer ct INNER JOIN trainer_spell ts ON ts.TrainerId = ct.TrainerId INNER JOIN creature c ON c.id = ct.CreatureId" in mgr
    assert "FROM npc_vendor nv INNER JOIN creature c ON c.id = nv.entry" in mgr
    assert "recipe_candidates" in mgr
    assert "INSERT INTO bot_memory_recipe_sources" in mgr
    assert "RecordEvent(state, bot, \"profession_recipe_source\"" in mgr
    assert "PathGenerator path(bot);" in mgr
    assert "path.CalculatePath(x, y, z, false)" in mgr
    assert "PATHFIND_INCOMPLETE" in mgr
    assert "PATHFIND_SHORTCUT" in mgr
    assert "PATHFIND_FARFROMPOLY" in mgr
    assert "PATHFIND_NOT_USING_PATH" in mgr
    assert "route_destination_unreachable" in mgr
    assert "route_destination_partial_path" in mgr
    assert "route_destination_shortcut_path" in mgr
    assert "route_destination_off_mesh" in mgr
    assert "alternatePathScore" not in function_body(mgr, "bool BotWorldPopulationMgr::MoveBotToPoint")
    assert "state.PreferMaterialMemoryAction = true;" in mgr
    assert "state.NextProfessionDecisionMs = NowMs() + 3000;" in mgr
    assert "situation = \"profession_recipe_acquisition\";" in mgr
    assert "action = \"plan_trainer_recipe_source\";" in mgr
    assert "action = \"plan_vendor_recipe_source\";" in mgr
    assert "action = \"plan_profession_recipe_source\";" in mgr
    assert "SELECT source_type, source_entry, item_id, observed_count, map_id, x, y, z FROM bot_memory_material_sources" in mgr
    assert "source\\\":\\\"world_item_source_index" in mgr
    assert "FROM creature_loot_template clt INNER JOIN creature c ON c.id = clt.Entry" in mgr
    assert "FROM gameobject_loot_template glt INNER JOIN gameobject g ON g.id = glt.Entry" in mgr
    assert "ORDER BY ((x - %f) * (x - %f) + (y - %f) * (y - %f)) LIMIT 1" in mgr
    assert "INSERT INTO bot_memory_material_sources" in mgr
    assert "bool BotWorldPopulationMgr::MoveBotToPoint" in mgr
    move_bot_to_point = function_body(mgr, "bool BotWorldPopulationMgr::MoveBotToPoint")
    assert "return rejectPath(\"route_destination_recently_failed\");" in move_bot_to_point
    assert "recentFailureMemory && !_config.ValidationRouteEnable" in move_bot_to_point
    assert 'state.LastNoProgressReason = "route_destination_recently_failed_memory";' in move_bot_to_point
    assert "RecordEvent(state, bot, \"material_farming_source\"" in mgr
    assert "state.PreferMaterialMemoryAction = false;" in mgr
    assert "situation = \"material_farming\";" in mgr
    assert "action = \"plan_material_farming_source\";" in mgr
    assert_ordered(
        mgr,
        "if (state.PreferMaterialMemoryAction)",
        "if (emitMaterialSource())",
        "return emitRecipeSource();",
        "if (emitRecipeSource())",
        "if (emitMaterialSource())",
    )

    assert_ordered(
        questing,
        "SelectQuestGiver(bot, true, &questId, &state)",
        "turnin_counter_reconciled",
        "RecordEvent(state, bot, \"mob_killed\", nullptr, \"turnin_counter_reconciled\"",
        "bot->RewardQuest(quest, rewardChoice, turnIn, true);",
    )

    assert_ordered(
        questing,
        "SelectQuestGiver(bot, true, &questId, &state)",
        "FindQuestTurnInDestination(bot, questStatus.first, turnInRoute)",
        "quest_hub_sweep",
        "FindQuestObjective(bot, lastAcceptedQuestId, acceptedObjective)",
        "ResolveObjectiveRoutePoint(bot, acceptedObjective, route)",
        "MoveBotToPoint(state, bot, route.X, route.Y, route.Z);",
        "BuildQuestPortfolioPlan(bot, state)",
        "FindQuestPickupDestination(bot, state, pickup)",
    )
    assert "leave_unsupported_quest_giver" in questing
    assert 'state.LastObjectiveNotFoundReason != "chain_step_accepted"' in questing

    for field in [
        "active_quest_count",
        "quest_bucket_id",
        "quest_bucket_objective_count",
        "quest_bucket_center",
        "quest_search_radius",
        "quest_search_destination",
        "last_no_quest_reason",
        "last_quest_classification",
        "last_bucket_selection_reason",
    ]:
        assert field in debug


def test_move_bot_to_point_keeps_matching_active_motion():
    move_bot_to_point = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::MoveBotToPoint")
    assert "constexpr float activeDestinationEpsilon = 0.1f;" in move_bot_to_point
    assert_ordered(
        move_bot_to_point,
        "if (recentFailureMemory)",
        "if (state.ActivePathValid && state.IsMoving",
        "return true;",
        "state.ActivePathFromX = bot->GetPositionX();",
        "bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);",
        "bot->GetMotionMaster()->MovePoint(0, x, y, z, true);",
    )


def test_move_bot_to_profile_range_projects_approaches_to_terrain():
    profile_range = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::MoveBotToProfileRange")
    assert "auto moveToTerrainProjectedPoint = [&](float x, float y, float z)" in profile_range
    assert "Map* map = bot->GetMap();" in profile_range
    assert "map->GetHeight(bot->GetPhaseShift(), x, y, z + 2.0f, true, 64.0f)" in profile_range
    assert "if (floorZ == INVALID_HEIGHT)\n            return false;" in profile_range
    assert "return MoveBotToPoint(state, bot, x, y, floorZ);" in profile_range
    assert "return moveToTerrainProjectedPoint(reference->GetPositionX(), reference->GetPositionY(), reference->GetPositionZ());" in profile_range
    assert "return moveToTerrainProjectedPoint(rangedPosition.GetPositionX(), rangedPosition.GetPositionY(), rangedPosition.GetPositionZ());" in profile_range


def test_applied_ground_danger_spell_shape_contract():
    persistent_area_aura = 27
    periodic_damage = 3
    periodic_damage_percent = 89

    def should_dodge(is_positive: bool, effects: list[tuple[int, int]]) -> bool:
        return not is_positive and any(
            effect == persistent_area_aura and aura in {periodic_damage, periodic_damage_percent}
            for effect, aura in effects
        )

    dampening_wave_82415 = [(2, 0), (6, 301)]
    crystal_barrage_86881 = [(persistent_area_aura, periodic_damage), (3, 0)]
    assert not should_dodge(False, dampening_wave_82415)
    assert should_dodge(False, crystal_barrage_86881)
    assert all(should_dodge(False, crystal_barrage_86881) for _party_member in range(2))
    assert not should_dodge(True, crystal_barrage_86881)
    assert not should_dodge(False, [])


def test_botauto_diagnosis_and_trace_surface():
    mgr_header = read(ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h")
    mgr = read(BOT_MGR)
    commands = read(BOT_COMMANDS)
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    diagnose = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotDiagnosisJson")
    config_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildConfigJson")
    trace = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotTraceJson")
    build_diagnosis = function_body(mgr, "BotWorldPopulationMgr::BotDiagnosis BotWorldPopulationMgr::BuildBotDiagnosis")
    diagnosis_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")
    snapshot_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDecisionSnapshotJson")
    trace_entries = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotTraceEntriesJson")
    record_decision = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")
    record_event = function_body(mgr, "void BotWorldPopulationMgr::RecordEvent")
    update_outcome_stats = function_body(mgr, "void BotWorldPopulationMgr::UpdateSemanticOutcomeStats")
    record_trace = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionTrace")
    fingerprint = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionFingerprintMemory")
    debug = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotDebugJson")

    assert '{ "diagnose", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert '{ "trace",   rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "GetBotDiagnosisJson" in commands
    assert "GetBotTraceJson" in commands
    assert "combatOrCasting" in update_bot
    assert "bot->IsInCombat() || bot->HasUnitState(UNIT_STATE_CASTING)" in update_bot
    assert "bot->GetVictim() && bot->GetVictim()->IsAlive()" in update_bot
    assert_ordered(
        update_bot,
        "Unit* target = state.TargetGuid.IsEmpty()",
        "bool combatOrCasting",
        "if (!combatOrCasting && moving && moved < 0.2f)",
        "if (state.StuckTimer >= 6000)",
    )

    for symbol in [
        "LastDecisionTickMs",
        "LastDecisionSituation",
        "LastDecisionAction",
        "LastDecisionActivity",
        "LastDecisionTargetGuid",
        "LastDecisionHandler",
        "DistanceMovedSinceLastDecision",
        "LastMovementProgressMs",
        "LastPathChangeMs",
        "ConsecutiveSameDecisionCount",
        "IdleDecisionRepeatCount",
        "TargetChurnCount",
        "LoopRecoveryCooldownUntilMs",
        "LastLoopGuardrailAction",
        "LastRecoveryMode",
        "DecisionTraceEntry",
        "BotDiagnosis",
    ]:
        assert symbol in mgr_header

    assert "diagnosis_schema_version" in diagnose
    assert "BuildBotDecisionSnapshotJson(state, bot)" in diagnose
    assert "BuildBotDiagnosisObjectJson(state, bot)" in diagnose
    assert "trace_schema_version" in trace
    assert '\\"bots\\":[' in trace
    assert "BuildBotTraceEntriesJson(state, normalizedLimit)" in trace
    assert "BuildBotTraceEntriesJson(*selected, normalizedLimit)" in trace

    for code in [
        "moving_but_not_progressing",
        "quest_pickup_unreachable",
        "no_supported_objective",
        "stuck_repath_loop",
        "waiting_decision_tick",
        "target_rejected",
        "dead_recovery",
        "idle_no_candidate",
        "validation_route_terminal",
        "route_destination_unreachable",
        "advance_validation_route_segment",
        "inspect_dungeon_trash_cleared_evidence",
        "fail_validation_route_segment",
        "repeated_decision_loop",
        "idle_loop_guardrail",
        "target_churn_loop",
    ]:
        assert code in build_diagnosis

    for field in [
        "diagnosis_code",
        "severity",
        "confidence",
        "intent",
        "current_action",
        "blocker",
        "evidence",
        "active_quest_cluster_id",
        "quest_cooldown_count",
        "no_progress_cooldown_count",
        "pet_db_row_present",
        "pet_store_active",
        "pet_guid",
        "pet_entry",
        "pet_alive",
        "last_pet_readiness_action",
        "paladin_righteous_fury_ready",
        "paladin_seal_ready",
        "paladin_aura_ready",
        "paladin_blessing_ready",
        "paladin_divine_plea_ready",
        "validation_route_manifest_index",
        "validation_route_manifest_count",
        "validation_route_advance_mode",
        "validation_route_advance_pending",
        "validation_route_advance_reason",
        "validation_route_manifest_load_error",
        "validation_route_progress_baseline_kills",
        "validation_route_pack_generation",
        "validation_route_pack_member_count",
        "validation_route_pack_engaged_count",
        "validation_route_pack_death_count",
        "validation_route_pack_transition_count",
        "validation_route_pack_observed_engagement",
        "validation_route_config_kind",
        "validation_route_config_node_kind",
        "validation_route_config_target_entry",
        "validation_route_config_activation_data_id",
        "validation_route_config_activation_spawn_group_id",
        "validation_route_config_activation_action_entry",
        "validation_route_config_activation_action_id",
        "validation_route_config_activation_summon_entry",
        "validation_route_config_opener_summon_entry",
        "validation_route_has_activation",
        "validation_route_manager_activation_applied",
        "validation_route_manager_activation_attempts",
        "validation_route_distance",
        "decision_fingerprint_hash",
        "decision_fingerprint_repeat_count",
        "decision_fingerprint_failure_count",
        "consecutive_same_decision_count",
        "idle_decision_repeat_count",
        "target_churn_count",
        "loop_guardrail_count",
        "last_loop_guardrail_action",
        "last_recovery_mode",
        "next_expected_action",
        "suggested_investigation",
    ]:
        assert field in diagnosis_json

    for mapping in [
        '<< ",\\"pack_generation\\":" << _validationRoutePackGeneration',
        '<< ",\\"pack_member_count\\":" << _validationRoutePackMemberGuids.size()',
        '<< ",\\"pack_engaged_count\\":" << _validationRoutePackEngagedGuids.size()',
        '<< ",\\"pack_death_count\\":" << _validationRoutePackDeathGuids.size()',
        '<< ",\\"pack_transition_count\\":" << _validationRoutePackTransitionGuids.size()',
        '<< ",\\"pack_observed_engagement\\":" << (_validationRoutePackObservedEngagement ? "true" : "false")',
    ]:
        assert mapping in config_json

    for section in [
        "identity",
        "runtime",
        "movement",
        "quest",
        "target",
        "routing",
        "decision",
        "recent_failures",
        "fingerprint_hash",
        "fingerprint_repeat_count",
        "fingerprint_failure_count",
        "recovery",
        "loop_guardrail_count",
        "last_loop_guardrail_reason",
        "quest_cooldown_count",
        "no_progress_cooldown_count",
    ]:
        assert section in snapshot_json

    for field in [
        "timestamp_ms",
        "sequence",
        "situation",
        "action",
        "quest_id",
        "target_id",
        "destination",
        "result",
        "reason_code",
        "fingerprint_repeat_count",
        "consecutive_same_decision_count",
        "idle_decision_repeat_count",
        "target_churn_count",
        "loop_guardrail_action",
        "recovery_mode",
    ]:
        assert field in trace_entries

    assert "RecordDecisionTrace(state" in record_decision
    assert "loop_guardrail_triggered" in update_bot
    assert "state.LoopRecoveryCooldownUntilMs = nowMs + 15000;" in update_bot
    assert "RecordDecisionFingerprintMemory(state, bot, situation, action, chosenActivity, failure);" in record_decision
    assert_ordered(
        fingerprint,
        "last_recovery_result",
        'JsonEscape(state.LastRecoveryResult) << "\\""',
        "fingerprint_source",
    )
    assert_ordered(
        record_decision,
        "RecordDecisionFingerprintMemory(state, bot, situation, action, chosenActivity, failure);",
        "RecordDecisionTrace(state, situation, action, target, state.LastDecisionQuestId",
    )
    assert "bool forceTeacherEvent = eventName == \"combat_started\"" in record_event
    assert "eventName == \"objective_target_lost\"" in record_event
    assert "if (!policy.writeEvent && !forceTeacherEvent)" in record_event
    assert "reward = clampMetric(reward, -25.0f, 25.0f);" in update_outcome_stats
    assert "powerDelta = clampMetric(powerDelta, -25.0f, 25.0f);" in update_outcome_stats
    assert "state.DecisionTrace.push_back(entry)" in record_trace
    assert "state.DecisionTrace.size() > 64" in record_trace
    assert "debug_schema_version" in debug
    assert "diagnosis" in debug


def test_botauto_runtime_profiles_surface():
    manifest_path = ROOT / "dataset/bot_runtime_profiles/profiles.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile_names = {profile["name"] for profile in manifest["profiles"]}
    assert manifest["schema"] == "bot_world_runtime_profiles_v1"
    assert {"free_roam_small", "stonecore_5n", "blackwing_descent_10n", "watch_near_player"} <= profile_names
    for profile in manifest["profiles"]:
        assert isinstance(profile["name"], str) and profile["name"]
        assert isinstance(profile["target_population"], int)
    assert next(profile for profile in manifest["profiles"] if profile["name"] == "stonecore_5n")["validation_route"] == {
        "enable": True,
        "manifest_path": "dataset/validation_scenarios/validation_routes.jsonl",
        "advance_mode": "terminal",
        "scenario_id": "stonecore_5n",
    }

    conf = read(WORLDSERVER_CONF)
    mgr = read(BOT_MGR)
    mgr_header = read(BOT_MGR_HEADER)
    commands = read(BOT_COMMANDS)

    assert 'BotWorld.ProfileManifest = "dataset/bot_runtime_profiles/profiles.json"' in conf
    assert re.search(r"^BotWorld\.AutoStart\s*=\s*0$", conf, re.MULTILINE)
    assert "BotWorldExperimentProfile" in mgr_header
    assert "SelectRuntimeProfile" in mgr_header
    assert "ReloadRuntimeProfiles" in mgr_header
    assert '{ "profiles", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert '{ "profile", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "HandleAutoProfilesCommand" in commands
    assert "HandleAutoProfileCommand" in commands
    assert "SelectRuntimeProfile(profileName)" in commands
    assert "JsonFieldIsBool" in mgr
    assert "profile_missing_name" in mgr
    assert "profile_bad_type_" in mgr
    assert "ExtractJsonLineObjects(manifestJson)" in mgr
    assert "node.ScenarioId != _config.ValidationRouteScenarioId" in mgr
    assert_ordered(
        function_body(mgr, "void BotWorldPopulationMgr::LoadConfig"),
        'sConfigMgr->GetStringDefault("BotWorld.ProfileManifest"',
        'sConfigMgr->GetIntDefault("BotWorld.TargetPopulation"',
        "ApplyRuntimeProfile(profileItr->second)",
        "LoadValidationRouteManifest();",
    )
    status = function_body(mgr, "std::string BotWorldPopulationMgr::GetStatusJson")
    assert '\\"active_profile\\"' in status
    assert '\\"loaded_profile_count\\"' in status
    assert '\\"validation_route\\"' in status


def test_validation_route_terminal_paths_consume_manifest_without_waiting_for_next_tick():
    mgr = read(BOT_MGR)
    mgr_header = read(BOT_MGR_HEADER)
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    advance_manifest = function_body(mgr, "bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest")
    record_decision = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")

    assert_ordered(
        update_bot,
        'std::string recoveryReason = "validation_route_stuck_no_fallback";',
        'RecordEvent(state, bot, "stuck_detected"',
        'RecordDecision(state, bot, "validation_route_recovery", "validation_route_stuck"',
        "return;",
    )
    assert "state.LastRecoveryResult = \"fallback_disabled\";" in update_bot
    assert_ordered(
        update_bot,
        "RecordDecision(state, bot, situation.c_str(), action.c_str()",
        'if (action == "validation_route_complete")',
        "MaybeAdvanceValidationRouteManifest();",
    )
    assert_ordered(
        route_objective,
        '_validationRouteManifestAdvanceReason = "boss_killed";',
        "MaybeAdvanceValidationRouteManifest();",
        "return true;",
    )
    assert_ordered(
        route_objective,
        "auto isEligibleTrashClusterMob",
        "bool pullable = bot->IsWithinLOSInMap(creature)",
        "&& bot->GetExactDist(creature) <= routeEngageRange(bot, creature, 0);",
        "&& (hasStrictPathToValidationRouteTarget(creature) || pullable);",
        "auto isLiveTrashClusterMob",
        "auto isValidationRouteObjectiveTarget",
    )
    assert "&& bot->IsWithinLOSInMap(creature)\n            && hasStrictPathToValidationRouteTarget(creature);" not in route_objective
    assert_ordered(
        route_objective,
        "Unit* preAnchorTrashTarget = nullptr;",
        "preAnchorTrashTarget = findTrashClusterThreatTarget();",
        "if (routeDistance > routeArrivalRadius && !preAnchorTrashTarget)",
        "Unit* routeTarget = preAnchorTrashTarget;",
    )
    live_cluster_block = route_objective.split("auto isLiveTrashClusterMob", 1)[1].split("auto isValidationCohortPlayer", 1)[0]
    assert "if (!bot || !creature || !creature->IsAlive() || !creature->GetHealth())" in live_cluster_block
    assert "isValidationRoutePackEntry(creature->GetEntry())" in live_cluster_block
    assert "creature->IsInEvadeMode()" not in live_cluster_block
    assert "IsValidAttackTarget" not in live_cluster_block
    assert "hasStrictPathToValidationRouteTarget" not in live_cluster_block
    assert "bot->IsWithinLOSInMap(creature)" not in live_cluster_block
    assert "bot->GetExactDist(_config.ValidationRouteX, _config.ValidationRouteY, _config.ValidationRouteZ) + radius + 40.0f" in route_objective
    assert 'node.ExpectedAliveCount = uint32(std::max(0, readInt(routeJson, "expected_alive_count")));' in mgr
    assert "_config.ValidationRouteExpectedAliveCount = node.ExpectedAliveCount;" in mgr
    trash_liveness_block = route_objective.split("auto trashClusterHasLiveMobs", 1)[1].split("auto markTrashClusterCleared", 1)[0]
    assert "_config.ValidationRouteExpectedAliveCount && _metrics.Kills - _validationRouteProgressBaselineKills < _config.ValidationRouteExpectedAliveCount" not in trash_liveness_block
    assert "cohortState.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();" in route_objective
    assert "cohortState.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();" in route_objective
    assert 'markTrashClusterCleared("trash_cluster_expected_empty");' not in route_objective
    assert "&& !_config.ValidationRouteExpectedAliveCount" not in route_objective
    assert_ordered(
        route_objective,
        "auto recordValidationRouteTrashKill",
        "if (_validationRouteRecordedKillGuids.find(killedTarget->GetGUID()) != _validationRouteRecordedKillGuids.end())",
        "return false;",
        "_validationRouteRecordedKillGuids.insert(killedTarget->GetGUID());",
        "++_metrics.Kills;",
        "state.LastKilledTargetGuid = killedTarget->GetGUID();",
        "if (isValidationRouteScriptTarget(creature)",
        "if (!trashClusterHasLiveMobs())",
        '"trash_cluster_empty_pending_anchor_verification"',
    )
    assert "GuidSet _validationRouteRecordedKillGuids;" in mgr_header
    assert "_validationRouteRecordedKillGuids.clear();" in mgr
    for symbol in [
        "std::string ValidationRouteNodeKind;",
        "GuidSet _validationRoutePackMemberGuids;",
        "GuidSet _validationRoutePackEngagedGuids;",
        "GuidSet _validationRoutePackDeathGuids;",
        "GuidSet _validationRoutePackTransitionGuids;",
        "uint64 _validationRoutePackGeneration",
        "bool _validationRoutePackObservedEngagement",
    ]:
        assert symbol in mgr_header
    assert 'node.NodeKind = ExtractJsonStringField(routeJson, "node_kind");' in mgr
    assert 'node.ScriptedEventEntries = ExtractJsonUIntArrayField(routeJson, "scripted_event_entries");' in mgr
    assert 'node.ScriptedEventTransitionAuraIds = ExtractJsonUIntArrayField(routeJson, "scripted_event_transition_aura_ids");' in mgr
    assert 'ExtractJsonBoolField(routeJson, "scripted_event_require_passive", node.ScriptedEventRequirePassive);' in mgr
    assert '_config.ValidationRouteNodeKind = node.NodeKind;' in mgr
    assert '_config.ValidationRouteScriptedEventEntries = node.ScriptedEventEntries;' in mgr
    assert '_config.ValidationRouteScriptedEventTransitionAuraIds = node.ScriptedEventTransitionAuraIds;' in mgr
    route_progress_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildRouteProgressJson")
    record_route_progress = function_body(mgr, "void BotWorldPopulationMgr::RecordRouteProgress")
    assert '<< ",\\"generation\\":" << diagnostic.Generation' in route_progress_json
    assert "diagnostic.Generation = _validationRouteGeneration;" in record_route_progress
    assert '_config.ValidationRouteTargetEntry = node.NodeKind == "discovery_leg" ? 0 : node.TargetEntry;' in mgr
    assert 'bool discoveryLeg = _config.ValidationRouteNodeKind == "discovery_leg";' in route_objective
    assert_ordered(
        route_objective,
        "auto isNaturalForwardHostile",
        "auto findForwardDiscoveryTarget",
        "PathGenerator path(bot);",
        "path.GetPath();",
        "creature->GetAttackDistance(bot)",
        "candidateAlongPath",
        "guid < bestGuid",
        "enrollValidationRoutePackMember(best, false);",
    )
    for rejected_path in [
        "PATHFIND_NOPATH",
        "PATHFIND_NOT_USING_PATH",
        "PATHFIND_INCOMPLETE",
        "PATHFIND_SHORTCUT",
        "PATHFIND_FARFROMPOLY",
    ]:
        assert rejected_path in route_objective
    assert "if (discoveryLeg)\n            return findForwardDiscoveryTarget();" in route_objective
    assert "if (discoveryLeg)\n            return false;" in route_objective
    assert_ordered(
        route_objective,
        "auto isValidationCohortPlayer",
        "auto isValidationCohortCombatLinked",
        "auto enrollValidationRoutePackMember",
        "_validationRoutePackMemberGuids.insert(creature->GetGUID()).second;",
        "_validationRoutePackEngagedGuids.insert(creature->GetGUID()).second;",
        'RecordEvent(state, bot, "validation_route_pack_enrolled"',
        "auto enrollEngagedValidationRoutePackMembers",
        "isValidationCohortCombatLinked(creature)",
        "auto persistedValidationRoutePackHasLiveMembers",
        "_validationRoutePackDeathGuids.find(guid) == _validationRoutePackDeathGuids.end()",
        "auto trashClusterHasLiveMobs",
        "enrollEngagedValidationRoutePackMembers();",
        "persistedValidationRoutePackHasLiveMembers()",
    )
    transition_block = route_objective.split("auto recordValidationRouteScriptedTransition", 1)[1].split("auto enrollEngagedValidationRoutePackMembers", 1)[0]
    for required in [
        "_validationRoutePackEngagedGuids.find(creature->GetGUID())",
        "_config.ValidationRouteScriptedEventEntries.end()",
        "_config.ValidationRouteScriptedEventTransitionAuraIds[index]",
        "creature->HasAura(auraId)",
        "creature->GetVictim()",
        "creature->HasReactState(REACT_PASSIVE)",
        "_validationRoutePackTransitionGuids.insert(creature->GetGUID())",
        "_validationRouteFocusGuid == transitionedGuid",
        "cohortState.TargetGuid == transitionedGuid",
        "member->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE)",
        "cohortState.ActivePathValid = false",
        '"validation_route_scripted_transition"',
    ]:
        assert required in transition_block
    for generic_state in ["IsValidAttackTarget", "IsInEvadeMode", "UNIT_STATE_EVADE", "hasStrictPathToValidationRouteTarget", "IsWithinLOSInMap"]:
        assert generic_state not in transition_block
    assert "_validationRoutePackTransitionGuids.find(guid) == _validationRoutePackTransitionGuids.end()" in route_objective
    enrollment_scan = route_objective.split("auto enrollEngagedValidationRoutePackMembers", 1)[1].split("auto persistedValidationRoutePackHasLiveMembers", 1)[0]
    assert "creature->IsSummon()" in enrollment_scan
    assert 'engagementInserted ? "cohort_threat_link" : "route_selection"' in route_objective
    eligible_block = route_objective.split("auto isEligibleTrashClusterMob", 1)[1].split("auto isLiveTrashClusterMob", 1)[0]
    assert "_validationRoutePackTransitionGuids.find(creature->GetGUID())" in eligible_block
    assert "AttackStop" not in transition_block
    assert "CombatStop" not in transition_block
    assert_ordered(
        route_objective,
        "_validationRoutePackMemberGuids.insert(killedTarget->GetGUID());",
        "_validationRoutePackDeathGuids.insert(killedTarget->GetGUID());",
        'RecordEvent(state, bot, "mob_killed"',
    )
    assert "&& _validationRoutePackObservedEngagement" in route_objective
    assert "&& !partyInCombat" in route_objective
    assert "nowMs - _validationRoutePackClearCandidateSinceMs >= 2000" in route_objective
    assert "_validationRoutePackEngagedGuids.find(killedTarget->GetGUID())" in route_objective
    assert "bestAnchorTargetScore" not in route_objective
    assert '"dynamic_pack_members_live_or_unobserved"' in route_objective
    config_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildConfigJson")
    diagnosis_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")
    for field in [
        "pack_generation",
        "pack_member_count",
        "pack_engaged_count",
        "pack_death_count",
        "pack_transition_count",
        "pack_observed_engagement",
    ]:
        assert f'\\"{field}\\"' in config_json
        assert f'\\"validation_route_{field}\\"' in diagnosis_json
    assert_ordered(
        route_objective,
        'recordValidationRouteTrashKill(seenRouteTarget, "target_seen_dead");',
        "clearValidationRouteKilledFocus(seenRouteTarget->GetGUID());",
        "seenRouteTarget = nullptr;",
        "if (!routeTarget && seenRouteTarget && seenRouteTargetDistance > 8.0f)",
    )
    assert_ordered(
        route_objective,
        "routeDistance <= routeArrivalRadius && std::string(GetDungeonRole(bot)) == \"tank\"",
        "++state.ValidationRouteTargetSearchMissCount >= 2",
        "if (_config.ValidationRouteAdvanceMode == \"terminal\"",
        "&& _validationRoutePackObservedEngagement",
        "&& !packHasLiveMobs",
        "&& !partyInCombat",
        "&& nowMs - _validationRoutePackClearCandidateSinceMs >= 2000)",
        'markTrashClusterCleared("trash_cluster_cleared");',
    )
    assert 'uint32 routeTargetNoProgressThreshold = _config.ValidationRouteKind == "boss" ? 5 : 20;' in route_objective
    assert "bool _validationRouteManifestComplete = false;" in mgr_header
    assert_ordered(
        advance_manifest,
        "if (_validationRouteManifestComplete)",
        "_validationRouteManifestAdvancePending = false;",
        "return true;",
        'bool arrivalRoute = _config.ValidationRouteKind == "travel" || _config.ValidationRouteKind == "regroup" || _config.ValidationRouteKind == "descent";',
        "bool terminal = !arrivalRoute",
        "&& _validationRouteManifestAdvanceGeneration == _validationRouteGeneration;",
    )
    assert "uint32 loadedParticipants = 0;" in advance_manifest
    assert "if (!loadedBot)\n                continue;" in advance_manifest
    assert "++loadedParticipants;" in advance_manifest
    assert "!IsValidationCohortMemberInOriginalInstance(state, loadedBot)" in advance_manifest
    assert "_config.TargetPopulation && loadedParticipants < _config.TargetPopulation" in advance_manifest
    assert "if (loadedParticipants && allLoadedArrived)" in advance_manifest
    assert "cohortReadyForAdvance" in advance_manifest
    assert "terminalCohortRadius" in advance_manifest
    assert "loadedBot->GetExactDist(_config.ValidationRouteX, _config.ValidationRouteY, _config.ValidationRouteZ) > terminalCohortRadius" in advance_manifest
    assert "if (!cohortReadyForAdvance)\n            return false;" in advance_manifest
    assert 'state.ValidationRouteTerminalReason != "arrival"' in advance_manifest
    assert "bool successfulTerminal = state.ValidationRouteGeneration == _validationRouteGeneration" in advance_manifest
    assert "&& state.ValidationRouteTerminalGeneration == _validationRouteGeneration" in advance_manifest
    assert 'state.ValidationRouteTerminalReason == "all_routes_complete"' in advance_manifest
    assert '_config.ValidationRouteKind == "boss"' in advance_manifest
    assert 'state.ValidationRouteTerminalReason == "boss_killed"' in advance_manifest
    assert '_config.ValidationRouteKind != "boss"' in advance_manifest
    assert "state.LastDecisionAction" not in advance_manifest
    assert 'state.ValidationRouteTerminalReason == "trash_cluster_cleared"' in advance_manifest
    assert 'state.ValidationRouteTerminalReason == "trash_cluster_expected_empty"' not in advance_manifest
    assert "ValidationRouteTerminalState" not in record_decision
    assert_ordered(
        advance_manifest,
        "if (nextIndex >= _validationRouteManifest.size())",
        "_validationRouteManifestComplete = true;",
        'RecordEvent(*reporterState, reporter, "validation_route_manifest_complete"',
        "state.ValidationRouteTerminalState = true;",
        "return true;",
    )
    assert_ordered(
        route_objective,
        "if (state.ValidationRouteTerminalState",
        "&& state.ValidationRouteTerminalGeneration == _validationRouteGeneration)",
        "MoveBotToPoint(state, bot, routeAnchorX, routeAnchorY, routeAnchorZ)",
        "terminal_cohort_catchup",
        'action = "move_to_validation_route_anchor";',
    )
    assert_ordered(
        route_objective,
        "if (_validationRouteManifestComplete)",
        'action = "validation_route_complete";',
        "return true;",
    )
    assert "_validationRouteManifestComplete" not in record_decision


def test_clip_capture_smoke_persists_clip_row_with_pre_and_post_frames():
    buffer = read(BOT_BUFFER)
    capture = function_body(buffer, "uint64 BotTelemetryBuffer::CaptureEvent")
    append_post = function_body(buffer, "void BotTelemetryBuffer::AppendPostFrame")

    assert "uint64 preWindowMs = uint64(_config.PreEventWindowSec) * 1000;" in capture
    assert "frame.timestamp_ms + preWindowMs >= nowMs" in capture
    assert "clip.pre_frames.push_back(frame);" in capture
    assert "clip.post_frames.push_back(trigger);" in capture
    assert "if (clip.pre_frames.empty())" in capture
    assert "clip.pre_frames.push_back(trigger);" in capture
    assert_ordered(
        capture,
        "clip.clip_id = InsertClipRow",
        "InsertFrameRows(clip.clip_id, clip.trigger_time_ms, clip.pre_frames, 0)",
        "InsertFrameRows(clip.clip_id, clip.trigger_time_ms, clip.post_frames, 0)",
        "buffer.OpenClips.push_back(clip)",
    )

    assert "frame.timestamp_ms <= clip.end_time_ms" in append_post
    assert "clip.post_frames.push_back(frame);" in append_post


def test_segment_trigger_smoke_opens_quest_execution_and_closes_success():
    segments = read(BOT_SEGMENTS)
    ctor = function_body(segments, "BotExperimentCoordinator::BotExperimentCoordinator")
    handle = function_body(segments, "void BotExperimentCoordinator::HandleTelemetryEvent")
    start = function_body(segments, "void BotExperimentCoordinator::StartSegment")
    finish = function_body(segments, "void BotExperimentCoordinator::FinishSegment")

    assert '{ "quest_execution_v1", { { "quest_accepted" } }, { "quest_completed" }, { "objective_failed", "timeout" } }' in ctor
    assert_ordered(handle, "Contains(definition->SuccessEvents, event)", "FinishSegment(itr->second, BotExperimentSegmentStatus::Success")
    assert_ordered(handle, "Contains(definition->FailureEvents, event)", "FinishSegment(itr->second, event == \"timeout\"")
    assert_ordered(handle, "for (BotExperimentDefinition const& definition", "if (trigger.EventType == event)", "StartSegment(bot, definition")

    assert "INSERT INTO experiment_bot_segments" in start
    assert "'running'" in start
    assert "UPDATE experiment_bot_segments SET status = '%s'" in finish
    assert "BotExperimentSegmentStatus::Success" in finish
    assert "++_counts.Success;" in finish


def test_recovery_smoke_records_death_recovery_without_center_fallback_unless_enabled():
    mgr = read(BOT_MGR)
    conf = read(WORLDSERVER_CONF)
    recover = function_body(mgr, "BotWorldPopulationMgr::DeathRecoveryResult BotWorldPopulationMgr::RecoverDeadBot")
    last_safe_recover = function_body(mgr, "bool BotWorldPopulationMgr::TryLastSafePositionResurrect")
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    build_policy = function_body(mgr, "BotWorldPopulationMgr::BotDeathRecoveryPolicy BotWorldPopulationMgr::BuildDeathRecoveryPolicy")

    assert re.search(r"^BotWorld\.TeleportToCenterOnDeath\s*=\s*0$", conf, re.MULTILINE)
    assert "policy.CenterFallbackEnabled = _config.TeleportToCenterOnDeath;" in build_policy
    assert "policy.MaxDeathsBeforeFallback = _config.MaxDeathsBeforeFallback;" in build_policy
    assert "recovery.RepeatedDeath = state.RecentDeathCount >= policy.MaxDeathsBeforeFallback;" in recover
    assert 'mode == "configured_center_fallback" && (!policy.CenterFallbackEnabled || !recovery.RepeatedDeath)' in recover
    assert "void BotWorldPopulationMgr::RememberSafePosition" in mgr
    assert "if (_config.ValidationRouteEnable)" in function_body(mgr, "void BotWorldPopulationMgr::RememberSafePosition")
    assert "Distance2d(state.LastDeathX, state.LastDeathY, bot->GetPositionX(), bot->GetPositionY()) <= 70.0f" in mgr
    assert 'result = "safe_local_dangerous";' in mgr
    assert "unsafeValidationSafePosition(itr->MapId, itr->X, itr->Y, itr->Z)" in last_safe_recover
    assert "ORDER BY last_seen_at DESC LIMIT 16" in last_safe_recover
    assert "Distance2d(state.LastDeathX, state.LastDeathY, safe.X, safe.Y) <= 70.0f" in mgr
    assert 'result = "safe_position_dangerous";' in mgr
    assert 'RecordEvent(state, bot, "death_recovery_started"' in update_bot
    assert 'RecordEvent(state, bot, "resurrected"' in update_bot
    assert 'RecordEvent(state, bot, "teleport_fallback_used"' in update_bot
    assert 'RecordEvent(state, bot, "death_recovery_failed"' in update_bot


def test_telemetry_frame_action_is_bounded_to_schema_width():
    mgr = read(BOT_MGR)
    frame_builder = function_body(mgr, "BotTelemetryFrame BotWorldPopulationMgr::BuildTelemetryFrame")

    assert "frame.action = BoundedResultLabel(action);" in frame_builder
    assert "frame.action = action ? action : \"\";" not in frame_builder


def test_export_smoke_lists_old_and_new_bot_experiment_tables():
    commands = read(BOT_COMMANDS)
    export_body = function_body(commands, "static bool HandleExportCommand")
    match = re.search(r'PSendSysMessage\("(?P<payload>\{.*?\})"\);', export_body, re.DOTALL)
    assert match
    payload = json.loads(match.group("payload").replace('\\"', '"'))

    assert payload["ok"] is True
    assert payload["action"] == "botexp_export"
    assert payload["storage"] == "character_database_tables"
    assert payload["embedding_feature_schema"] == "bot_semantic_phase6_v1"
    assert payload["policy_feature_schema"] == "bot_policy_features_v1"
    assert payload["failure_reason"] is None
    assert payload["tables"] == [
        "experiment_bot_runs",
        "experiment_bot_segments",
        "experiment_bot_events",
        "experiment_bot_decisions",
        "experiment_bot_activities",
        "experiment_bot_replay_records",
        "experiment_bot_clips",
        "experiment_bot_clip_frames",
        "bot_semantic_outcome_stats",
        "bot_memory_pois",
        "bot_memory_danger_zones",
        "bot_memory_failed_paths",
        "bot_memory_safe_positions",
        "bot_memory_objective_clusters",
        "bot_memory_recipe_sources",
        "bot_memory_material_sources",
        "bot_memory_daily_cooldowns",
        "bot_memory_transport_usage",
        "bot_memory_decision_fingerprints",
        "bot_policy_models",
        "bot_policy_evaluations",
    ]


def test_extended_bot_memory_schema_and_decision_fingerprint_surface():
    schema = read(ROOT / "sql/updates/characters/4.3.4/2026_06_16_00_characters_bot_extended_memory.sql")
    mgr_header = read(ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h")
    mgr = read(BOT_MGR)
    record_decision = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")
    fingerprint = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionFingerprintMemory")
    record_quest = function_body(mgr, "void BotWorldPopulationMgr::RecordQuestEvent")
    objective_cluster = function_body(mgr, "void BotWorldPopulationMgr::RecordObjectiveClusterMemory")
    remember_poi = function_body(mgr, "void BotWorldPopulationMgr::RememberPoi")
    visible_source = function_body(mgr, "void BotWorldPopulationMgr::RememberVisibleSourceMemory")
    diagnosis_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")

    for table in [
        "bot_memory_objective_clusters",
        "bot_memory_recipe_sources",
        "bot_memory_material_sources",
        "bot_memory_daily_cooldowns",
        "bot_memory_transport_usage",
        "bot_memory_decision_fingerprints",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in schema

    for column in [
        "`cluster_id` int unsigned NOT NULL",
        "`recipe_spell_id` int unsigned NOT NULL",
        "`item_id` int unsigned NOT NULL",
        "`available_at` datetime NOT NULL",
        "`transport_type` varchar(64) NOT NULL",
        "`fingerprint_hash` int unsigned NOT NULL",
        "UNIQUE KEY `uniq_bot_fingerprint` (`bot_guid`, `fingerprint_hash`)",
    ]:
        assert column in schema

    assert "RecordDecisionFingerprintMemory" in mgr_header
    assert "RecordDecisionFingerprintMemory(state, bot, situation, action, chosenActivity, failure);" in record_decision
    assert "INSERT INTO bot_memory_decision_fingerprints" in fingerprint
    assert "ON DUPLICATE KEY UPDATE repeat_count = repeat_count + 1" in fingerprint
    assert "FeatureSchemaHash(fingerprint.str())" in fingerprint
    assert "LastDecisionFingerprintRepeatCount" in mgr_header
    assert "SELECT repeat_count, failure_count FROM bot_memory_decision_fingerprints" in fingerprint
    assert "fingerprint_source" in fingerprint
    assert "RecordObjectiveClusterMemory(state, bot, eventType, questId, result, valueInt, contextJson);" in record_quest
    assert "INSERT INTO bot_memory_objective_clusters" in objective_cluster
    assert "DATE_ADD(NOW(), INTERVAL 2 MINUTE)" in objective_cluster
    assert "RememberVisibleSourceMemory(state, bot, object, poiType, entry, questId, metadataJson.c_str());" in remember_poi
    assert "INSERT INTO bot_memory_recipe_sources" in visible_source
    assert "INSERT INTO bot_memory_material_sources" in visible_source
    assert "decision_fingerprint_repeat_count" in diagnosis_json


def test_policy_model_shadow_assist_uses_registered_artifact_and_safe_gate():
    mgr_header = read(ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h")
    mgr = read(BOT_MGR)
    conf = read(WORLDSERVER_CONF)
    schema = read(ROOT / "sql/updates/characters/4.3.4/2026_06_14_00_characters_bot_policy_models.sql")
    area_schema = read(ROOT / "sql/updates/characters/4.3.4/2026_06_14_01_characters_bot_decision_area_id.sql")
    validate = function_body(mgr, "void BotWorldPopulationMgr::ValidatePolicyModelDeployment")
    load_artifact = function_body(mgr, "bool BotWorldPopulationMgr::LoadPolicyModelArtifact")
    apply_scores = function_body(mgr, "void BotWorldPopulationMgr::ApplyPolicyModelScores")
    score = function_body(mgr, "float BotWorldPopulationMgr::ScorePolicyModelCandidate")
    trace = function_body(mgr, "BotWorldPopulationMgr::PolicyModelTrace BotWorldPopulationMgr::BuildPolicyModelTrace")
    record = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")

    for symbol in [
        "ArtifactPath",
        "ArtifactLoaded",
        "ModelMeans",
        "ModelWeights",
        "LoadPolicyModelArtifact",
        "PredictPolicyModelLabel",
        "BuildPolicyModelFeatureMap",
        "RecordDecisionReplay",
    ]:
        assert symbol in mgr_header

    assert "accepted, artifact_path, model_type" in validate
    assert "LoadPolicyModelArtifact(_policyModelConfig.ArtifactPath)" in validate
    assert "_policyModelConfig.Mode == \"shadow\"" in validate
    assert "_policyModelConfig.Mode == \"control\"" in validate
    assert "control_mode_disabled" in validate
    assert "_policyModelConfig.AssistAllowed = true;" in validate
    assert "artifact_load_failed" in validate

    assert "ReadSmallTextFile(artifactPath)" in load_artifact
    assert "ExtractJsonObjectField(json, \"means\")" in load_artifact
    assert "ExtractJsonObjectField(json, \"weights\")" in load_artifact
    assert "_policyModelConfig.ArtifactLoaded = true;" in load_artifact

    assert "MaxDecisionLatencyMs" in apply_scores
    assert "latencyMs > _policyModelConfig.MaxDecisionLatencyMs" in apply_scores
    assert "PredictPolicyModelLabel(\"expected_reward\", features)" in score
    assert "PredictPolicyModelLabel(\"death_risk\", features)" in score
    assert "artifact_loaded" in trace
    assert "model_type" in trace
    assert '\\"run_id\\"' in trace
    assert '\\"experiment_id\\"' in trace
    assert '\\"decision_id\\":null' in trace
    assert '\\"replay_id\\":' in trace
    assert '\\"feature_schema_version\\"' in trace

    for column in [
        "`model_version` varchar(128) NULL",
        "`feature_schema_version` varchar(64) NULL",
        "`model_score` float NULL",
        "`model_rank` int unsigned NULL",
        "`model_features_hash` int unsigned NULL",
    ]:
        assert column in schema
    assert "ADD COLUMN `area_id` int unsigned NULL" in area_schema
    assert "idx_experiment_bot_decisions_area" in area_schema

    assert "RecordDecisionReplay(state, bot, target" in record
    assert "replay_key" in record
    assert "zone_id, area_id, x, y, z" in record
    assert "bot->GetAreaId()" in record
    assert "model_version, feature_schema_version, model_score, model_rank, model_features_hash" in record
    for key in [
        "BotPolicyModel.MinEvalRows = 100",
        "BotPolicyModel.MaxDeathRate = 0.0",
        "BotPolicyModel.MaxStuckRate = 0.0",
        "BotPolicyModel.MaxFailureRate = 0.0",
    ]:
        assert key in conf
    assert "Mode may be shadow," in conf
    assert "assist, or control" in conf


def test_host_world_makefile_can_generate_always_on_recording_config():
    makefile = read(ROOT / "Makefile")

    assert "BOTWORLD_ENABLE ?= 1" in makefile
    assert "BOTWORLD_AUTOSTART ?= 0" in makefile
    assert "BOTWORLD_AUTOSTART_RECORDING ?= 1" in makefile
    assert "BOTWORLD_RECORDING_WINDOW_MINUTES ?= 15" in makefile
    assert "BOTWORLD_TARGET_POPULATION ?= 5" in makefile
    assert "BOTWORLD_ALLOW_CONFIGURED_CENTER_FALLBACK ?= 0" in makefile
    assert "BOTWORLD_USE_SAVED_POSITION ?= 1" in makefile
    assert "host-world-botexp-real" in makefile
    assert "host-world-botexp-watch" in makefile
    assert "bot-live-validate" in makefile
    assert "tools.bot_ml.run_live_bot_validation" in makefile
    assert "BotWorld.AutoStart = $(BOTWORLD_AUTOSTART)" in makefile
    assert "BotWorld.AutoStartRecording = $(BOTWORLD_AUTOSTART_RECORDING)" in makefile
    assert "BotWorld.AutoRecordingWindowMinutes = $(BOTWORLD_RECORDING_WINDOW_MINUTES)" in makefile
    assert "s|^BotWorld\\.SpawnMode\\s*=.*$$|BotWorld.SpawnMode = \"$(BOTWORLD_SPAWN_MODE)\"|gm" in makefile
    assert "BotWorld.UseSavedPosition = $(BOTWORLD_USE_SAVED_POSITION)" in makefile
    assert "BotWorld.RespawnMode = \"safe_local\"" in makefile
    assert "BotWorld.AllowQuesting = 1" in makefile


def test_player_bot_chase_movement_inform_does_not_deref_non_creature_owner():
    chase = read(CHASE_MOVEMENT)
    inform = function_body(chase, "inline void DoMovementInform")

    assert "if (!owner->IsCreature())" in inform
    assert_ordered(inform, "if (!owner->IsCreature())", "return;", "owner->ToCreature()->AI()")
