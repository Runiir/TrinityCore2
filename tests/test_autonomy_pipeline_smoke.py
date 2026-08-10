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
PRAYER_OF_MENDING_GUARD_SQL = ROOT / "sql/custom/world/2026_07_14_02_holy_priest_prayer_of_mending_aura_guard.sql"
PALADIN_AOE_THREAT_SQL = ROOT / "sql/custom/world/2026_07_14_03_stonecore_paladin_aoe_threat_priority.sql"
MARKSMAN_STATIONARY_SQL = ROOT / "sql/custom/world/2026_07_14_04_marksmanship_cast_time_stationary.sql"
EMERGENCY_ADD_THREAT_SQL = ROOT / "sql/custom/world/2026_07_15_01_stonecore_emergency_add_threat.sql"
WOWHEAD_GUIDE_ROTATION_SQL = ROOT / "sql/custom/world/2026_07_16_00_stonecore_wowhead_guide_rotations.sql"
PROTECTION_HOLY_WRATH_SELF_SQL = ROOT / "sql/custom/world/2026_08_09_00_phase9_protection_holy_wrath_self_center.sql"
BOT_POLICY = ROOT / "src/server/game/Bots/BotTelemetryPolicy.cpp"
BOT_BUFFER = ROOT / "src/server/game/Bots/BotTelemetryBuffer.cpp"
BOT_SEGMENTS = ROOT / "src/server/game/Bots/BotExperimentCoordinator.cpp"
WORLDSERVER_CONF = ROOT / "src/server/worldserver/worldserver.conf.dist"
CHASE_MOVEMENT = ROOT / "src/server/game/Movement/MovementGenerators/ChaseMovementGenerator.cpp"
MAP_CPP = ROOT / "src/server/game/Maps/Map.cpp"
PLAYER_CPP = ROOT / "src/server/game/Entities/Player/Player.cpp"
VALIDATION_SCENARIOS = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
PYTEST_CONFIG = ROOT / "pytest.ini"
AZIL_SCRIPT = ROOT / "src/server/scripts/Maelstrom/Stonecore/boss_high_priestess_azil.cpp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_prayer_of_mending_profile_uses_the_applied_aura_as_its_guard() -> None:
    migration = read(PRAYER_OF_MENDING_GUARD_SQL)

    assert "`action`.`spell_id` = 33076" in migration
    assert "`action`.`forbidden_target_aura` = 41635" in migration
    assert "`action`.`maintain_aura_id` = 41635" in migration


def test_protection_paladin_prioritizes_multi_target_threat_actions() -> None:
    migration = read(PALADIN_AOE_THREAT_SQL)

    assert "`profile`.`spec_tag` = 'protection'" in migration
    assert "`action`.`spell_id` IN (53595, 26573) THEN 1" in migration
    assert "`action`.`spell_id` IN (53595, 26573, 2812)" in migration


def test_profile_taunts_require_a_real_non_tank_victim() -> None:
    manager = read(BOT_MGR)
    assert manager.count("(!target->GetVictim() || target->GetVictim() == bot)") >= 2

    fillers = read(ROOT / "sql/custom/world/2026_07_16_06_protection_single_target_fillers.sql")
    assert "`action`.`min_enemies`=1" in fillers
    assert "WHEN `action`.`spell_id`=26573 THEN 5" in fillers
    assert "WHEN `action`.`spell_id`=2812 THEN 6" in fillers


def test_combat_telemetry_attributes_player_totem_damage_to_its_owner() -> None:
    manager = read(BOT_MGR)
    owner_helper = function_body(manager, "Player* CombatOwnerPlayer")
    damage_hook = function_body(manager, "void BotWorldPopulationMgr::NotifyCombatDamage")

    assert "current->ToTotem()->GetOwner()" in owner_helper
    assert "depth < 4" in owner_helper
    assert "CombatOwnerPlayer(attacker)" in damage_hook


def test_marksmanship_cast_time_shots_require_stationary_execution() -> None:
    migration = read(MARKSMAN_STATIONARY_SQL)

    assert "`action`.`spell_id` IN (19434, 56641)" in migration
    assert "`action`.`requires_stationary` = 1" in migration


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
    assert generated_by_step[1]["cluster_radius_yards"] == 0.0
    assert "expected_alive_count" not in generated_by_step[1]
    assert generated_by_step[1]["pack_target_entries"] == []
    assert generated_by_step[1]["completion_policy"] == "corridor_clear_after_engagement"
    assert all(route["expected_alive_count"] == len(route["pack_target_entries"]) for route in generated_trash if route["step"] != 1)
    assert all(route["expected_alive_count"] > 0 for route in generated_trash if route["node_kind"] == "trash_cluster")
    assert all(route["expected_alive_count_semantics"] == "descriptive_only" for route in generated_trash)
    assert all(route["completion_policy"] == "cluster_clear_after_pull" for route in generated_trash if route["step"] != 1)
    corborus = next(route for route in manifest["validation_routes"] if route["scenario_id"] == "stonecore_5n" and route["label"] == "Corborus")
    assert corborus["add_target_entries"] == [43917]


def test_validation_route_group_focus_reaches_profile_action_without_threat_rewait():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    group_focus_start = route_objective.index("if (Unit* focusTarget = routeGroupFocusTarget())")
    group_focus_end = route_objective.index('if (std::string(GetDungeonRole(bot)) != "tank"\n        && (', group_focus_start)
    group_focus = route_objective[group_focus_start:group_focus_end]
    later_threat_gate = 'if (routeBossTarget && _config.ValidationRouteKind != "boss" && !botIsTank\n            && validationRouteHasLivingTank() && !routeFocusTankOwned(target))'

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


def test_validation_route_prerequisite_switch_resets_pack_progress_budget():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    switch_marker = "else\n            {\n                state.ValidationRoutePackProgressTargetGuid"
    target_switch = switch_marker + route_objective.split(switch_marker, 1)[1]
    target_switch = target_switch.split("}\n\n            if (contextIsCombatProgressProbe()", 1)[0]

    assert "A prerequisite switch is fresh progress context" in target_switch
    assert_ordered(
        target_switch,
        "state.ValidationRoutePackProgressTargetGuid = prerequisiteTarget->GetGUID();",
        "state.ValidationRoutePackBestHealthPct = healthPct;",
        "state.ValidationRoutePackNoProgressCount = 0;",
        "return false;",
    )


def test_unengaged_boss_prerequisite_cannot_latch_trash_failure_terminal():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    no_progress = route_objective.split("bool unengagedBossPrerequisite", 1)[1].split(
        "if (bossRouteContext", 1
    )[0]

    assert '&& !isValidationRouteScriptTarget(creature)' in no_progress
    assert '&& !prerequisiteTarget->IsInCombat()' in no_progress
    assert '&& !prerequisiteTarget->GetVictim();' in no_progress
    assert_ordered(
        no_progress,
        "if (unengagedBossPrerequisite)",
        "state.ValidationRouteCombatNoProgressCount = 0;",
        "state.ValidationRoutePackNoProgressCount = 0;",
        'refreshRouteProgress("unengaged_boss_prerequisite_observed", 0);',
        "return false;",
    )
    assert "markValidationRouteTrashFailed" not in no_progress


def test_boss_prerequisites_use_trash_swarm_threat_security_without_intercepting_boss_adds():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    threat_security = route_objective.split("struct TrashThreatControl", 1)[1].split(
        "if (tryValidationRouteAdds())", 1
    )[0]

    assert "Boss nodes can still contain ordinary prerequisite packs" in threat_security
    assert "isValidationRouteScriptTarget(creature) || declaredBossAdd" in threat_security
    assert 'if (bot->getClass() == CLASS_HUNTER' in threat_security
    assert "bool useAreaTransfer = trashThreatControl.EngagedCount >= 2;" in threat_security
    assert 'if (std::string(GetDungeonRole(bot)) == "dps"' in threat_security
    assert '"prerequisite_swarm_emergency_defensive"' in threat_security
    assert '"spread_after_secure_prerequisite_threat"' in threat_security
    assert 'if (_config.ValidationRouteKind != "boss"' not in threat_security


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
    assert "CombatArchetypeForClass(state.ClassId, _runtimeRole, _classSpec)" in decide
    assert 'classSpec == "enhancement_shaman"' in controller
    assert "return BotCombatArchetype::MeleeDps;" in controller
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
    assert 'classSpec == "survival_hunter"' in profiles
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
        'action.AutoAttackMode == "melee"',
        "bot->Attack(target, true);",
        "action.SpellId == 75",
        "CURRENT_AUTOREPEAT_SPELL",
        "BotActionResult check = CheckHostileSpell(owner, bot, target, action.SpellId);",
        "TARGET_FLAG_DEST_LOCATION",
        ": bot->CastSpell(target, action.SpellId, castArgs);",
    )
    assert "!bot->IsWithinMeleeRange(actionTarget)" in world_mgr


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

    for spell_id in ["25780", "31801", "465", "20217", "13165", "982", "1130", "34477"]:
        assert spell_id in readiness

    assert "divine_plea_ready" not in readiness

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

    assert "if (bot->IsInCombat())" in readiness
    assert "state.GroupReadinessStableSinceMs = 0;" in readiness
    assert 'result.Action = "validation_route_readiness_wait";' in readiness
    assert "nowMs - state.GroupReadinessStableSinceMs < 10000" in readiness
    assert "hunterHasStoredPet" in readiness
    assert "(!bot->GetPet() || !bot->GetPet()->IsAlive())" in readiness
    assert "if (!urgentHunterPetRecovery)\n        for (ActiveBuffRequirement const& requirement" in readiness
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
    assert "static uint32 const callPetSpells[] = { 883, 83242, 83243, 83244, 83245 };" in readiness
    assert "bot->GetPlayerPetDataBySlot(slot)" in readiness
    assert "validation_route_readiness_call_pet" in readiness
    assert "hunter_pet_call_failed:" in readiness
    assert "hunter_pet_missing" in readiness
    assert "hunter_pet_dead" in readiness
    assert "buff_cast_failed:\" << readyReason << \":spell=\" << spellId << \":target=\"" in readiness
    assert "if (!canAttempt(attemptKey))\n            return true;" in readiness
    assert 'state.ReadinessPartyCoverageSignature[attemptKey] == "cast_once"' not in function_body(
        readiness, "auto castSelf"
    )
    assert "state.ReadinessRetryUntilMs[attemptKey] = nowMs + 5000;" in readiness
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


def test_headless_hunter_promotes_a_valid_stable_pet_without_displacing_active_slots():
    bot_mgr = read(PLAYER_BOT_MGR)
    load = function_body(bot_mgr, "Player* BotMgr::LoadCharacterAsBotSession")

    assert_ordered(
        load,
        "bot->LoadPetsFromDB(holder->GetPreparedResult(PLAYER_LOGIN_QUERY_LOAD_ALL_PETS))",
        "if (bot->getClass() == CLASS_HUNTER)",
        "for (uint8 slot = PET_SLOT_FIRST_ACTIVE_SLOT; slot <= PET_SLOT_LAST_ACTIVE_SLOT; ++slot)",
        "if (!bot->GetPlayerPetDataCurrent())",
        "if (Optional<uint8> activeSlot = bot->GetFirstUnusedActivePetSlot())",
        "for (uint8 slot = PET_SLOT_FIRST_STABLE_SLOT; slot <= PET_SLOT_LAST_STABLE_SLOT; ++slot)",
        "stagedStablePet = petData;",
        "petData->Slot = *activeSlot;",
        "petData->Active = true;",
        "PlayerBot hunter stable pet staged",
        "bot->LoadPet()",
        "loadedPet->GetCharmInfo()->GetPetNumber() == stagedStablePet->PetId",
        "UPDATE character_pet SET active = 1, slot = %u WHERE owner = %u AND id = %u",
        "PlayerBot hunter stable pet activated",
    )
    assert "isLoadableHunterPet" in load
    assert "creatureInfo->IsTameable(bot->CanTameExoticPets())" in load
    assert "GetFirstUnusedActivePetSlot" in load
    assert "CHAR_UPD_CHAR_PET_SLOT_BY_SLOT" not in load
    assert "TryCastFriendlySpell(bot, bot, 883)" not in load


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
    assert "Totem* totem = creature ? creature->ToTotem()" in totems
    assert "totem && totem->IsAlive()" in totems
    assert "totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == spellId" in totems
    assert "totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) == 2894" in totems
    assert "elemental->GetEntry() != 15438" in totems
    assert "elemental->AI()->AttackStart(target)" in totems
    assert "totem->GetSpell() == spellId" not in totems
    assert "ReadinessRetryUntilMs" in totems
    assert "totem_cast_failed:" in totems
    assert "desiredTotems" in totems
    assert "individual_combat_totem" in totems
    assert "SUMMON_SLOT_TOTEM_FIRE" in totems
    assert "SUMMON_SLOT_TOTEM_EARTH" in totems
    assert "SUMMON_SLOT_TOTEM_WATER" in totems
    assert "SUMMON_SLOT_TOTEM_AIR" in totems
    assert "TryEnsureCombatTotems(*state, bot, target, hostileCount)" in execute_profile
    assert "hostileCount >= 3 && bot->HasSpell(8190) ? 8190 : 3599" in totems
    assert "totem->AI()->AttackStart(target)" in totems

    totem_ai = read(ROOT / "src/server/game/AI/CoreAI/TotemAI.cpp")
    assert "me->ToTotem()->GetOwner()" in totem_ai
    assert "me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED)" in totem_ai
    assert "owner->IsValidAttackTarget(victim, spellInfo)" in totem_ai
    assert "TRIGGERED_IGNORE_TARGET_CHECK" in totem_ai
    assert "_lastCastResult = me->CastSpell" in totem_ai
    assert "++_updateCalls" in totem_ai
    assert "++_noTargetSkips" in totem_ai


def test_cobra_shot_extends_serpent_sting_periodic_tick_budget():
    hunter = read(ROOT / "src/server/scripts/Spells/spell_hunter.cpp")
    cobra = hunter[hunter.index("// 77767 - Cobra Shot"):hunter.index("// -53234 - Piercing Shots")]

    assert "aur->SetDuration(std::min(newDuration, aur->GetMaxDuration()), true)" in cobra
    assert "periodic->ResetTicks()" in cobra


def test_persistent_spec_setup_precedes_dummy_and_profile_rotations():
    mgr = read(BOT_MGR)
    setup = function_body(mgr, "bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup")
    calibration = function_body(mgr, "void BotWorldPopulationMgr::UpdateCalibrationBot")
    execute_profile = function_body(
        mgr,
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state, Player* bot, Unit* target, ResolvedCombatAction* actionOut, uint32 hostileCount, bool densityOnly)",
    )

    for spell_id in ["25780", "31801", "465", "20217", "1459", "30482", "13165", "324", "8232", "8024", "1130"]:
        assert spell_id in setup
    assert "79058" in setup
    assert "79063" in setup
    assert "TEMP_ENCHANTMENT_SLOT" in setup
    assert "EQUIPMENT_SLOT_MAINHAND" in setup
    assert "EQUIPMENT_SLOT_OFFHAND" in setup
    assert "targets.SetItemTarget(weapon)" in setup
    assert "TryEnsurePersistentCombatSetup(state, bot, target)" in calibration
    assert_ordered(calibration, "TryEnsurePersistentCombatSetup(state, bot, target)", "metrics.WindowStartedMs = NowMs()")
    assert "TryEnsurePersistentCombatSetup(*state, bot, target)" in execute_profile

    calibration_json = function_body(mgr, "std::string BotWorldPopulationMgr::GetCombatCalibrationJson")
    assert '\\"persistent_setup\\"' in calibration_json
    assert '\\"mainhand_temp_enchant\\"' in calibration_json
    assert '\\"offhand_temp_enchant\\"' in calibration_json
    assert '\\"fire_totem\\"' in calibration_json
    assert '\\"last_cast_result\\"' in calibration_json
    assert '\\"cast_successes\\"' in calibration_json
    assert '\\"uses_totem_ai\\"' in calibration_json
    assert '\\"autorepeat_spell\\"' in calibration_json
    assert '\\"no_target_skips\\"' in calibration_json
    assert '\\"stats\\"' in calibration_json


def test_reference_calibration_reports_only_conditions_it_applies():
    mgr = read(BOT_MGR)
    calibration_json = function_body(mgr, "std::string BotWorldPopulationMgr::GetCombatCalibrationJson")

    assert '\\"flask\\"' in calibration_json
    assert '\\"potions\\":false' in calibration_json
    assert '\\"engineering_cooldowns\\":false' in calibration_json
    assert '\\"racial_cooldowns\\":false' in calibration_json
    assert '\\"consumables\\":false' in calibration_json


def test_requested_wowhead_profiles_and_target_count_aware_misdirection_are_explicit():
    sql = read(WOWHEAD_GUIDE_ROTATION_SQL)
    manager = read(BOT_MGR)

    for token in [
        "'survival', 'dps', 'focus'",
        "53301, 'spender', 'explosive_shot",
        "3674, 'dot', 'black_arrow",
        "2643, 'aoe', 'multi_shot,aoe,misdirection_transfer'",
        "77767, 'resource_generator', 'cobra_shot",
        "11129,'spender','combustion",
        "51533,'offensive_cooldown','feral_spirit",
        "88625,'heal_fast','holy_word_serenity",
        "84963,'spender','inquisition",
    ]:
        assert token in sql
    assert "`action`.`required_self_aura_stacks` = CASE" in sql
    assert "WHEN `action`.`spell_id` IN (403,421) THEN 5" in sql
    assert "a.min_primary_power_pct, a.max_primary_power_pct" in read(PLAYER_BOT_ACTION_PROFILE)
    assert "bool useAreaTransfer = trashThreatControl.EngagedCount >= 2;" in manager
    assert "bool useAreaTransfer = addCount >= 2;" in manager
    assert 'useAreaTransfer ? "misdirection_aoe_transfer" : "misdirection_single_target_transfer"' in manager
    assert "ResolveProfileCombatAction(bot, target, 1, false)" in manager


def test_dummy_calibration_tuning_gates_spenders_and_adds_measured_aoe_actions():
    root = Path(__file__).resolve().parents[1]
    sql = (root / "sql/custom/world/2026_07_16_03_dummy_dps_rotation_tuning.sql").read_text()
    manager = read(BOT_MGR)

    assert "11113,'aoe','blast_wave,aoe,on_cooldown'" in sql
    assert "`action`.`required_self_aura`=64343" in sql
    assert "`action`.`required_self_aura`=73683" in sql
    assert "POWER_HOLY_POWER" in manager
    assert 'candidate.SpellId == 53600 || candidate.SpellId == 84963' in manager
    assert "combustion_dot_window_not_ready" in manager
    assert "ignite->GetAmount() < 10000" in manager


def test_enhancement_unleash_flame_experiment_has_measured_rollback():
    experiment = read(ROOT / "sql/custom/world/2026_07_17_01_enhancement_unleash_flame_priority.sql")
    rollback = read(ROOT / "sql/custom/world/2026_07_17_02_enhancement_unleash_flame_rollback.sql")

    assert "`action`.`spell_id`=73680" in experiment
    assert "`action`.`required_self_aura`=73683" in experiment
    assert "`action`.`refresh_aura_below_ms`=9000" in experiment
    assert "`action`.`priority_bucket`=4" in rollback
    assert "`action`.`required_self_aura`=0" in rollback
    assert "`action`.`maintain_aura_id`=8050" in rollback
    assert "`action`.`refresh_aura_below_ms`=0" in rollback


def test_enhancement_uses_and_preserves_fire_elemental_before_searing_fallback():
    root = Path(__file__).resolve().parents[1]
    sql = (root / "sql/custom/world/2026_07_16_07_enhancement_fire_elemental.sql").read_text()
    provisioning = (root / "experiments/configs/validation_provisioning_cata_001.json").read_text()

    assert "2894,'offensive_cooldown','fire_elemental_totem" in sql
    assert provisioning.count('"spells": [2894]') == 2

    elemental_ai = (root / "src/server/scripts/Pet/pet_shaman.cpp").read_text()
    assert "AcquireShamanOwnerVictim" in elemental_ai
    assert "owner->GetVictim()" in elemental_ai
    assert "UNIT_FLAG_PLAYER_CONTROLLED" in elemental_ai


def test_dummy_calibration_followup_spreads_living_bomb_and_avoids_refresh_waste():
    root = Path(__file__).resolve().parents[1]
    sql = (root / "sql/custom/world/2026_07_16_04_dummy_dps_rotation_followup.sql").read_text()
    resolver = function_body(read(BOT_MGR), "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction")

    assert "activeLivingBombs < 3" in resolver
    assert "spreadTarget->HasAura(44457, bot->GetGUID())" in resolver
    assert 'action.DebugName = "living_bomb_spread"' in resolver
    assert "`action`.`maintain_aura_id`=84963" in sql
    assert "`action`.`spell_id`=73680" in sql
    assert "`action`.`priority_bucket`=4" in sql


def test_dummy_calibration_uses_aura_refresh_threshold_for_serpent_sting():
    sql = read(ROOT / "sql/custom/world/2026_07_16_05_dummy_dps_aura_refresh.sql")
    profile = read(PLAYER_BOT_ACTION_PROFILE)
    manager = read(BOT_MGR)

    assert "`action`.`maintain_aura_id`=1978" in sql
    assert "`action`.`refresh_aura_below_ms`=3000" in sql
    assert "MaintainedAuraBlocksRefresh" in profile
    assert "spell.RefreshAuraBelowMs" in profile
    assert "MaintainedProfileAuraBlocksRefresh" in manager
    assert "spell.RefreshAuraBelowMs" in manager


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
        "56641, 'resource_generator', 'steady_shot,focus_builder",
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
    assert 'validationRouteHasLivingTank() && !routeFocusTankOwned(target)' in validation_route_objective
    assert "activeValidationRoutePackTarget" in validation_route_objective
    assert "if (Unit* packTarget = activeValidationRoutePackTarget())" in validation_route_objective
    assert "if (botIsTank && victim && !victimIsTank)" in validation_route_objective
    assert "score += 20000.0f;" in validation_route_objective
    assert "bool livingTankAvailable = false;" in validation_route_objective
    assert 'if (_config.ValidationRouteKind != "boss" && !memberIsTank && livingTankAvailable)' in validation_route_objective
    assert '"tank_positioning", target, "route_trash_tank_focus"' in validation_route_objective
    rotation_profiles_sql = read(ROOT / "sql/custom/world/2026_06_21_00_bot_rotation_profiles.sql")
    assert "blood_presence,self,tank_stance,mitigation" in rotation_profiles_sql
    assert "death_strike,self_heal,melee,threat" in rotation_profiles_sql
    assert "(8, 'fire', 'dps', 'mana', 'ranged', 'ranged', 'none', 0, 35" in rotation_profiles_sql
    assert "(3, 'marksmanship', 'dps', 'focus', 'ranged', 'ranged', 'ranged', 5, 35" in rotation_profiles_sql
    for spell_id in (19434, 56641, 53209):
        row = next(line for line in rotation_profiles_sql.splitlines() if f", {spell_id}," in line and "marksmanship" in line)
        assert row.rstrip().endswith(", 0),") or row.rstrip().endswith(", 0);")
    assert 'if (_config.ValidationRouteKind == "boss" || activeTankFocus(focus))' in mgr
    assert 'if (_config.ValidationRouteKind != "boss" && !memberIsTank && livingTankAvailable)' in mgr
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
    assert "hold_unresolved_authoritative_focus" in mgr
    assert "hold_last_known_tank_focus" in mgr
    authoritative_memory = validation_route_objective.split("if (routeFocusMemoryActive())", 1)[1].split('if (std::string(GetDungeonRole(bot)) != "tank")', 1)[0]
    assert "follow_anchor_last_known_tank_focus" not in authoritative_memory
    assert "follow_last_known_tank_focus" not in authoritative_memory
    assert "FindDungeonAnchor(bot)" not in authoritative_memory
    assert "MoveBotToPoint(state, bot, _validationRouteFocusX" not in authoritative_memory
    assert_ordered(
        authoritative_memory,
        "if (tryRouteGroupHeal(bot, nullptr))",
        "float focusDistance = bot->GetExactDist(_validationRouteFocusX, _validationRouteFocusY, _validationRouteFocusZ);",
        "unresolved_authoritative_focus_recovery",
        "hold_unresolved_authoritative_focus",
        "hold_last_known_tank_focus",
    )
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
    assert "WorldObject const* dodgeOrigin = movementOrigin && movementOrigin != bot ? movementOrigin : caster;" in validation_route_objective
    assert "bot->GetRelativeAngle(dodgeOrigin) + float(M_PI)" in validation_route_objective
    assert 'ValidationRouteMechanicProfile.find("adds")' in validation_route_objective
    assert "ValidationRouteAddTargetEntries.empty()" in validation_route_objective
    assert "creature->IsInCombat() || creature->GetVictim()" in validation_route_objective
    assert "ValidationRouteAddTargetEntries.end(), creature->GetEntry()" in validation_route_objective
    assert "BuildBossMechanicFeatures(bot, bossTarget)" not in validation_route_objective
    assert "BotActionResult pull = executor.Pull(bot, add);" in validation_route_objective
    assert "if (result == BotActionResult::NoAction)\n                    result = pull;" in validation_route_objective
    assert 'priority = victimRole == "healer" ? 3 : (victimRole == "tank" ? 2 : 1);' in validation_route_objective
    assert "priority == bestPriority && healthPct < bestHealthPct" in validation_route_objective
    assert "healthPct == bestHealthPct && guid < bestGuid" in validation_route_objective
    assert "_validationRouteAddFocusGeneration != _validationRouteGeneration" in validation_route_objective
    assert "else if (!isUsableListedAdd(bot, add))" in validation_route_objective
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
    assert "bool moved = MoveBotToPoint(state, bot, dodge.GetPositionX(), dodge.GetPositionY(), dodge.GetPositionZ())" in validation_route_objective
    assert 'moved ? "movement_check_jump" : "tactical_path_rejected"' in validation_route_objective
    assert 'action = moved ? "movement_check_jump" : "hold_tactical_path_rejected";' in validation_route_objective
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
    assert "boss_death_unconfirmed" in validation_route_objective
    assert "_validationRouteConfirmedBossDeathGuid == killedTarget->GetGUID()" in validation_route_objective
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
        "moveToRouteAnchor();",
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


def test_move_bot_to_point_only_terminalizes_strategic_route_failures():
    mgr = read(BOT_MGR)
    move_bot_to_point = function_body(mgr, "bool BotWorldPopulationMgr::MoveBotToPoint")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "bool terminalOnFailure" in mgr
    assert_ordered(
        move_bot_to_point,
        "if (_config.ValidationRouteEnable)",
        "if (terminalOnFailure)",
        "state.ValidationRouteTerminalState = true;",
        'RecordEvent(state, bot, "validation_route_recovery"',
    )
    assert route_objective.count("moveToRouteAnchor()") == 3
    assert "auto moveToRouteAnchor = [&]() -> bool" in route_objective
    assert "float floorZ = routeMap->GetHeight(bot->GetPhaseShift(), routeAnchorX, routeAnchorY, routeAnchorZ + 2.0f, true, 8.0f);" in route_objective
    assert "if (floorZ > INVALID_HEIGHT && std::fabs(floorZ - routeAnchorZ) <= 8.0f)\n            routeAnchorZ = floorZ;" in route_objective
    assert 'bool terminalOnFailure = Cohort().Config.ValidationRouteKind != "descent";' in route_objective
    assert "return MoveBotToPoint(state, bot, routeAnchorX, routeAnchorY, routeAnchorZ, terminalOnFailure);" in route_objective
    assert "MoveBotToProfileRange(state, bot, target, &profileAction)" in route_objective
    assert "hold_tactical_path_rejected" in route_objective
    assert 'moved ? "approach_target" : "tactical_path_rejected"' in route_objective
    assert "GetFirstCollisionPosition(profileAction.MinRange" not in route_objective


def test_rerun195_descent_path_probe_cannot_terminalize_before_native_jump():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    anchor_move = route_objective.split("auto moveToRouteAnchor = [&]() -> bool", 1)[1].split("auto routeFocusTankOwned", 1)[0]
    arrival = route_objective.split("if (arrivalRoute && !arrivalCombatActive)", 1)[1].split(
        'if (Cohort().Config.ValidationRouteKind != "boss"', 1
    )[0]

    assert 'bool terminalOnFailure = Cohort().Config.ValidationRouteKind != "descent";' in anchor_move
    assert "MoveBotToPoint(state, bot, routeAnchorX, routeAnchorY, routeAnchorZ, terminalOnFailure)" in anchor_move
    assert_ordered(
        arrival,
        'if (Cohort().Config.ValidationRouteKind == "descent")',
        "state.ActivePathFromX = bot->GetPositionX();",
        "bot->GetMotionMaster()->MoveJump(routeAnchorX, routeAnchorY, routeAnchorZ",
        'action = "move_to_validation_route_anchor";',
    )
    assert "state.ValidationRouteTerminalState = true;" not in anchor_move


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
    assert "return MoveBotToPoint(state, bot, x, y, floorZ, false);" in profile_range
    assert "return moveToTerrainProjectedPoint(reference->GetPositionX(), reference->GetPositionY(), reference->GetPositionZ());" in profile_range
    assert "Player* partyRangedAnchor = nullptr;" in profile_range
    assert 'std::string(GetDungeonRole(member)) == "healer"' in profile_range
    assert "member->IsWithinLOSInMap(reference)" not in profile_range
    assert "for (float spread : { 3.0f, -3.0f, 0.0f })" in profile_range
    assert "partyRangedAnchor->GetPositionX() + std::cos(tangentAngle) * spread" in profile_range
    assert "float candidateRange = reference->GetExactDist(rangedPosition);" in profile_range
    assert "bool movingOutward = distance < desiredRange - 1.0f;" in profile_range
    assert "reference->GetAngle(bot) : bot->GetAngle(reference)" in profile_range
    assert "bot->GetFirstCollisionPosition(travelDistance, relativeBearing + angleOffset)" in profile_range
    assert "reference->GetFirstCollisionPosition(desiredRange" not in profile_range
    assert 'std::string(GetDungeonRole(member)) == "tank"' in profile_range
    assert "member->GetExactDist(reference) <= 12.0f" in profile_range
    assert "float ringRanges[] = { desiredRange, std::max(minimumRingRange, desiredRange - 2.0f) };" in profile_range
    assert "for (uint8 ringIndex = 0; ringIndex < 16; ++ringIndex)" in profile_range
    assert "reference->GetPositionX() + std::cos(angle) * ringRange" in profile_range
    assert "tankAnchor->GetFirstCollisionPosition" not in profile_range
    assert "MoveChase(reference, desiredRange)" not in profile_range
    assert "float minimumCandidateRange = movingOutward" in profile_range
    assert "if (candidateRange < minimumCandidateRange" in profile_range
    assert "|| bot->GetExactDist(rangedPosition) < 1.0f)" in profile_range
    assert "if (moveToTerrainProjectedPoint(rangedPosition.GetPositionX(), rangedPosition.GetPositionY(), rangedPosition.GetPositionZ()))" in profile_range
    assert "return true;" in profile_range


def test_confirmed_direct_boss_death_emits_route_terminal_without_manifest():
    confirmed_death = function_body(read(BOT_MGR), "void BotWorldPopulationMgr::NotifyCreatureDeath")
    terminal_block = confirmed_death.split('if (_config.ValidationRouteKind == "boss")', 1)[1]
    assert 'state.ValidationRouteTerminalReason = "boss_killed";' in terminal_block
    assert 'RecordEvent(*reporterState, reporter, "validation_route_terminal"' in terminal_block
    assert_ordered(
        terminal_block,
        'state.ValidationRouteTerminalReason = "boss_killed";',
        'if (!_validationRouteManifest.empty() && _config.ValidationRouteAdvanceMode == "terminal")',
        'RecordEvent(*reporterState, reporter, "validation_route_terminal"',
    )


def test_direct_route_config_loads_mechanics_without_manifest():
    load_config = function_body(read(BOT_MGR), "void BotWorldPopulationMgr::LoadConfig")
    for key in [
        "BotWorld.ValidationRoute.AddTargetEntries",
        "BotWorld.ValidationRoute.PackTargetEntries",
        "BotWorld.ValidationRoute.HazardSourceEntry",
        "BotWorld.ValidationRoute.HazardDetectionSpellId",
        "BotWorld.ValidationRoute.HazardDamageSpellId",
        "BotWorld.ValidationRoute.HazardShape",
        "BotWorld.ValidationRoute.HazardRadiusYards",
        "BotWorld.ValidationRoute.HazardSafetyMarginYards",
        "BotWorld.ValidationRoute.ClusterRadiusYards",
    ]:
        assert key in load_config


def test_active_hazard_exit_cannot_be_preempted_by_combat_movement():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    exit_guard = route_objective.split("else if (state.ActivePathValid && state.IsMoving)", 1)[1].split(
        "Unit* caster = nullptr;", 1
    )[0]
    assert 'situation = "validation_route_mechanic";' in exit_guard
    assert 'action = "move_out_of_hazard";' in exit_guard
    assert "return true;" in exit_guard


def test_completed_hazard_exit_holds_safe_side_while_hazard_is_active():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    movement = route_objective[
        route_objective.index("auto tryValidationRouteMovementCheck"):
        route_objective.index("auto tryValidationRouteAdds")
    ]

    assert "outsideHazard && hazardActive && state.ValidationRouteDodgeUntilMs > nowMs" in movement
    assert 'action = "hold_outside_hazard";' in movement
    assert 'configuredHazardShape == "radial" ? 6000 : 3000' in movement
    assert "if (!configuredHazard\n            && state.ValidationRouteDodgeCasterGuid == caster->GetGUID()" in movement


def test_trash_swarm_waits_for_secure_tank_threat_before_dps_release():
    route = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "trashThreatControl.SecureTankCount * 10 < trashThreatControl.EngagedCount * 9" in route
    assert "trashThreatControl.TankOwnedCount * 10 >= trashThreatControl.EngagedCount * 9" in route
    assert "tankThreat >= 2000.0f && tankThreat >= highestPartyThreat * 2.5f" in route
    assert '"hold_for_secure_trash_threat"' in route
    assert '"focused_damage_during_trash_threat_build"' in route
    assert "ResolveProfileCombatAction(bot, tankFocus, 1, false)" in route
    assert "BotActionResult result = executor.Pull(bot, tankFocus);" in route
    assert 'action = moved ? "move_to_focused_trash_target"' in route
    assert "bot->InterruptNonMeleeSpells(false);" in route
    assert "pet->AttackStop();" in route
    assert '"trash_density_area_threat"' in route
    assert "trashThreatControl.EngagedCount, true" in route
    assert '"hand_of_salvation_healer_trash_threat_drop"' in route


def test_validation_route_exact_hazards_suppress_generic_boss_cast_dodges():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    movement = route_objective[
        route_objective.index("auto tryValidationRouteMovementCheck"):
        route_objective.index("auto tryValidationRouteAdds")
    ]

    assert "bool currentNodeHasConfiguredHazard = _config.ValidationRouteHazardSourceEntry != 0;" in movement
    assert "bool profileAllowsGenericCastMovement" in movement
    assert "profileAllowsGenericCastMovement || !hazardDefinitions.empty()" in movement
    assert "for (ValidationRouteManifestNode const& node : _validationRouteManifest)" not in movement
    assert 'previousDefinition->Shape == "radial"\n                    && previousHazard->IsAlive()\n                    && !bot->IsValidAttackTarget(previousHazard)' in movement
    assert 'definition->Shape == "radial"\n                    && !bot->IsValidAttackTarget(hazard)' in movement
    assert "if (!caster && !currentNodeHasConfiguredHazard && profileAllowsGenericCastMovement)\n            inspectCaster(preferredTarget);" in movement
    assert movement.count("if (!caster && !currentNodeHasConfiguredHazard && profileAllowsGenericCastMovement)") == 2


def test_holy_priest_primes_chakra_and_gates_friendly_holy_word_on_serenity():
    mgr = read(BOT_MGR)
    route = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    healer = route[route.index("auto tryRouteGroupHeal"):route.index("bool discoveryLeg")]
    profile_sql = read(ROOT / "sql/custom/world/2026_07_16_00_stonecore_wowhead_guide_rotations.sql")
    serenity_sql = read(ROOT / "sql/custom/world/2026_07_16_01_stonecore_holy_priest_serenity.sql")
    direct_cast_sql = read(ROOT / "sql/custom/world/2026_07_16_02_stonecore_holy_word_serenity_cast.sql")

    assert "healer->HasSpell(14751)" in healer
    assert "!healer->HasAura(14751)" in healer
    assert "!healer->HasAura(81208)" in healer
    assert "TryCastFriendlySpell(healer, healer, 14751)" in healer
    assert '"chakra_serenity_primed"' in healer
    assert "88625,'heal_fast','holy_word_serenity,spot_heal'" in profile_sql
    assert "`action`.`required_self_aura` = 81208" in serenity_sql
    assert "`action`.`spell_id` = 88625" in serenity_sql
    assert "`action`.`spell_id` = 88684" in direct_cast_sql
    assert "AND `action`.`spell_id` = 88625" in direct_cast_sql


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
    assert "state.MovementProgressWindowDistance += moved" in update_bot
    assert "bool movementProgress = state.MovementProgressWindowDistance >= 0.2f" in update_bot
    assert "if (movementProgress || state.MovementProgressWindowMs >= 1000)" in update_bot
    assert_ordered(
        update_bot,
        "Unit* target = state.TargetGuid.IsEmpty()",
        "bool combatOrCasting",
        "bool movementProgress",
        "bool validationRouteComplete = _config.ValidationRouteEnable && _validationRouteManifestComplete;",
        "if (!combatOrCasting && moving && !movementProgress && !validationRouteComplete)",
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
        "validation_route_pack_members",
        "validation_route_combat_links",
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

    for field in [
        "guid",
        "entry",
        "observed",
        "alive",
        "attackable",
        "evade",
        "engaged",
        "death_recorded",
        "transition_recorded",
        "victim_guid",
        "attacker_guids",
    ]:
        assert field in diagnosis_json
    assert "bot && bot->IsInWorld() && bot->GetMap()" in diagnosis_json
    assert '<< ",\\\"entry\\\":" << guid.GetEntry()' in diagnosis_json
    assert "std::sort(attackerGuids.begin(), attackerGuids.end());" in diagnosis_json
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


def test_validation_route_movement_check_requires_classified_ground_danger():
    route = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "profileAllowsCastMovement" not in route
    assert "if (!SpellLooksLikeGroundDanger(castSpell))" in route
    assert "if (!castSpell || !castSpell->CalcCastTime(candidate->getLevel()))" in route
    assert "WorldObject const* dodgeOrigin = movementOrigin && movementOrigin != bot ? movementOrigin : caster;" in route
    assert "bot->GetRelativeAngle(dodgeOrigin) + float(M_PI)" in route
    assert 'configuredHazard ? "hazard_exit_started" : "movement_check_jump"' in route
    assert 'configuredHazard ? "hazard_exit_failed" : "tactical_path_rejected"' in route
    assert 'configuredHazard ? "move_out_of_hazard" : "movement_check_jump"' in route
    assert 'configuredHazard ? "hold_hazard_exit_failed" : "hold_tactical_path_rejected"' in route


def test_validation_route_cleared_trash_regroups_to_terminal_endpoint():
    mgr = read(BOT_MGR)
    route = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    readiness_call = route.index("TryValidationRouteReadiness(state, bot, target, power, stage, activity, readinessResult)")
    endpoint_move = route.index('moved ? "move_to_terminal_route_endpoint" : "terminal_route_endpoint_path_rejected"')
    regroup_block = route[route.rfind('if (_config.ValidationRouteKind != "boss"', 0, endpoint_move):readiness_call]

    assert endpoint_move < readiness_call
    assert 'std::string(GetDungeonRole(bot)) != "tank"' in regroup_block
    assert "routeDistance > routeArrivalRadius" in regroup_block
    assert "(_validationRoutePackObservedEngagement || _validationRouteCompletedPackCount > 0)" in regroup_block
    assert "!routeFocusMemoryFresh()" in regroup_block
    assert "routeTankFocusGuid().IsEmpty()" in regroup_block
    assert "!trashClusterHasLiveMobs()" in regroup_block
    assert "!validationPartyHasActiveCombat()" in regroup_block
    assert_ordered(
        regroup_block,
        "if (tryValidationRouteMovementCheck(target))",
        "return true;",
        "MoveBotToPoint(state, bot, _config.ValidationRouteX, _config.ValidationRouteY, _config.ValidationRouteZ, true)",
    )
    assert "move_to_terminal_route_endpoint" in regroup_block


def test_validation_route_status_persists_terminal_and_boss_death_evidence():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    notify_death = function_body(mgr, "void BotWorldPopulationMgr::NotifyCreatureDeath")
    advance = function_body(mgr, "bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest")
    status = function_body(mgr, "std::string BotWorldPopulationMgr::GetStatusJson")

    assert "std::vector<ValidationRouteEvidence> _validationRouteTerminalEvidence;" in header
    assert "std::vector<ValidationRouteEvidence> _validationRouteBossDeathEvidence;" in header
    assert "_validationRouteBossDeathEvidence.push_back" in notify_death
    assert "_validationRouteTerminalEvidence.push_back" in advance
    assert '"terminal_evidence"' in status
    assert '"boss_death_evidence"' in status


def test_validation_route_boss_terminal_requires_unit_kill_provenance():
    mgr = read(BOT_MGR)
    mgr_header = read(BOT_MGR_HEADER)
    unit = read(ROOT / "src/server/game/Entities/Unit/Unit.cpp")
    notify_death = function_body(mgr, "void BotWorldPopulationMgr::NotifyCreatureDeath")
    route_objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    advance_manifest = function_body(mgr, "bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest")

    assert "void NotifyCreatureDeath(Creature* killed);" in mgr_header
    assert_ordered(
        unit,
        "victim->setDeathState(JUST_DIED);",
        "ai->JustDied(attacker);",
        "sBotWorldPopulationMgr->NotifyCreatureDeath(creature);",
    )
    assert "killed->GetEntry() != _config.ValidationRouteTargetEntry" in notify_death
    assert "_validationRouteEngagedBossGuid != killed->GetGUID()" in notify_death
    assert "_validationRouteEngagedBossGeneration != _validationRouteGeneration" in notify_death
    assert "_validationRouteEngagedBossMapId != killed->GetMapId()" in notify_death
    assert "_validationRouteEngagedBossInstanceId != killed->GetInstanceId()" in notify_death
    assert "_validationRouteConfirmedBossDeathGuid = killed->GetGUID();" in notify_death
    assert 'RecordEvent(*reporterState, reporter, "boss_killed", killed, "confirmed_unit_death"' in notify_death
    assert '_validationRouteManifestAdvanceReason = "boss_killed";' in notify_death
    assert "boss_death_unconfirmed" in route_objective
    assert "&& confirmedBossDeath" in advance_manifest


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
    assert 'state.ValidationRouteTerminalReason == "validation_trash_no_progress"' in route_objective
    assert "!persistedValidationRoutePackHasLiveMembers()" in route_objective
    assert "activeValidationRoutePackTarget()" in route_objective
    assert "failedTrashPackCanRetry" in route_objective
    assert "isEligibleTrashClusterMob(retryableFailedTrashTarget->ToCreature())" in route_objective
    assert "!validationPartyHasActiveCombat()" in route_objective
    assert '"failed_terminal_reopened_after_pack_death"' in route_objective
    assert '"failed_terminal_reopened_for_live_pack_reapproach"' in route_objective
    assert 'cohortState.ValidationRouteAnchorOverrideReason = "validation_route_disengaged_pack_reapproach";' in route_objective
    assert "cohortState.LoopRecoveryCooldownUntilMs = retryNowMs + 1000;" in route_objective
    assert 'bool routeTrashPackTarget = _config.ValidationRouteKind != "boss"' in route_objective
    assert "creature && isEligibleTrashClusterMob(creature);" in route_objective
    assert "if (routeTrashPackTarget && !botIsTank" in route_objective
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
    live_cluster_block = route_objective.split("auto isLiveTrashClusterMob", 1)[1].split(
        "auto forEachActiveValidationCohortCombatCreature", 1
    )[0]
    assert "if (!bot || !creature || !creature->IsAlive() || !creature->GetHealth())" in live_cluster_block
    assert "_validationRouteFinalTransitionGuids.find(creature->GetGUID())" in live_cluster_block
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
    assert 'std::string(GetDungeonRole(bot)) != "tank"' in route_objective
    assert 'cohortState.LastNoProgressReason = "unengaged_trash_target_repath";' in route_objective
    assert 'RecordEvent(state, bot, "validation_route_recovery", prerequisiteTarget, "unengaged_trash_target_repath"' in route_objective
    assert_ordered(
        route_objective,
        "Regroup and descent nodes must not suppress a natural pull",
        "bool arrivalCombatActive = arrivalRoute && validationPartyHasActiveCombat();",
        "if (arrivalCombatActive)",
        "enrollEngagedValidationRoutePackMembers();",
        "if (arrivalRoute && !arrivalCombatActive)",
        "bot->CombatStop(true);",
    )
    assert_ordered(
        route_objective,
        "A trash route can expose the next target",
        'if (_config.ValidationRouteKind != "boss"',
        "&& !prerequisiteTarget->IsInCombat()",
        "&& !prerequisiteTarget->GetVictim())",
        'RecordEvent(state, bot, "validation_route_recovery", prerequisiteTarget, "unengaged_trash_target_repath"',
        'markValidationRouteTrashFailed(prerequisiteTarget, "validation_trash_no_progress"',
    )
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
        "GuidSet _validationRoutePendingFinalTransitionGuids;",
        "GuidSet _validationRouteFinalTransitionGuids;",
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
        "return best;",
    )
    discovery_block = route_objective.split("auto findForwardDiscoveryTarget", 1)[1].split("auto isValidationRouteObjectiveTarget", 1)[0]
    assert "enrollValidationRoutePackMember" not in discovery_block
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
    threat_target_block = route_objective.split("auto findTrashClusterThreatTarget", 1)[1].split("auto trashClusterHasLiveMobs", 1)[0]
    assert_ordered(
        threat_target_block,
        "Creature* creature = object ? object->ToCreature() : nullptr;",
        "if (!isEligibleTrashClusterMob(creature))",
        "Unit* victim = creature->GetVictim();",
    )
    assert "_validationRoutePackMemberGuids.find(creature->GetGUID())" not in threat_target_block
    assert_ordered(
        route_objective,
        "auto forEachActiveValidationCohortCombatCreature",
        "auto isValidationCohortCombatLinked",
        "auto isNaturalValidationRoutePackMember",
        "auto enrollValidationRoutePackMember",
        "!engaged",
        "_validationRoutePackMemberGuids.insert(creature->GetGUID()).second;",
        "_validationRoutePackEngagedGuids.insert(creature->GetGUID()).second;",
        'RecordEvent(state, bot, "validation_route_pack_enrolled"',
        "auto enrollEngagedValidationRoutePackMembers",
        "enrollValidationRoutePackMember(creature, true);",
        "auto persistedValidationRoutePackHasLiveMembers",
        "_validationRoutePackDeathGuids.find(guid) == _validationRoutePackDeathGuids.end()",
        "auto trashClusterHasLiveMobs",
        "enrollEngagedValidationRoutePackMembers();",
        "persistedValidationRoutePackHasLiveMembers()",
    )
    defeated_pack_block = route_objective.split("auto recordDefeatedValidationRoutePackMembers", 1)[1].split("auto routeUsableCombatTarget", 1)[0]
    assert "_validationRoutePackEngagedGuids.find(guid) == _validationRoutePackEngagedGuids.end()" in defeated_pack_block
    assert "_validationRoutePackDeathGuids.find(guid) != _validationRoutePackDeathGuids.end()" in defeated_pack_block
    assert "_validationRoutePackTransitionGuids.find(guid) != _validationRoutePackTransitionGuids.end()" in defeated_pack_block
    assert "std::vector<ObjectGuid> memberGuids(_validationRoutePackMemberGuids.begin(), _validationRoutePackMemberGuids.end());" in defeated_pack_block
    assert "for (ObjectGuid const& guid : memberGuids)" in defeated_pack_block
    assert "bot->GetMap()->GetCreature(guid); creature && !creature->IsAlive() && !creature->GetHealth()" in defeated_pack_block
    assert 'recordValidationRouteTrashKill(creature, "enrolled_member_seen_dead")' in defeated_pack_block
    assert "if (!creature)" not in defeated_pack_block
    usable_target_block = route_objective.split("auto routeUsableCombatTarget", 1)[1].split("auto maybeValidationPrerequisiteNoProgressAssist", 1)[0]
    assert "_validationRouteFinalTransitionGuids.find(creature->GetGUID())" in usable_target_block
    assert_ordered(
        route_objective,
        'targetSearchResult = "target_seen_dead";',
        "if (!isValidationRouteCombatTarget(creature))",
        'targetSearchResult = "target_seen_activation_target";',
    )
    transition_block = route_objective.split("auto recordValidationRouteScriptedTransition", 1)[1].split("auto enrollEngagedValidationRoutePackMembers", 1)[0]
    for required in [
        "_validationRoutePackEngagedGuids.find(creature->GetGUID())",
        "resolvedScriptedTransitionAuraId(creature)",
        "_validationRoutePackTransitionGuids.insert(creature->GetGUID())",
        "_validationRouteManifestIndex + 1",
        "ScriptedEventEntries.begin()",
        "if (!declaredByFutureNode)",
        "if (discoveryLeg)",
        "_validationRoutePendingFinalTransitionGuids.insert(transitionedGuid)",
        "else",
        "_validationRouteFinalTransitionGuids.insert(transitionedGuid)",
        "_validationRouteFocusGuid == transitionedGuid",
        "cohortState.TargetGuid == transitionedGuid",
        "cohortState.LastDecisionTargetGuid == transitionedGuid",
        "member->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE)",
        "cohortState.LastCombatAttempt.TargetGuid == transitionedGuid",
        "cohortState.LastRouteProgress.TargetGuid == transitionedGuid",
        "cohortState.ActivePathValid = false",
        '"validation_route_scripted_transition"',
    ]:
        assert required in transition_block
    resolved_transition_block = route_objective.split("auto resolvedScriptedTransitionAuraId", 1)[1].split("auto isEligibleTrashClusterMob", 1)[0]
    for required in [
        "_config.ValidationRouteScriptedEventEntries.end()",
        "_config.ValidationRouteScriptedEventTransitionAuraIds[index]",
        "creature->HasAura(auraId)",
        "creature->GetVictim()",
        "creature->HasReactState(REACT_PASSIVE)",
    ]:
        assert required in resolved_transition_block
    for generic_state in ["IsValidAttackTarget", "IsInEvadeMode", "UNIT_STATE_EVADE", "hasStrictPathToValidationRouteTarget", "IsWithinLOSInMap"]:
        assert generic_state not in transition_block
    natural_pack_member_block = route_objective.split("auto isNaturalValidationRoutePackMember", 1)[1].split(
        "auto enrollValidationRoutePackMember", 1
    )[0]
    assert "_validationRoutePendingFinalTransitionGuids.find(creature->GetGUID())" in natural_pack_member_block
    assert "_validationRouteFinalTransitionGuids.find(creature->GetGUID())" in natural_pack_member_block
    assert "_validationRoutePackTransitionGuids.find(guid) == _validationRoutePackTransitionGuids.end()" in route_objective
    assert_ordered(
        mgr,
        "void BotWorldPopulationMgr::LoadValidationRouteManifest()",
        "_validationRoutePendingFinalTransitionGuids.clear();",
        "_validationRouteFinalTransitionGuids.clear();",
    )
    apply_node = function_body(mgr, "bool BotWorldPopulationMgr::ApplyValidationRouteManifestNode")
    load_manifest = function_body(mgr, "void BotWorldPopulationMgr::LoadValidationRouteManifest")
    for required in [
        "node.NavigationAnchorX = node.X",
        "node.NavigationAnchorY = node.Y",
        "node.NavigationAnchorZ = node.Z",
        "node.NavigationAnchorO = node.O",
        'ExtractJsonNumberField(routeJson, "navigation_anchor_x", node.NavigationAnchorX)',
        'ExtractJsonNumberField(routeJson, "navigation_anchor_y", node.NavigationAnchorY)',
        'ExtractJsonNumberField(routeJson, "navigation_anchor_z", node.NavigationAnchorZ)',
        'ExtractJsonNumberField(routeJson, "navigation_anchor_o", node.NavigationAnchorO)',
    ]:
        assert required in load_manifest
    assert "_config.ValidationRouteX = node.NavigationAnchorX;" in apply_node
    assert "_config.ValidationRouteY = node.NavigationAnchorY;" in apply_node
    assert "_config.ValidationRouteZ = node.NavigationAnchorZ;" in apply_node
    assert "_config.ValidationRouteO = node.NavigationAnchorO;" in apply_node
    assert "_config.ValidationRouteTargetEntry = node.NodeKind == \"discovery_leg\" ? 0 : node.TargetEntry;" in apply_node
    reset_route = function_body(mgr, "void BotWorldPopulationMgr::ResetValidationRouteRuntimeState")
    assert "state.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();" in reset_route
    assert "state.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();" in reset_route
    assert "_validationRoutePendingFinalTransitionGuids.clear();" in apply_node
    assert "_validationRouteFinalTransitionGuids.clear();" in mgr
    enrollment_scan = route_objective.split("auto enrollEngagedValidationRoutePackMembers", 1)[1].split("auto persistedValidationRoutePackHasLiveMembers", 1)[0]
    active_combat_scan = route_objective.split("auto forEachActiveValidationCohortCombatCreature", 1)[1].split(
        "auto enrollValidationRoutePackMember", 1
    )[0]
    assert "GetCombatManager().GetPvECombatRefs()" in active_combat_scan
    assert "combatReference->IsSuppressedFor(member)" in active_combat_scan
    assert "combatReference->IsSuppressedFor(other)" in active_combat_scan
    assert "combatReference && !combatReference->IsSuppressedFor(member) && !combatReference->IsSuppressedFor(creature)" in active_combat_scan
    assert "member->GetMap() != bot->GetMap()" in active_combat_scan
    assert "creature->GetMap() != bot->GetMap()" in active_combat_scan
    assert "std::unordered_set<ObjectGuid> visited" in active_combat_scan
    assert "GetThreatManager().IsThreatenedBy" not in route_objective
    assert "combatReferences.find(creature->GetGUID())" in active_combat_scan
    assert "_validationRoutePendingFinalTransitionGuids.find(creature->GetGUID())" in active_combat_scan
    assert "_validationRouteFinalTransitionGuids.find(creature->GetGUID())" in active_combat_scan
    assert "AllWorldObjectsInRange" not in enrollment_scan
    assert "Cell::VisitAllObjects" not in enrollment_scan
    assert "forEachActiveValidationCohortCombatCreature" in enrollment_scan
    assert "isNaturalValidationRoutePackMember(creature)" in enrollment_scan
    assert "!discoveryLeg && !isLiveTrashClusterMob(creature)" not in enrollment_scan
    assert "enrollValidationRoutePackMember(creature, true);" in enrollment_scan
    assert '!engaged || !isNaturalValidationRoutePackMember(creature)' in route_objective
    assert "std::vector<ObjectGuid> memberGuids" in enrollment_scan
    assert "recordValidationRouteScriptedTransition(creature);" in enrollment_scan
    assert 'RecordEvent(state, bot, "validation_route_pack_enrolled", creature, "cohort_combat_reference"' in route_objective
    assert '"route_selection"' not in route_objective
    eligible_block = route_objective.split("auto isEligibleTrashClusterMob", 1)[1].split("auto isLiveTrashClusterMob", 1)[0]
    assert "_validationRoutePackTransitionGuids.find(creature->GetGUID())" in eligible_block
    assert "_validationRouteFinalTransitionGuids.find(creature->GetGUID())" in eligible_block
    assert "focusedDiscoveryCandidate" in eligible_block
    assert "_validationRouteFocusGuid == creature->GetGUID()" in eligible_block
    assert "AttackStop" not in transition_block
    assert "CombatStop" not in transition_block
    ineligible_target_block = route_objective.split("else if (ineligibleTrashTarget)", 1)[1].split(
        "if (bot->IsInCombat() && target", 1
    )[0]
    assert '"ineligible_trash_target"' in ineligible_target_block
    assert "bot->AttackStop();" in ineligible_target_block
    assert "state.TargetGuid.Clear();" in ineligible_target_block
    assert "target = nullptr;" in ineligible_target_block
    profile_action = function_body(mgr, "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction")
    for required in [
        "auto effectiveSpellMinRange",
        "bot->GetSpellMinRangeForTarget(target, spellInfo)",
        "spellInfo->RangeEntry->Flags & SPELL_RANGE_RANGED",
        "spellMinRange += bot->GetMeleeRange(target)",
        "action.MinRange = std::max(action.MinRange, minRange)",
        "action.MinRange = effectiveSpellMinRange(*best, action.MinRange)",
        'bool selfTarget = best->Profile.TargetSelector == "self";',
        "action.MinRange = selfTarget ? 0.0f",
        "action.MaxRange = selfTarget ? 0.0f",
    ]:
        assert required in profile_action
    assert_ordered(
        route_objective,
        "_validationRoutePackMemberGuids.insert(killedTarget->GetGUID());",
        "_validationRoutePackDeathGuids.insert(killedTarget->GetGUID());",
        'RecordEvent(state, bot, "mob_killed"',
    )
    assert "!_validationRoutePackObservedEngagement" in route_objective
    assert "member->GetVictim() || !member->getAttackers().empty()" in route_objective
    assert "&& !partyHasActiveCombatUnit" in route_objective
    assert "nowMs - _validationRoutePackClearCandidateSinceMs < 2000" in route_objective
    assert "_validationRoutePackEngagedGuids.find(killedTarget->GetGUID())" in route_objective
    assert "bestAnchorTargetScore" not in route_objective
    assert '"dynamic_pack_members_live_or_unobserved"' in route_objective
    config_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildConfigJson")
    diagnosis_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")
    for field in [
        "pack_generation",
        "pack_sequence",
        "completed_pack_count",
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
        "uint64& clearCandidateSinceMs = discoveryLeg ? _validationRouteNodeClearCandidateSinceMs : _validationRoutePackClearCandidateSinceMs;",
        "if (_config.ValidationRouteAdvanceMode == \"terminal\"",
        "(discoveryLeg ? _validationRouteCompletedPackCount > 0 : _validationRoutePackObservedEngagement)",
        "&& !packHasLiveMobs",
        "&& !partyHasActiveCombatUnit",
        "&& fullCohortAtEndpoint",
        "&& nowMs - clearCandidateSinceMs >= 2000)",
        'markTrashClusterCleared("trash_cluster_cleared");',
    )
    assert_ordered(
        route_objective,
        "auto completeDiscoveredPackIfReady",
        "ledgerComplete = false;",
        "validationPartyHasActiveCombat()",
        'RecordEvent(state, bot, "validation_route_pack_terminal"',
        "++_validationRouteCompletedPackCount;",
        "++_validationRoutePackSequence;",
        "_validationRoutePackMemberGuids.clear();",
        "if (completeDiscoveredPackIfReady())",
    )
    discovered_pack_terminal = route_objective.split("auto completeDiscoveredPackIfReady", 1)[1].split("auto routeUsableCombatTarget", 1)[0]
    assert "_validationRoutePendingFinalTransitionGuids.clear()" not in discovered_pack_terminal
    assert_ordered(
        route_objective,
        "if (discoveryLeg)",
        "_validationRouteFinalTransitionGuids.insert(_validationRoutePendingFinalTransitionGuids.begin(), _validationRoutePendingFinalTransitionGuids.end());",
        "_validationRoutePendingFinalTransitionGuids.clear();",
        'markTrashClusterCleared("trash_cluster_cleared");',
        "MaybeAdvanceValidationRouteManifest();",
    )
    assert 'uint32 routeTargetNoProgressThreshold = _config.ValidationRouteKind == "boss" ? 5 : 20;' in route_objective
    assert "bool _validationRouteManifestComplete = false;" in mgr_header
    assert_ordered(
        advance_manifest,
        "if (_validationRouteManifestComplete)",
        "_validationRouteManifestAdvancePending = false;",
        "return true;",
        'bool arrivalRoute = _config.ValidationRouteKind == "travel" || _config.ValidationRouteKind == "regroup" || _config.ValidationRouteKind == "descent";',
        'bool confirmedBossDeath = _config.ValidationRouteKind != "boss"',
        "bool terminal = !arrivalRoute",
        "&& confirmedBossDeath",
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
        "moveToRouteAnchor()",
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


def test_trash_terminal_uses_current_generation_truth_after_metric_restart():
    route_objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    terminal_block = route_objective.split(
        'if (!routeTarget && _config.ValidationRouteKind != "boss" && routeDistance <= routeArrivalRadius', 1
    )[1].split('if (!routeTarget && _config.ValidationRouteKind == "boss")', 1)[0]
    direct_scan = route_objective.split("if (_config.ValidationRouteTargetEntry && !routeTarget)", 1)[1].split(
        'if (!routeTarget\n        && seenRouteTarget', 1
    )[0]
    live_scan = route_objective.split("auto trashClusterHasLiveMobs", 1)[1].split("auto markTrashClusterCleared", 1)[0]

    assert "ValidationRouteHasProgressSinceApply()" not in terminal_block
    assert "_validationRoutePackGeneration == _validationRouteGeneration && _validationRoutePackObservedEngagement" in terminal_block
    assert "++state.ValidationRouteTargetSearchMissCount >= 2" in terminal_block
    assert "!packHasLiveMobs" in terminal_block
    assert "!partyHasActiveCombatUnit" in terminal_block
    assert "fullCohortAtEndpoint" in terminal_block
    assert "nowMs - clearCandidateSinceMs >= 2000" in terminal_block

    assert_ordered(
        direct_scan,
        "bool recordedCurrentDead = _validationRoutePackGeneration == _validationRouteGeneration",
        "_validationRoutePackDeathGuids.find(creature->GetGUID())",
        "_validationRouteRecordedKillGuids.find(creature->GetGUID())",
        "if (recordedCurrentDead)",
        "continue;",
        "float distance = bot->GetExactDist(creature);",
    )
    assert "recordValidationRouteTrashKill(seenRouteTarget, \"target_seen_dead\")" in route_objective
    readiness_call = route_objective.index("TryValidationRouteReadiness(state, bot, target, power, stage, activity, readinessResult)")
    early_terminal_regroup = route_objective.index('moved ? "move_to_terminal_route_endpoint" : "terminal_route_endpoint_path_rejected"')
    assert early_terminal_regroup < readiness_call
    early_regroup_block = route_objective[route_objective.rfind('if (_config.ValidationRouteKind != "boss"', 0, early_terminal_regroup):readiness_call]
    assert 'std::string(GetDungeonRole(bot)) != "tank"' in early_regroup_block
    assert "routeDistance > routeArrivalRadius" in early_regroup_block
    assert "!routeFocusMemoryFresh()" in early_regroup_block
    assert "routeTankFocusGuid().IsEmpty()" in early_regroup_block
    assert "!trashClusterHasLiveMobs()" in early_regroup_block
    assert "!validationPartyHasActiveCombat()" in early_regroup_block
    assert_ordered(
        early_regroup_block,
        "if (tryValidationRouteMovementCheck(target))",
        "return true;",
        "MoveBotToPoint(state, bot, _config.ValidationRouteX, _config.ValidationRouteY, _config.ValidationRouteZ, true)",
    )

    for forbidden_filter in [
        "if (!bot->IsValidAttackTarget(creature))",
        "if (creature->IsInEvadeMode()",
        "if (!hasStrictPathToValidationRouteTarget(creature))",
    ]:
        assert forbidden_filter not in live_scan
    for blocker_field in ["guid", "entry", "distance", "alive", "attackable", "evade", "path", "member"]:
        assert f'\\\"{blocker_field}\\\"' in terminal_block
    for hold_field in [
        "pack_has_live_mobs",
        "party_has_active_combat",
        "full_cohort_at_endpoint",
        "quiet_elapsed_ms",
        "quiet_remaining_ms",
    ]:
        assert f'\\\"{hold_field}\\\"' in terminal_block
    for hold_reason in [
        "dynamic_pack_members_live_or_unobserved",
        "trash_cluster_party_combat_active",
        "trash_cluster_cohort_not_at_endpoint",
        "trash_cluster_terminal_mode_required",
        "trash_cluster_clear_stability_pending",
    ]:
        assert f'"{hold_reason}"' in terminal_block
    assert_ordered(
        terminal_block,
        "if (packHasLiveMobs)",
        'raw << "{\\\"guid\\\":"',
        "else",
        'raw << "null";',
    )


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
    mark_death = function_body(mgr, "void BotWorldPopulationMgr::MarkDeathDangerZone")
    assert 'sourceEntry, state.RecentDeathCount, 0u, metadataJson.c_str()' in mark_death
    assert "bool DeathEpisodeRecorded = false;" in read(BOT_MGR_HEADER)
    assert "if (!state.DeathEpisodeRecorded)" in update_bot
    assert "state.DeathEpisodeRecorded = true;" in update_bot
    assert "state.DeathEpisodeRecorded = false;" in update_bot
    recovery_success = update_bot.split("if (recovery.Recovered)", 1)[1].split("else", 1)[0]
    assert "state.DeathEpisodeRecorded = false;" in recovery_success
    assert "if (state.DeadTimer == diff)" not in update_bot


def test_validation_route_healer_uses_native_party_resurrection():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    route = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    native = function_body(mgr, "bool BotWorldPopulationMgr::TryNativePartyResurrection")
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")

    assert "bool TryNativePartyResurrection" in header
    terminal_state = route.index("if (state.ValidationRouteTerminalState")
    native_call = route.index("TryNativePartyResurrection(state, bot")
    readiness_call = route.index("TryValidationRouteReadiness(state, bot")
    assert native_call < terminal_state < readiness_call
    for gate in [
        "!healer->IsAlive()",
        "healer->IsInCombat()",
        "member->GetVictim() || !member->getAttackers().empty()",
        "!healer->IsInSameGroupWith(member)",
        "member->GetMap() != healer->GetMap()",
        "member->GetInstanceId() != healer->GetInstanceId()",
        "member->IsResurrectRequested() && !requestedByHealer",
        "memberState->NativeResurrectionPendingUntilMs > nowMs && !pendingByHealer",
    ]:
        assert gate in native
    for effect in [
        "SPELL_EFFECT_RESURRECT",
        "SPELL_EFFECT_RESURRECT_NEW",
        "SPELL_EFFECT_RESURRECT_WITH_AURA",
    ]:
        assert effect in native
    assert "healer->HasSpell(spellId)" in native
    assert "healer->IsWithinLOSInMap(deadMember)" in native
    assert "healer->IsWithinDistInMap(deadMember, resurrectionRange)" in native
    assert "healer->CastSpell(deadMember, candidate.SpellId, false)" in native
    assert "deadMember->GetSession()" in native
    assert "member->GetSession()->IsBotSession()" in native
    assert "candidate.Guid == member->GetGUID()" in native
    assert "deadMemberPriority" in native
    assert "requestedByHealer ? 2" in native
    assert "memberState->NativeResurrectionPendingUntilMs > nowMs" in native
    assert "deadMember->IsResurrectRequestedBy(healer->GetGUID())" in native
    assert "HandleResurrectResponseOpcode(response)" in native
    assert "HandleMoveTeleportAck(ack)" in native
    assert '"native_resurrection_completed"' in native
    assert "NativeResurrectionPendingUntilMs" in native
    assert "NativeResurrectionCasterGuid" in native
    assert "NativeResurrectionSpellId" in native
    assert "healer->FindCurrentSpellBySpellId(spellId)" in native
    assert 'result.Action = "validation_route_native_resurrection_casting"' in native
    assert "SPELL_ATTR8_ENFORCE_IN_COMBAT_RESSURECTION_LIMIT" in native
    assert "state.NativeResurrectionPendingUntilMs > NowMs()" in update_bot
    assert_ordered(update_bot, "state.NativeResurrectionPendingUntilMs > NowMs()", "RecoverDeadBot(state, bot)")
    assert "std::sort(resurrectionCandidates.begin(), resurrectionCandidates.end()" in native
    assert "return !left.CombatResurrection;" in native
    assert "for (ResurrectionCandidate const& candidate : resurrectionCandidates)" in native
    assert '"spell_cast_result_" + std::to_string(uint32(castResult))' in native
    assert "healer->GetSpellMaxRangeForTarget(deadMember, spellInfo)" in native
    assert "NativeResurrectionRejectedTargetGuid" in header
    assert "NativeResurrectionRejectedSpellId" in header
    assert "NativeResurrectionRejectedCastResult" in header
    assert "NativeResurrectionRetryAfterMs" in header
    assert "NativeResurrectionConsecutiveFailures" in header
    assert "rejectedCandidate" in native
    assert "CancelRemovableShapeshifts(healer)" in native
    assert 'result.Action = "cancel_shapeshift_for_native_resurrection"' in native
    assert '"native_candidates_backed_off"' in native
    assert "state.NativeResurrectionConsecutiveFailures >= 2 ? 60000 : 5000" in native
    assert 'result.Action = "validation_route_native_resurrection_failed"' not in native
    assert "ResurrectUsingRequestData" not in native
    assert "ResurrectPlayer" not in native
    assert "NearTeleportTo" not in native
    assert "TeleportTo(" not in native


def test_certified_recovery_waits_for_group_combat_and_rebuffs_after_stability():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    readiness = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteReadiness")

    assert "uint64 GroupReadinessStableSinceMs = 0;" in header
    assert "certifiedGroupCombatActive" in update_bot
    assert "instance->IsEncounterInProgress()" in update_bot
    assert_ordered(update_bot, "if (certifiedGroupCombatActive)", "RecoverDeadBot(state, bot)")
    assert "member->IsInCombat()" in readiness
    assert "member->GetVictim()" in readiness
    assert "!member->getAttackers().empty()" in readiness
    assert "state.GroupReadinessStableSinceMs = 0;" in readiness
    assert "nowMs - state.GroupReadinessStableSinceMs < 10000" in readiness


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


def test_profile_combat_resolver_prioritizes_density_actions_then_uses_rotation_fallbacks():
    mgr = read(BOT_MGR)
    resolver = function_body(
        mgr,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    executor = function_body(
        mgr,
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state, Player* bot, Unit* target, ResolvedCombatAction* actionOut, uint32 hostileCount, bool densityOnly)",
    )

    assert "candidate.Category == BotCombatActionCategory::Aoe" in resolver
    assert "candidate.Category == BotCombatActionCategory::Cleave" in resolver
    assert "candidate.Category == BotCombatActionCategory::ResourceGenerator" in resolver
    assert "bestDensityFallback" in resolver
    assert "candidate.Profile.MinEnemies > hostileCount" in resolver
    assert "hostileCount > candidate.Profile.MaxEnemies" in resolver
    assert 'candidate.RejectReason = "enemy_count_too_low";' in resolver
    assert 'candidate.RejectReason = "enemy_count_too_high";' in resolver
    assert "auto engagedWithBotParty = [bot](Unit* unit) -> bool" in resolver
    assert "player->GetGroup() == bot->GetGroup()" in resolver
    assert "&& engagedWithBotParty(unit)" in resolver
    assert "best = bestDensityArea ? bestDensityArea : (bestDensityGenerator ? bestDensityGenerator : bestDensityFallback);" in resolver
    assert "ResolveProfileCombatAction(bot, target, hostileCount, densityOnly)" in executor


def test_hostile_profile_execution_rejects_buffs_and_defers_moving_cast_time_spells():
    mgr = read(BOT_MGR)
    resolver = function_body(
        mgr,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    executor = function_body(read(ROOT / "src/server/game/Bots/BotActionExecutor.cpp"), "BotActionResult BotActionExecutor::ExecuteCombat")

    assert "candidate.Category == BotCombatActionCategory::Buff" in resolver
    assert 'candidate.RejectReason = "requires_ally_target";' in resolver
    assert "spellInfo->CalcCastTime(bot->getLevel()) > 0" in executor
    assert "bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING)" in executor
    assert_ordered(
        executor,
        "bot->StopMoving();",
        "MoveIdle();",
        "return BotActionResult::Casting;",
        "bot->CastSpell(target, action.SpellId, castArgs)",
    )


def test_feral_stampeding_roar_records_every_existing_gate_and_cast_rejection():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "feral_stampeding_roar_gate_v1" in objective
    for gate in [
        "reserved_healer_threat_handoff",
        "native_charge_ready_for_healer_threat",
        "active_path_valid",
        "state_is_moving",
        "has_spell_77761",
        "has_aura_77761",
        "cast_attempted",
        "cast_submitted",
        "failure_reason",
    ]:
        assert gate in objective
    assert "bot, bot, 77761, &failureReason" in objective
    assert '"feral_stampeding_roar_not_submitted:" + failureReason' in objective
    assert "healerThreatAttacker, diagnosticResult.c_str()" in objective
    assert_ordered(
        objective,
        'failureReason = "reserved_healer_threat_handoff";',
        'failureReason = "native_charge_ready_for_healer_threat";',
        'failureReason = "inactive_path";',
        'failureReason = "state_not_moving";',
        'failureReason = "missing_spell";',
        'failureReason = "aura_active";',
        "TryCastFriendlySpell(",
        '"validation_route_threat_pickup_diagnostic"',
        "std::string diagnosticResult",
        "if (castSubmitted)",
    )


def test_rerun168_feral_healer_threat_restores_bear_form_before_recovery():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert_ordered(
        objective,
        "if (healerThreatAttacker)",
        "state.DecisionTimer = std::min<uint32>(state.DecisionTimer, 250);",
        "if (!bot->HasAura(5487) && bot->HasSpell(5487)",
        "TryCastFriendlySpell(bot, bot, 5487)",
        '"feral_bear_form_healer_threat_before_recovery"',
        "healerThreatAttackerCount == 1",
        "TryCastCombatSpell(bot, healerThreatAttacker, 6795)",
    )


def test_rerun168_feral_reserved_handoff_preempts_stampeding_roar_gcd():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert_ordered(
        objective,
        "bool const reservedHealerThreatHandoff =",
        "state.FeralHealerThreatHandoffUntilMs > NowMs()",
        "!state.FeralHealerThreatHandoffTargetGuid.IsEmpty()",
        "!state.FeralHealerThreatHandoffAnchorGuid.IsEmpty()",
        "if (reservedHealerThreatHandoff)",
        'failureReason = "reserved_healer_threat_handoff";',
        "TryCastFriendlySpell(\n                    bot, bot, 77761, &failureReason)",
        "if (castSubmitted)",
        "if (state.FeralHealerThreatHandoffRemoteCluster",
        "TryCastCombatSpell(\n                        bot, feralTrashHandoffAnchor, 16979)",
    )


def test_feral_single_healer_threat_growl_preempts_stampeding_roar_gcd():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")

    assert "healerThreatAttackerCount == 1" in objective
    assert '"feral_growl_single_healer_threat_before_roar"' in objective
    assert_ordered(
        objective,
        "healerThreatAttackerCount == 1",
        "TryCastCombatSpell(bot, healerThreatAttacker, 6795)",
        '"feral_growl_single_healer_threat_before_roar"',
        "bool const activePathValid = state.ActivePathValid;",
        "TryCastFriendlySpell(",
        '"feral_stampeding_roar_healer_threat_reposition"',
    )


def test_rerun198_multi_healer_wave_reserves_native_pickup_before_stampeding_roar():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    gate = objective.split(
        "bool const reservedHealerThreatHandoff =", 1
    )[1].split("std::ostringstream diagnosticRaw;", 1)[0]

    assert_ordered(
        gate,
        "if (reservedHealerThreatHandoff)",
        "else if (nativeChargeReadyForHealerThreat)",
        "else if (healerThreatAttackerCount >= 3)",
        'failureReason = "multi_healer_wave_native_pickup_reserved";',
        "else if (!activePathValid)",
        "TryCastFriendlySpell(",
    )
    assert "SetVictim" not in gate
    assert "AddThreat" not in gate
    assert "NearTeleportTo" not in gate


def test_feral_generic_healer_threat_fallback_preserves_densest_cluster_target():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    fallback = objective.split("Rerun140 proved the specialized Feral handoffs", 1)[1].split(
        "Unit* threatFocus = findTrashClusterThreatTarget();", 1
    )[0]

    assert "std::vector<Unit*> HealerOwnedTargets;" in objective
    assert "trashThreatControl.HealerOwnedTargets.push_back(creature);" in objective
    assert 'bot->getClass() == CLASS_DRUID && defenseTarget' in fallback
    assert 'std::string(GetDungeonRole(defenseTarget)) == "healer"' in fallback
    assert "candidate->GetVictim() != defenseTarget" in fallback
    assert "neighbor->GetVictim() == defenseTarget" in fallback
    assert "candidate->GetExactDist2d(neighbor) <= 10.0f" in fallback
    assert_ordered(
        fallback,
        "clusterCount > densestHealerClusterCount",
        "distance < densestHealerClusterDistance",
        "guid < densestHealerClusterGuid",
        "trashThreatControl.AreaTarget =",
        "densestHealerClusterTarget;",
        "ResolveProfileCombatAction(bot, target,",
    )
    assert_ordered(
        objective,
        '"feral_growl_lingering_healer_trash_attacker"',
        "Rerun140 proved the specialized Feral handoffs",
        'action = moved ? "move_to_trash_density"',
    )


def test_rerun160_feral_local_healer_swarm_prefers_native_swipe_with_roar_fallthrough():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    recovery = objective.split("Rerun160's maximum 6025-ms exposure", 1)[1].split(
        "if (feralTrashChargeArrived && defenseTarget", 1
    )[0]

    assert "nearbyHealerOwnedCount * 2" in recovery
    assert ">= currentHealerOwnedAttackers.size()" in recovery
    assert "trashThreatControl.EngagedCount >= 12" not in recovery
    assert "TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 779)" in recovery
    assert '"feral_swipe_healer_swarm_retention_before_roar"' in recovery
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "if (nearbyHealerOwnedCount >= 2 && missingOwnedRoar",
        "TryCastFriendlySpell(bot, bot, 99)",
        '"feral_demoralizing_roar_remote_healer_trash_cluster_handoff"',
    )


def test_rerun202_feral_ordinary_local_majority_prefers_thrash_before_swipe_and_roar():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    full_recovery = objective.split(
        "Rerun160's maximum 6025-ms exposure", 1
    )[1].split("if (feralTrashChargeArrived && defenseTarget", 1)[0]
    recovery = full_recovery.split(
        "Rerun202's generation-13 Flayer swarm", 1
    )[1]

    assert "nearbyHealerOwnedCount >= 2" in full_recovery
    assert "nearbyHealerOwnedCount * 2" in full_recovery
    assert ">= currentHealerOwnedAttackers.size()" in full_recovery
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "TryCastCombatSpell(bot, nearbyHealerOwnedAttacker, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "if (nearbyHealerOwnedCount >= 2 && missingOwnedRoar",
        "TryCastFriendlySpell(bot, bot, 99)",
        '"feral_demoralizing_roar_remote_healer_trash_cluster_handoff"',
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetThreat" not in recovery
    assert "AddThreat" not in recovery
    assert "SetVictim" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun171_feral_arrived_boss_handoff_prefers_native_swipe_before_roar():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun171 completed all fourteen route nodes", 1
    )[1].split("Rerun163 reached its identity-bound remote handoff", 1)[0]

    assert "localHealerOwnedSwipeWindow" in recovery
    assert "!feralHealerHandoffActive || feralHealerHandoffArrived" in recovery
    assert "candidate->GetVictim() == densityHealer" in recovery
    assert "bot->GetExactDist2d(candidate) <= 10.0f" in recovery
    assert "localHealerOwnedSwipeCount * 2" in recovery
    assert ">= healerOwnedBeforeHandoffSwipe" in recovery
    assert "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)" in recovery
    assert '"feral_swipe_healer_swarm_retention_before_roar"' in recovery
    assert "state.DecisionTimer, 250" in recovery
    assert_ordered(
        manager,
        "Rerun171 completed all fourteen route nodes",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "Rerun163 reached its identity-bound remote handoff",
        "tryFeralRoarPickup(true)",
    )


def test_rerun198_arrived_boss_handoff_prefers_thrash_with_swipe_fallback():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun198's second failing Azil subwave", 1
    )[1].split("Rerun163 reached its identity-bound remote handoff", 1)[0]

    assert "localHealerOwnedMajority" in recovery
    assert_ordered(
        recovery,
        "feralHealerHandoffActive",
        "feralHealerHandoffArrived",
        "healerOwnedBeforeHandoffSwipe >= 2",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "localHealerOwnedMajority",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun199_arrived_handoff_thrash_accepts_local_minority_before_second_roar():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun199 then reached the same arrived handoff", 1
    )[1].split("Rerun144 proved that a successful local Roar", 1)[0]
    thrash_gate = recovery.split(
        "if (localHealerOwnedSwipeTarget", 1
    )[1].split("TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)", 1)[0]

    assert "feralHealerHandoffArrived" in thrash_gate
    assert "|| localHealerOwnedMajority" in thrash_gate
    assert "healerOwnedBeforeHandoffSwipe >= 2" in thrash_gate
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "if (localHealerOwnedSwipeTarget && bot->HasSpell(779)",
        "localHealerOwnedMajority",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
    )
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun203_fresh_boss_local_majority_prefers_thrash_before_swipe():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun203 proved the ordinary-trash Thrash correction", 1
    )[1].split("Rerun144 proved that a successful local Roar", 1)[0]
    thrash_gate = recovery.split(
        "if (localHealerOwnedSwipeTarget", 1
    )[1].split("TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)", 1)[0]

    assert "feralHealerHandoffActive && feralHealerHandoffArrived" in thrash_gate
    assert "|| localHealerOwnedMajority" in thrash_gate
    assert "healerOwnedBeforeHandoffSwipe >= 2" in thrash_gate
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun204_fresh_large_local_minority_prefers_thrash_before_roar():
    manager = read(BOT_MGR)
    recovery = manager.split(
        "Rerun204 proved that the fresh local-majority Thrash gate", 1
    )[1].split("Rerun144 proved that a successful local Roar", 1)[0]
    thrash_gate = recovery.split(
        "if (localHealerOwnedSwipeTarget", 1
    )[1].split("TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)", 1)[0]

    assert "freshLargeLocalHealerCluster = !feralHealerHandoffActive" in recovery
    assert "healerOwnedBeforeHandoffSwipe >= 12" in recovery
    assert "localHealerOwnedSwipeCount >= 2" in recovery
    assert "|| freshLargeLocalHealerCluster" in thrash_gate
    assert_ordered(
        recovery,
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 77758)",
        '"feral_thrash_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
    )
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun190_feral_local_majority_swipe_precedes_initial_roar():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun190 then proved the same damaging pickup"
    )
    recovery = objective[marker - 700 : marker + 10000]

    assert_ordered(
        recovery,
        'profile.SpecTag == "feral_druid_tank"',
        "!feralHealerHandoffActive || feralHealerHandoffArrived",
        "candidate->GetVictim() == densityHealer",
        "localHealerOwnedSwipeCount * 2",
        ">= healerOwnedBeforeHandoffSwipe",
        "TryCastCombatSpell(bot, localHealerOwnedSwipeTarget, 779)",
        '"feral_swipe_healer_swarm_retention_before_roar"',
        "tryFeralRoarPickup(true)",
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetVictim" not in recovery
    assert "AddThreat" not in recovery
    assert "NearTeleportTo" not in recovery


def test_rerun173_protection_healer_decay_and_hazard_pickup_use_native_responses():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )

    fade_marker = route.index(
        "Rerun173's Protection/Holy composition fully owned the opening corridor"
    )
    fade_branch = route[fade_marker : fade_marker + 3300]
    assert "trashThreatControl.Tank->getClass() == CLASS_PALADIN" in fade_branch
    assert "trashThreatControl.HealerTargetCount >= 4" in fade_branch
    assert "trashThreatControl.HealerTargetCount >= 9" in fade_branch
    assert "protectionPaladinHealerThreat" in fade_branch
    assert "state.DecisionTimer, 250" in fade_branch
    assert "TryCastFriendlySpell(bot, bot, 586)" in fade_branch
    assert_ordered(
        fade_branch,
        "protectionPaladinHealerThreat =",
        "trashThreatControl.HealerTargetCount >= 9",
        "state.DecisionTimer, 250",
        "TryCastFriendlySpell(bot, bot, 586)",
        '"fade_early_trash_swarm_threat_drop"',
    )

    hazard_marker = route.index(
        "Rerun173's only over-ceiling dwell began when an Azil follower"
    )
    hazard_branch = route[hazard_marker - 900 : hazard_marker + 4500]
    assert 'hazardProfile.SpecTag == "protection"' in hazard_branch
    assert "bot->getClass() == CLASS_PALADIN" in hazard_branch
    assert "areaPriority == 3 && areaTarget" in hazard_branch
    assert "state.DecisionTimer, 250" in hazard_branch
    assert "TryCastCombatSpell(bot, areaTarget, 62124)" in hazard_branch
    assert '"hand_of_reckoning_hazard_healer_pickup"' in hazard_branch
    assert "Player* hazardHealer = areaTarget->GetVictim()" in hazard_branch
    assert 'GetDungeonRole(hazardHealer) == "healer"' in hazard_branch
    assert "TryCastFriendlySpell(bot, hazardHealer, 31789)" in hazard_branch
    assert '"righteous_defense_hazard_healer_pickup"' in hazard_branch
    assert_ordered(
        hazard_branch,
        "BotClassSpecActionProfile hazardProfile",
        'hazardProfile.SpecTag == "protection"',
        "TryCastCombatSpell(bot, areaTarget, 62124)",
        '"hand_of_reckoning_hazard_healer_pickup"',
        "TryCastFriendlySpell(bot, hazardHealer, 31789)",
        '"righteous_defense_hazard_healer_pickup"',
        "auto tryFeralHazardThrashRetention",
    )


def test_rerun174_large_passive_swarm_stages_party_before_native_activation():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = route.index(
        "Rerun174 reached this passive 60-follower wave"
    )
    branch = route[marker - 800 : marker + 21000]

    assert "tankVisiblePassiveSwarmEngagedCount == 0" in branch
    assert "tankVisiblePassiveSwarmAddCount >= 24" in branch
    assert "isUsableListedAdd(densityTank, creature)" in branch
    assert "largePassiveSwarmEvidenceTarget" in branch
    assert_ordered(
        branch,
        "!IsValidationCohortMemberInOriginalInstance",
        "++largePassiveSwarmLoadedParticipants",
        "member->GetExactDist2d(densityTank) <= 18.0f",
    )
    assert "member->GetExactDist2d(densityTank) <= 18.0f" in branch
    assert "largePassiveSwarmStagedParticipants" in branch
    assert "Cohort().Config.TargetPopulation" in branch
    assert 'role != "tank"' in branch
    assert '"stage_for_large_passive_swarm_activation"' in branch
    assert '"hold_for_large_passive_swarm_activation"' in branch
    assert '"hold_large_passive_swarm_for_party_staging"' in branch
    assert "state.DecisionTimer, 250" in branch
    assert_ordered(
        branch,
        "tankVisiblePassiveSwarmAddCount",
        "bool largePassiveSwarm =",
        'role != "tank"',
        '"stage_for_large_passive_swarm_activation"',
        'role == "tank" && largePassiveSwarm',
        '"hold_large_passive_swarm_for_party_staging"',
        'activationAction.DebugName = "activate_passive_swarm"',
        '"tank_activate_passive_swarm"',
    )


def test_rerun176_remote_party_uses_tank_visible_passive_swarm_gate():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = route.index("Rerun176 proved the original staging decision")
    branch = route[marker : marker + 17000]

    assert_ordered(
        branch,
        "Trinity::AllWorldObjectsInRange tankVisibleCheck(",
        "densityTank, 45.0f",
        "isUsableListedAdd(densityTank, creature)",
        "++tankVisiblePassiveSwarmAddCount",
        "tankVisiblePassiveSwarmEngagedCount == 0",
        "tankVisiblePassiveSwarmAddCount >= 24",
        "largePassiveSwarmEvidenceTarget",
        'role != "tank"',
        "stagingReference",
        '"stage_for_large_passive_swarm_activation"',
        'role == "tank" && pendingSwarmActivation',
        'activationAction.DebugName = "activate_passive_swarm"',
    )


def test_rerun176_native_charge_preempts_stampeding_roar_and_small_pack_decay():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    charge = objective.split(
        "bool nativeChargeReadyForHealerThreat = false;", 1
    )[1].split("std::ostringstream diagnosticRaw;", 1)[0]
    secure = objective.split(
        "Rerun176 then recorded 45 of generation 13's 53", 1
    )[1].split("Rerun112 localized the all-hostile retention failure", 1)[0]

    assert "bot->GetSpellHistory()->HasGlobalCooldown(" in charge
    assert "bot->GetSpellHistory()->IsReady(chargeInfo)" in charge
    assert "HasPowerForSpell(bot, chargeInfo)" in charge
    assert_ordered(
        charge,
        "nativeChargeReadyForHealerThreat =",
        "if (reservedHealerThreatHandoff)",
        "else if (nativeChargeReadyForHealerThreat)",
        'failureReason = "native_charge_ready_for_healer_threat";',
        "TryCastFriendlySpell(",
    )
    assert "trashThreatControl.EngagedCount >= 3" in secure
    assert "tankOwnsTrashMajority && insecureTrashSwarm" in secure
    assert "TryCastCombatSpell(bot, feralSecureMarginTarget, 779)" in secure


def test_rerun177_moderate_healer_subwave_ignores_tank_owned_cohort_size():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun177's only failing dwell was an eleven-healer-owned"
    )
    branch = objective[marker : marker + 1200]

    assert "healerOwnedCount >= 3 && healerOwnedCount < 12" in branch
    assert "nearbyHealerOwnedCount >= 1" in branch
    assert "engagedAddCount < 12" not in branch
    assert_ordered(
        branch,
        "bool immediateModerateWavePickup =",
        "healerOwnedCount >= 3 && healerOwnedCount < 12",
        "nearbyHealerOwnedCount >= 1",
        "bool usefulLocalPickup = immediateModerateWavePickup",
    )


def test_rerun178_tank_proof_drives_remote_passive_swarm_staging():
    manager = read(BOT_MGR)
    objective = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun178 proved that recomputing the tank-visible staging fact"
    )
    shared = objective[marker - 1300 : marker + 19000]
    pre_anchor = objective[objective.index("bool sharedLargePassiveSwarmStaging =") : marker]

    assert "ValidationRouteLargePassiveSwarmStagingGeneration" in pre_anchor
    assert "&& !sharedLargePassiveSwarmStaging" in pre_anchor
    assert_ordered(
        shared,
        "bool tankViewProvesLargePassiveSwarm =",
        "tankVisiblePassiveSwarmEngagedCount == 0",
        "tankVisiblePassiveSwarmAddCount >= 24",
        'if (role == "tank" && tankViewProvesLargePassiveSwarm)',
        "Party().ValidationRouteLargePassiveSwarmStaging = true",
        "bool largePassiveSwarm = densityTank",
        "&& sharedLargePassiveSwarmStaging",
        'role != "tank"',
        "float stagingAngle =",
        "FOLLOW_MOTION_TYPE",
        "MoveFollow(",
        '"stage_for_large_passive_swarm_activation"',
        'role == "tank" && pendingSwarmActivation',
        'activationAction.DebugName = "activate_passive_swarm"',
    )
    reset = function_body(
        manager,
        "void BotWorldPopulationMgr::ResetValidationRouteBossAddDensityState",
    )
    assert "ValidationRouteLargePassiveSwarmStaging = false" in reset
    assert "ValidationRouteLargePassiveSwarmStagingGeneration = 0" in reset


def test_rerun179_azil_seismic_shards_fail_closed_without_an_empty_seat():
    script = read(AZIL_SCRIPT)
    mount = script[script.index("case EVENT_SEISMIC_SHARD_MOUNT:") :]
    mount = mount[: mount.index("default:")]
    fill_path = function_body(script, "void FillPath")

    assert "SeatMap::const_iterator seat = vehicle->GetNextEmptySeat(0, false);" in mount
    assert "if (seat != vehicle->Seats.end())" in mount
    assert "me->EnterVehicle(highPriestAzil, seat->first);" in mount
    assert "me->DespawnOrUnsummon();" in mount
    assert "vehicle->GetNextEmptySeat(0, false)->first" not in mount
    assert fill_path.count("path.push_back(point);") == 3


def test_rerun180_large_feral_wave_retires_moderate_pickup_reservation():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun180 captured a moderate reservation while eleven Azil"
    )
    promotion = objective[marker : marker + 2400]
    active_marker = objective.index("bool activeSwarmPickupEligible =")
    active = objective[active_marker : active_marker + 650]

    assert "healerOwnedCount >= 12 && nearbyHealerOwnedCount < 2" in promotion
    assert "state.FeralActiveSwarmPickupAnchorGuid.Clear();" in promotion
    assert "state.FeralActiveSwarmPickupUntilMs = 0;" in promotion
    assert "state.FeralActiveSwarmPickupAttempted = false;" in promotion
    assert "state.FeralActiveSwarmPickupArrived = false;" in promotion
    assert_ordered(
        promotion,
        "state.FeralActiveSwarmPickupAnchorGuid.Clear();",
        "state.FeralActiveSwarmPickupUntilMs = 0;",
        "MoveBotToPoint(state, bot,",
        '"feral_move_to_healer_for_split_swarm_pickup"',
    )
    assert "observedListedAttackerCount(densityHealer) >= 3" in active
    assert "observedListedAttackerCount(densityHealer) < 12" in active


def test_rerun175_feral_healer_target_preempts_tank_owned_density():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = route.index(
        "Rerun175's only 14 eligible healer-exposure samples"
    )
    branch_start = route.rindex(
        "bool feralCurrentHealerThreat =", 0, marker
    )
    branch = route[branch_start : marker + 12000]

    assert "feralCurrentHealerThreat" in branch
    assert_ordered(
        branch,
        "bool feralCurrentHealerThreat =",
        "bool feralTankOwnedDensitySelected = false;",
        "&& !feralCurrentHealerThreat",
        "if (!feralTankOwnedDensitySelected",
        "trashThreatControl.HealerOwnedTargets",
        "trashThreatControl.AreaTarget =",
        "ResolveProfileCombatAction(bot, target",
    )


def test_feral_large_tank_owned_trash_wave_prefers_density_before_freshness():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    selector = objective.split("Rerun142 proved continuous aura-fresh", 1)[1].split(
        "Rerun140 proved the specialized Feral handoffs", 1
    )[0]
    ordering = selector.split("if (!densestTankOwnedClusterTarget", 1)[1]

    assert "std::vector<Unit*> TankOwnedTargets;" in objective
    assert "trashThreatControl.TankOwnedTargets.push_back(creature);" in objective
    assert "trashThreatControl.EngagedCount >= 12" in selector
    assert "tankOwnsTrashMajority" in selector
    assert "candidate->GetVictim() != trashThreatControl.Tank" in selector
    assert "neighbor->GetVictim() == trashThreatControl.Tank" in selector
    assert "candidate->GetExactDist2d(neighbor) <= 10.0f" in selector
    assert "!candidate->HasAura(77758, bot->GetGUID())" in selector
    assert_ordered(
        ordering,
        "clusterCount > densestTankOwnedClusterCount",
        "missingThrash",
        "distance < densestTankOwnedClusterDistance",
        "guid < densestTankOwnedClusterGuid",
        "trashThreatControl.AreaTarget =",
        "densestTankOwnedClusterTarget;",
        "feralTankOwnedDensitySelected = true;",
    )
    assert_ordered(
        objective,
        "Rerun142 proved continuous aura-fresh",
        "Rerun140 proved the specialized Feral handoffs",
        "ResolveProfileCombatAction(bot, target,",
    )


def test_feral_secure_margin_targets_remote_insecure_cluster_before_swipe():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    selector = objective.split("Unit* feralSecureMarginTarget = nullptr;", 1)[1].split(
        "Rerun112 localized the all-hostile retention failure", 1
    )[0]

    assert "std::vector<Unit*> InsecureTankOwnedTargets;" in objective
    assert "trashThreatControl.InsecureTankOwnedTargets.push_back(creature);" in objective
    assert "tankThreat >= 2000.0f" in objective
    assert "tankThreat >= highestPartyThreat * 2.5f" in objective
    assert "candidate->GetVictim() != bot" in selector
    assert "neighbor->GetVictim() == bot" in selector
    assert "candidate->GetExactDist2d(neighbor) <= 10.0f" in selector
    assert "state.FeralHealerThreatHandoffUntilMs > NowMs()" in selector
    assert "!feralHealerHandoffPending" in selector
    assert_ordered(
        selector,
        "clusterCount > feralSecureMarginClusterCount",
        "distance < feralSecureMarginDistance",
        "guid < feralSecureMarginGuid",
        "MoveBotToProfileRange(",
        '"feral_approach_insecure_trash_threat_cluster"',
        "TryCastCombatSpell(bot, feralSecureMarginTarget, 779)",
        '"feral_swipe_secure_trash_threat_margin"',
    )


def test_trash_tactical_focus_and_next_encounter_terminal_ownership_stay_separate():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    active_combat = objective.split("auto validationPartyHasActiveCombat", 1)[1].split(
        "auto isBoundedTerminalPartyCombatTarget", 1
    )[0]
    bounded_terminal = objective.split("auto isBoundedTerminalPartyCombatTarget", 1)[1].split(
        "auto findBoundedTerminalPartyCombatTarget", 1
    )[0]
    area_focus = objective.split("target = trashThreatControl.AreaTarget;", 1)[1].split(
        "ResolvedCombatAction areaAction", 1
    )[0]
    terminal_start = objective.index("bool packHasLiveMobs = trashClusterHasLiveMobs();")
    terminal = objective[terminal_start : objective.index("if (terminalCombatTarget)", terminal_start)]

    assert "isImmediateNextValidationRouteEncounterMember" in active_combat
    assert "transferImmediateNextEncounter" in active_combat
    assert "isImmediateNextValidationRouteEncounterMember(creature)" in bounded_terminal
    assert "isImmediateNextValidationRouteBossTarget(creature)" not in bounded_terminal
    assert "!isImmediateNextValidationRouteEncounterMember(areaCreature)" in area_focus
    assert "isEligibleTrashClusterMob(areaCreature)" not in area_focus
    assert 'Cohort().Config.ValidationRouteKind == "boss"' not in area_focus
    assert "rememberValidationRouteFocus(target);" in area_focus
    assert_ordered(
        terminal,
        "bool packHasLiveMobs = trashClusterHasLiveMobs();",
        "validationPartyHasActiveCombat(!packHasLiveMobs)",
        "!packHasLiveMobs && partyHasActiveCombatUnit",
    )


def test_feral_boss_remote_handoff_uses_collision_safe_eight_yard_intercept():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    handoff = objective.split("Rerun141 left one generation-14 boss-handoff attacker", 1)[1].split(
        'RecordEvent(state, bot, "boss_add_density", movementAnchor,', 1
    )[0]

    assert "state.FeralHealerThreatHandoffRemoteCluster" in handoff
    assert "movementAnchor->GetFirstCollisionPosition(" in handoff
    assert "8.0f" in handoff
    assert "movementAnchor->GetAngle(bot)" in handoff
    assert "- movementAnchor->GetOrientation()" in handoff
    assert_ordered(
        handoff,
        "Position remoteRoarIntercept;",
        "movementX =",
        "movementY =",
        "movementZ =",
        "continuingRemotePath",
        "MoveBotToPoint(state, bot,",
        "movementX, movementY, movementZ",
    )


def test_feral_initial_boss_split_handoff_starts_at_same_roar_intercept():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    initial_handoff = objective.split(
        "Rerun150 proved the continuation's collision-safe Roar", 1
    )[1].split("if (remoteClusterRemains)", 1)[0]

    assert "remoteClusterAnchor->GetFirstCollisionPosition(" in initial_handoff
    assert "8.0f" in initial_handoff
    assert "remoteClusterAnchor->GetAngle(bot)" in initial_handoff
    assert "- remoteClusterAnchor->GetOrientation()" in initial_handoff
    assert "remoteClusterAnchor->GetPositionX()" not in initial_handoff
    assert "remoteClusterAnchor->GetPositionY()" not in initial_handoff
    assert "remoteClusterAnchor->GetPositionZ()" not in initial_handoff
    assert_ordered(
        initial_handoff,
        "Position remoteRoarIntercept;",
        "splitHandoffX =",
        "splitHandoffY =",
        "splitHandoffZ =",
        "bool splitClusterHandoff = remoteClusterRemains",
        "MoveBotToPoint(state, bot,",
        "splitHandoffX, splitHandoffY, splitHandoffZ",
    )


def test_feral_arrived_handoff_retries_roar_before_post_roar_area_threat():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    post_roar = objective.split("Rerun144 proved that a successful local Roar", 1)[1].split(
        "Rerun106 isolated two Azil split waves", 1
    )[0]

    assert "candidate->GetVictim() == densityHealer" not in post_roar
    assert "bot->GetExactDist2d(candidate) <= 10.0f" in post_roar
    assert "candidate->HasAura(99, bot->GetGUID())" in post_roar
    assert (
        "postRoarAreaThreatReady = feralHealerHandoffActive\n"
        "            && feralHealerHandoffArrived"
    ) in post_roar
    assert "healerOwnedAfterRoar >= 2" in post_roar
    assert "localRoarCoveredCount >= 2" in post_roar
    assert "localRoarCoveredCount * 2 >= healerOwnedAfterRoar" in post_roar
    assert "ResolveProfileCombatAction(" in post_roar
    assert "addCount, true, 0, true" in post_roar
    assert "ExecuteProfileCombatAction(" in post_roar
    assert '"feral_post_roar_area_threat_retention"' in post_roar
    assert '"feral_hold_post_roar_area_threat_retention"' in post_roar
    assert_ordered(
        objective,
        "Rerun163 reached its identity-bound remote handoff",
        "feralHealerHandoffActive && feralHealerHandoffArrived",
        "tryFeralRoarPickup(true)",
        "Rerun144 proved that a successful local Roar",
        "feral_post_roar_area_threat_retention",
        "Rerun106 isolated two Azil split waves",
        "// A remote Charge must not abandon a useful local healer-owned cluster.",
    )

    retry = objective.split(
        "Rerun163 reached its identity-bound remote handoff", 1
    )[1].split("Rerun144 proved that a successful local Roar", 1)[0]
    assert "acceptance" not in retry
    assert "threshold" not in retry
    assert "tryFeralRoarPickup(true)" in retry
    assert "return true;" in retry


def test_rerun181_prearrival_handoff_does_not_spend_post_roar_swipe_gcd():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    post_roar = objective.split("Rerun144 proved that a successful local Roar", 1)[1].split(
        "Rerun106 isolated two Azil split waves", 1
    )[0]

    assert_ordered(
        post_roar,
        "Rerun181 showed this resolver could spend native Swipe",
        "postRoarAreaThreatReady = feralHealerHandoffActive",
        "&& feralHealerHandoffArrived",
        "if (postRoarAreaThreatReady)",
        '"feral_post_roar_area_threat_retention"',
    )


def test_rerun182_shared_passive_swarm_proof_keeps_native_tank_follow():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun182 proved the generation-scoped tank observation"
    )
    branch = objective[marker : marker + 17000]
    staging = branch[
        branch.index('if (largePassiveSwarm && role != "tank"') :
        branch.index('if (role == "tank" && pendingSwarmActivation')
    ]

    assert "cohortSwarmActive && densityTank" not in branch[:800]
    assert_ordered(
        branch,
        "bool largePassiveSwarm = densityTank",
        "&& sharedLargePassiveSwarmStaging",
        "member->GetExactDist2d(densityTank) <= 18.0f",
        'role != "tank"',
        "FOLLOW_MOTION_TYPE",
        "state.ActivePathToX = densityTank->GetPositionX()",
        "MoveFollow(",
        "densityTank, stagingRadius, stagingAngle",
        '"stage_for_large_passive_swarm_activation"',
    )
    assert "MoveBotToPoint" not in staging
    assert "largePassiveSwarmPartyStaged" in branch
    assert 'role == "tank" && pendingSwarmActivation' in branch
    assert 'activationAction.DebugName = "activate_passive_swarm"' in branch


def test_rerun196_shared_passive_swarm_proof_resolves_remote_staging_tank():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun195 proved that the shared large-passive-swarm fact"
    )
    branch = objective[
        objective.index("bool sharedLargePassiveSwarmStaging =") :
        objective.index("bool passiveSwarmActivationNotActionable")
    ]

    assert marker > objective.index("bool sharedLargePassiveSwarmStaging =")
    assert_ordered(
        branch,
        "bool sharedLargePassiveSwarmStaging =",
        "bool swarmDefenseActive = highDensityPhase || cohortSwarmActive",
        "|| sharedLargePassiveSwarmStaging;",
        "if (swarmDefenseActive)",
        'if (!densityTank && memberRole == "tank")',
        "densityTank = member;",
        "bool largePassiveSwarm = densityTank",
        "&& sharedLargePassiveSwarmStaging",
        'if (largePassiveSwarm && role != "tank"',
        "MoveFollow(",
        'activationAction.DebugName = "activate_passive_swarm"',
    )
    assert "member->GetExactDist2d(densityTank) <= 18.0f" in branch
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun183_healer_owned_stable_swarm_path_revalidates_early():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun183 exposed one identity-stable healer-owned follower"
    )
    branch = objective[marker - 500 : marker + 2300]

    assert_ordered(
        branch,
        "auto continueStableFeralSwarmApproach",
        "bool selectedHealerOwned = densityHealer && selectedAdd",
        "selectedAdd->GetVictim() == densityHealer",
        "selectedHealerOwned ? 750 : 2000",
        "pathAgeMs <= stableApproachLimitMs",
        "selectedAdd->GetExactDist2d(state.ActivePathToX, state.ActivePathToY)",
    )
    assert "cohortSwarmActive" in branch


def test_rerun184_feral_prepares_form_before_native_swarm_activation():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun184 activated all 59 staged followers onto the Feral"
    )
    branch = objective[marker - 700 : marker + 5200]

    assert_ordered(
        branch,
        "feralPassiveSwarmBearFormMissing",
        'profile.SpecTag == "feral_druid_tank"',
        "largePassiveSwarm && passiveSwarmClusterAnchor",
        "!bot->HasAura(5487)",
        "TryEnsurePersistentCombatSetup(",
        "feralPassiveSwarmBearFormGcdPending",
        "HasGlobalCooldown(",
        '"feral_prepare_bear_form_before_passive_swarm_activation"',
        '"feral_hold_bear_form_gcd_before_passive_swarm_activation"',
        'if (role == "tank" && largePassiveSwarm',
        'activationAction.DebugName = "activate_passive_swarm"',
    )
    assert "state.DecisionTimer, 250" in branch
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun185_protection_remote_boss_add_rescue_precedes_area_approach():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun185 completed Azil but localized 554 healer-target"
    )
    branch = objective[marker - 900 : marker + 6500]

    assert_ordered(
        branch,
        "if (approach)",
        'profile.SpecTag == "protection"',
        "densityDefenseTarget == densityHealer",
        "add->GetVictim() == densityHealer",
        "TryCastFriendlySpell(bot, densityHealer, 31789)",
        '"righteous_defense_healer_before_area_approach"',
        "TryCastCombatSpell(bot, add, 62124)",
        '"hand_of_reckoning_healer_before_area_approach"',
        "healerAttackerCount >= 2",
        "TryCastCombatSpell(bot, add, 31935)",
        '"avengers_shield_healer_before_area_approach"',
        "continueStableFeralSwarmApproach(add)",
        "MoveBotToProfileRange(state, bot, add, &immediateAreaThreat)",
    )
    assert branch.count("state.DecisionTimer, 250);") >= 3
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun186_boss_handoff_enrolls_remaining_healer_owned_newcomer():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    branch = objective.split(
        "Rerun156 proved the boss handoff discarded a still-valid Azil", 1
    )[1].split("bool feralHealerRemoteHandoffValid", 1)[0]
    fallback = branch.split(
        "Rerun186's first Roar started a bounded split-cluster handoff", 1
    )[1]

    assert_ordered(
        branch,
        "feralHealerHandoffAnchor->GetExactDist2d(candidate)",
        "<= 10.0f",
        "if (!reboundAnchor)",
        "float reboundDistance = std::numeric_limits<float>::max();",
        "bot->GetExactDist(candidate)",
        "state.FeralHealerThreatHandoffAnchorGuid =",
    )
    assert "candidate->GetVictim() == densityHealer" in fallback
    assert "bot->IsValidAttackTarget(candidate)" in fallback
    assert "distance < reboundDistance" in fallback
    assert "guid < reboundGuid" in fallback
    assert "FeralHealerThreatHandoffUntilMs =" not in fallback
    assert "SetThreat" not in fallback
    assert "SetVictim" not in fallback
    assert "NearTeleportTo" not in fallback


def test_rerun188_lingering_feral_healer_attacker_uses_native_swipe_after_growl():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun188 reduced Azil's final healer-owned wave to one follower"
    )
    branch = objective[marker - 1900 : marker + 3200]

    assert_ordered(
        branch,
        "observedListedAttackerCount(densityHealer) == 1",
        "TryCastCombatSpell(bot, healerOwnedAdd, 6795)",
        '"feral_growl_lingering_healer_swarm_attacker"',
        "TryCastCombatSpell(bot, healerOwnedAdd, 779)",
        '"feral_swipe_lingering_healer_swarm_attacker"',
        "add = healerOwnedAdd",
    )
    assert "state.DecisionTimer, 250" in branch
    assert "SetThreat" not in branch
    assert "SetVictim" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun189_protection_holy_wrath_uses_existing_self_centered_area_gate():
    migration = read(PROTECTION_HOLY_WRATH_SELF_SQL)
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    area_gate = objective.split(
        "On a multi-target wave, establish area threat before spending", 1
    )[1].split("if (role == \"tank\" && densityHealer", 1)[0]

    assert "SET a.`target_selector` = 'self'" in migration
    assert "p.`class_id` = 2" in migration
    assert "p.`spec_tag` = 'protection'" in migration
    assert "p.`role` = 'tank'" in migration
    assert "a.`spell_id` = 2812" in migration
    assert "min_enemies" not in migration
    assert "priority_bucket" not in migration
    assert_ordered(
        area_gate,
        "immediateAreaThreat.TargetGuid == bot->GetGUID()",
        "selfCenteredTargets >= 2",
        "bot->GetExactDist2d(add) <= 10.0f",
        "ExecuteProfileCombatAction(",
    )
    assert "SetThreat" not in area_gate
    assert "SetVictim" not in area_gate
    assert "NearTeleportTo" not in area_gate


def test_rerun192_protection_prefers_profile_self_centered_area_for_local_healer_wave():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    objective = function_body(
        mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    area_gate = objective.split(
        "Rerun191 captured fifteen Azil followers on the healer", 1
    )[1].split("if (role == \"tank\" && densityHealer", 1)[0]
    resolver = function_body(
        mgr,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )

    assert "bool selfCenteredOnly = false" in header
    assert_ordered(
        area_gate,
        "localProtectionHealerOwnedCount >= 2",
        "localProtectionHealerOwnedCount * 2",
        ">= protectionHealerAttackerCount",
        "ResolveProfileCombatAction(",
        "preferSelfCenteredProtectionArea",
        "!immediateAreaThreat.Valid && preferSelfCenteredProtectionArea",
    )
    assert 'candidate.Profile.TargetSelector != "self"' in resolver
    assert 'candidate.RejectReason = "self_centered_action_required"' in resolver
    assert "preferSelfCenteredProtectionArea);" in area_gate
    assert "SetThreat" not in area_gate
    assert "SetVictim" not in area_gate
    assert "NearTeleportTo" not in area_gate


def test_rerun193_protection_distributes_native_pickup_before_area_gcd():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    boss_marker = objective.index(
        "Rerun192 showed two distinct Protection starvation paths"
    )
    boss_branch = objective[boss_marker - 300 : boss_marker + 5600]
    trash_marker = objective.index(
        "Rerun170 retained 17 eligible healer-target samples"
    )
    trash_branch = objective[trash_marker : trash_marker + 4300]

    assert_ordered(
        boss_branch,
        'profile.SpecTag == "protection"',
        "protectionHealerAttackerCount >= 2",
        "TryCastFriendlySpell(bot, densityHealer, 31789)",
        '"righteous_defense_healer_before_area_gcd"',
        "Rerun191 captured fifteen Azil followers on the healer",
        "ResolveProfileCombatAction(",
    )
    assert "state.DecisionTimer, 250" in boss_branch
    assert_ordered(
        trash_branch,
        "bool healerTauntRepeatsCurrentTarget = true;",
        "attacker->GetGUID() == state.TargetGuid",
        "&& !repeatsCurrentTarget",
        "TryCastCombatSpell(bot, healerTauntTarget, 62124)",
    )
    assert "SetThreat" not in boss_branch + trash_branch
    assert "SetVictim" not in boss_branch + trash_branch
    assert "NearTeleportTo" not in boss_branch + trash_branch


def test_rerun198_protection_uses_native_healer_immunity_before_area_starvation():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun197 captured the complementary native-rescue"
    )
    rescue = objective[marker - 1300 : marker + 3800]

    assert_ordered(
        rescue,
        'TryCastFriendlySpell(bot, densityHealer, 31789)',
        '"righteous_defense_healer_before_area_gcd"',
        "protectionHealerAttackerCount >= 5",
        "!densityHealer->HasAura(1022)",
        "TryCastFriendlySpell(bot, densityHealer, 1022)",
        '"hand_of_protection_healer_before_area_gcd"',
        "Rerun191 captured fifteen Azil followers on the healer",
        "ResolveProfileCombatAction(",
    )
    assert "state.DecisionTimer, 250" in rescue
    lower_emergency = objective.index('"hand_of_protection_healer_emergency"')
    assert marker < lower_emergency
    assert "SetThreat" not in rescue
    assert "SetVictim" not in rescue
    assert "NearTeleportTo" not in rescue


def test_rerun200_protection_uses_avengers_shield_after_direct_taunt_rejection():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun200's only strict role failure was a remote two-follower Azil"
    )
    rescue = objective[marker - 1400 : marker + 3000]

    assert_ordered(
        rescue,
        "TryCastCombatSpell(bot, add, 62124)",
        '"hand_of_reckoning_add_pickup"',
        'profile.SpecTag == "protection"',
        "densityDefenseTarget == densityHealer",
        "addVictim == densityHealer",
        "observedListedAttackerCount(densityHealer) >= 2",
        "TryCastCombatSpell(bot, add, 31935)",
        '"avengers_shield_healer_add_pickup"',
        '"consecration_healer_pickup"',
    )
    assert "state.DecisionTimer, 250" in rescue
    assert "SetThreat" not in rescue
    assert "SetVictim" not in rescue
    assert "NearTeleportTo" not in rescue


def test_rerun200_protection_rescue_preserves_existing_area_approach_chain():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun200's only strict role failure was a remote two-follower Azil"
    )
    rescue = objective[marker - 1800 : marker + 4200]

    assert_ordered(
        rescue,
        '"righteous_defense_healer_pickup"',
        '"hand_of_reckoning_add_pickup"',
        '"avengers_shield_healer_add_pickup"',
        '"consecration_healer_pickup"',
    )
    area_marker = objective.index(
        "Rerun185 completed Azil but localized 554 healer-target"
    )
    area_rescue = objective[area_marker - 900 : area_marker + 6500]
    assert_ordered(
        area_rescue,
        '"righteous_defense_healer_before_area_approach"',
        '"hand_of_reckoning_healer_before_area_approach"',
        '"avengers_shield_healer_before_area_approach"',
        "MoveBotToProfileRange(state, bot, add, &immediateAreaThreat)",
    )


def test_rerun201_protection_honors_ready_local_majority_area_before_remote_approach():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun201 proved one exception already encoded by the resolver"
    )
    area = objective[marker - 3200 : marker + 10500]

    assert_ordered(
        area,
        "localProtectionHealerOwnedCount >= 2",
        "localProtectionHealerOwnedCount * 2",
        ">= protectionHealerAttackerCount",
        "preferSelfCenteredProtectionArea",
        "uint32 selfCenteredTargets = 0",
        "bool preferredLocalProtectionAreaReady",
        "preferSelfCenteredProtectionArea",
        "immediateAreaThreat.TargetGuid == bot->GetGUID()",
        "selfCenteredTargets >= 2",
        "bool selfCenteredAreaReady",
        "preferredLocalProtectionAreaReady",
        "|| bot->GetExactDist2d(add) <= 10.0f",
        "if (approach)",
        "MoveBotToProfileRange(state, bot, add, &immediateAreaThreat)",
        "ExecuteProfileCombatAction(",
    )
    assert "TryCastCombatSpell(bot, add, 31935)" in area
    assert "SetThreat" not in area
    assert "SetVictim" not in area
    assert "NearTeleportTo" not in area


def test_rerun201_local_majority_area_keeps_remote_and_non_protection_movement_contracts():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun201 proved one exception already encoded by the resolver"
    )
    area = objective[marker - 1200 : marker + 10500]

    assert "preferSelfCenteredProtectionArea" in area
    assert "preferredLocalProtectionAreaReady" in area
    assert "!densityDefenseTarget" in area
    assert "bot->GetExactDist2d(add) <= 10.0f" in area
    assert "MoveBotToProfileRange(state, bot, add, &immediateAreaThreat)" in area
    assert "preferSelfCenteredProtectionArea);" in area
    assert "SetThreat" not in area
    assert "SetVictim" not in area
    assert "NearTeleportTo" not in area


def test_rerun194_feral_remote_healer_wave_charges_before_local_minority_roar():
    objective = function_body(
        read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective"
    )
    marker = objective.index(
        "Rerun193 completed every strict route objective"
    )
    recovery = objective[marker - 700 : marker + 5200]

    assert "healerOwnedBeforeCharge >= 1" in recovery
    assert "localHealerOwnedBeforeCharge * 2 < healerOwnedBeforeCharge" in recovery
    assert "candidate->GetVictim() != densityHealer" in recovery
    assert "bot->GetExactDist(candidate) <= 8.0f" in recovery
    assert "candidate->GetExactDist2d(neighbor) <= 10.0f" in recovery
    assert_ordered(
        recovery,
        "clusterCount > remoteHealerWaveClusterCount",
        "distance < remoteHealerWaveDistance",
        "guid < remoteHealerWaveGuid",
        "TryCastCombatSpell(bot, remoteHealerWaveChargeTarget, 16979)",
        '"feral_charge_remote_healer_wave_before_roar"',
        "state.FeralChargePickupUntilMs = NowMs() + 2500;",
        "if (localHealerOwnedBeforeCharge >= 2",
        "tryFeralRoarPickup(feralHealerHandoffArrived)",
    )
    assert "state.DecisionTimer, 250" in recovery
    assert "SetThreat" not in recovery
    assert "SetVictim" not in recovery
    assert "NearTeleportTo" not in recovery


def test_profile_los_failure_is_recorded_before_existing_range_recovery():
    executor = function_body(
        read(BOT_MGR),
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState* state",
    )
    los = executor.split("SPELL_FAILED_LINE_OF_SIGHT", 1)[1].split(
        "if (state && result == BotActionResult::Ok)", 1
    )[0]

    assert "ProfileCastSuppressedSpellId = action.SpellId" in los
    assert "recoverLineOfSight = true;" in los
    assert_ordered(
        los,
        "RecordCombatAttempt(*state, bot, target",
        "if (recoverLineOfSight && target)",
        "MoveBotToProfileRange(*state, bot, target, &action);",
    )


def test_native_self_resurrection_uses_only_the_player_spell_cast_path():
    mgr = read(BOT_MGR)
    update = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    self_res = function_body(mgr, "bool BotWorldPopulationMgr::TryNativeSelfResurrection")

    assert "TryNativeSelfResurrection(state, bot)" in update
    assert "PLAYER_SELF_RES_SPELL" in self_res
    assert "SPELL_EFFECT_SELF_RESURRECT" in self_res
    assert "bot->CastSpell(bot, spellId, false)" in self_res
    assert "ResurrectPlayer" not in self_res
    assert "native_self_resurrection_submitted" in self_res


def test_validation_route_high_density_adds_pull_the_tank_into_the_swarm_and_fail_closed_to_density_contract():
    mgr = read(BOT_MGR)
    objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    start = objective.index("auto tryValidationRouteAdds")
    end = objective.index("auto markValidationRouteTerminalAfterProgress", start)
    adds = objective[start:end]
    reset = function_body(mgr, "void BotWorldPopulationMgr::ResetValidationRouteRuntimeState")
    density_reset = function_body(mgr, "void BotWorldPopulationMgr::ResetValidationRouteBossAddDensityState")

    assert "addX += creature->GetPositionX();" in adds
    assert "addY += creature->GetPositionY();" in adds
    assert 'observedBossEngagement = _config.ValidationRouteKind == "boss"' in adds
    assert "!_validationRouteBossProgressTargetGuid.IsEmpty()" in adds
    assert "ObjectAccessor::GetUnit(*bot, _validationRouteBossProgressTargetGuid)" in adds
    assert "bool routeBossUnavailable = !routeBoss" in adds
    assert "_validationRouteBossAddDensityGeneration = _validationRouteGeneration;" in adds
    assert "_validationRouteBossAddDensityGeneration != _validationRouteGeneration || !cohortSwarmActive" in adds
    assert "_validationRouteBossAddDensityPhase && routeBossAttackable" in adds
    assert "ResetValidationRouteBossAddDensityState();" in reset
    assert "_validationRouteBossAddDensityPhase = false;" in density_reset
    assert "_validationRouteBossAddDensityGeneration = 0;" in density_reset
    killed_focus = objective[objective.index("auto clearValidationRouteKilledFocus"):start]
    assert "if (_validationRouteBossProgressTargetGuid == killedGuid)" in killed_focus
    assert "ResetValidationRouteBossAddDensityState();" in killed_focus
    assert '\\"boss_add_density_phase\\"' in mgr
    assert '\\"boss_add_density_generation\\"' in mgr
    assert "profile.MovementDirective != \"melee\"" in adds
    assert "float centroidDistance = densityTank->GetExactDist2d(centroidX, centroidY);" in adds
    assert "MoveBotToPoint(state, densityTank, centroidX, centroidY, centroidZ)" in adds
    assert 'moved ? "tank_move_to_add_centroid" : "tank_add_centroid_path_rejected"' in adds
    assert 'escapeIssued ? "reissue_shared_escape_unreached" : "move_to_shared_escape"' in adds
    assert "densityAreaPhase ? addCount : 0, densityAreaPhase" in adds
    assert "ExecuteProfileCombatAction(&state, bot, add, &profileAction, addCount, true)" in adds
    assert "++densityTankOwnedAddCount;" in adds
    assert "densityTankOwnedAddCount * 10 >= addCount * 8" in adds
    assert "bool urgentSwarmDamageRelease = cohortSwarmActive && addCount >= 24" in adds
    assert "bool dpsSwarmDamageRelease = densityTankOwnsSecureMajority || urgentSwarmDamageRelease;" in adds
    assert "!dpsSwarmDamageRelease && !bot->getAttackers().empty()" in adds
    assert '"tank_swarm_defensive"' in adds
    assert "std::array<uint32, 3>{ 86150, 31850, 498 }" in adds
    assert 'RecordEvent(state, bot, "boss_add_density", add, "no_legal_density_action"' in adds
    assert_ordered(
        adds,
        "bool densitySingleTargetFallback = densityAreaPhase && !profileAction.Valid;",
        "profileAction = ResolveProfileCombatAction(bot, add);",
        '"single_target_fallback_selected"',
        '"focused_attack_boss_add_density"',
    )
    assert 'densityGenerator ? "resource_generator_selected" : "area_action_selected"' in adds
    assert 'densityGenerator ? "generate_resource_boss_add_density"' in adds
    assert 'action = "hold_boss_add_density";' in adds
    assert_ordered(adds, "tryRouteGroupHeal(bot, add)", "move_to_shared_escape", 'if (role == "healer")', "no_legal_density_action")
    assert "43438" not in adds
    assert "43917" not in adds

    density_branch = adds[adds.index("if (densityAreaPhase)", adds.index("BotActionResult result")):]
    density_branch = density_branch[:density_branch.index("else\n            {")]
    assert "executor.Pull" not in density_branch


def test_validation_route_ground_danger_dodge_is_reserved_per_cast_window():
    mgr = read(BOT_MGR)
    header = read(BOT_MGR_HEADER)
    objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    movement = objective[objective.index("auto tryValidationRouteMovementCheck"):objective.index("auto tryValidationRouteAdds")]

    assert "ValidationRouteDodgeCasterGuid" in header
    assert "ValidationRouteDodgeSpellId" in header
    assert "ValidationRouteDodgeUntilMs" in header
    assert "state.ValidationRouteDodgeCasterGuid == caster->GetGUID()" in movement
    assert "state.ValidationRouteDodgeSpellId == castSpell->Id" in movement
    assert "state.ValidationRouteDodgeUntilMs > nowMs" in movement
    assert "state.ValidationRouteDodgeUntilMs = nowMs + (moved ? 3000 : 500);" in movement
    assert 'configuredHazardShape == "frontal_cone"' in movement
    assert "dodgeOrigin->GetOrientation() + side * float(M_PI_2)" in movement
    assert_ordered(movement, "ValidationRouteDodgeUntilMs > nowMs", "MoveBotToPoint", "ValidationRouteDodgeUntilMs = nowMs")


def test_density_action_anchor_is_local_range_compatible_and_not_shared_cleanup_focus():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    start = objective.index("auto tryValidationRouteAdds")
    end = objective.index("auto markValidationRouteTerminalAfterProgress", start)
    adds = objective[start:end]

    assert "std::vector<Creature*> localAdds;" in adds
    assert "if (highDensityPhase && role != \"healer\")" in adds
    assert "for (Creature* candidate : localAdds)" in adds
    assert 'profile.MovementDirective == "melee"' in adds
    assert "distance < minRange" in adds
    assert "distance > maxRange" in adds
    assert "distance < bestDistance || (distance == bestDistance && guid < bestAnchorGuid)" in adds
    assert "distance < nearestDistance || (distance == nearestDistance && guid < nearestAnchorGuid)" in adds
    assert "add = densityAnchor;" in adds
    assert "sharedFocusValid = false;" in adds
    assert "if (!highDensityPhase && !sharedFocusValid)" in adds
    assert '"no_compatible_density_anchor"' in adds
    assert "ResolvedCombatAction approachAction;" in adds
    assert "approachAction.MinRange = profile.MinRange;" in adds
    assert "approachAction.MaxRange = profile.MaxRange;" in adds
    assert "MoveBotToProfileRange(state, bot, densityApproachAnchor, &approachAction)" in adds
    assert '"approach_density_anchor"' in adds
    approach_block = adds[adds.index("if (highDensityPhase && !add && densityApproachAnchor)"):adds.index("if (!add)", adds.index("if (highDensityPhase && !add && densityApproachAnchor)"))]
    assert "executor.Pull" not in approach_block
    assert_ordered(adds, "add = densityAnchor;", "if (!highDensityPhase && !sharedFocusValid)")


def test_inactive_density_without_listed_add_does_not_consume_boss_activation_handler():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    start = objective.index("auto tryValidationRouteAdds")
    end = objective.index("auto markValidationRouteTerminalAfterProgress", start)
    adds = objective[start:end]
    no_add = adds[adds.index("if (!add)", adds.index("approach_density_anchor")):adds.index("if (!highDensityPhase && !sharedFocusValid)")]

    assert_ordered(no_add, "if (!highDensityPhase)", "return false;", '"no_compatible_density_anchor"', "return true;")
    assert "if (highDensityPhase && !add && densityApproachAnchor)" in adds
    assert '"approach_density_anchor"' in adds
    assert '"no_compatible_density_anchor"' in no_add


def test_density_tank_centroid_control_prioritizes_loose_healer_targets():
    mgr = read(BOT_MGR)
    objective = function_body(mgr, "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    start = objective.index("auto tryValidationRouteAdds")
    end = objective.index("auto markValidationRouteTerminalAfterProgress", start)
    adds = objective[start:end]
    assert "Player* densityTank = nullptr;" in adds
    assert "Player* densityHealer = nullptr;" in adds
    assert 'uint8 priority = victimRole == "healer" ? 3 : 2;' in adds
    assert "add = looseAdd ? looseAdd : densityAnchor;" in adds
    assert "highDensityPhase && bot == densityTank && addCount >= 3" in adds
    assert "&& !densityDefenseTarget" in adds
    assert "float centroidX = addX / float(addCount);" in adds
    assert "float centroidY = addY / float(addCount);" in adds
    assert "centroidDistance > 4.0f" in adds
    assert "MoveBotToPoint(state, densityTank, centroidX, centroidY, centroidZ)" in adds
    assert 'action = moved ? "tank_move_to_add_centroid" : "hold_tank_add_centroid";' in adds
    assert '"dps_stack_for_add_pickup"' in adds
    assert "densityDefenseTarget == bot && densityTank" not in adds
    assert 'role == "dps" && densityTank && !dpsSwarmDamageRelease && !bot->getAttackers().empty()' in adds
    assert 'if (memberRole == "tank" || member->getAttackers().empty())' in adds
    assert "nearestAttacker->GetAngle(densityTank) - densityTank->GetOrientation()" in adds
    assert "densityTank->GetFirstCollisionPosition(4.0f" in adds
    assert "bool swarmDefenseActive = highDensityPhase || cohortSwarmActive\n            || sharedLargePassiveSwarmStaging;" in adds
    assert "if (swarmDefenseActive)" in adds
    assert "defenseScore = attackerCount + (memberRole == \"healer\" ? 3 : 0)" in adds
    assert '"dps_stack_for_swarm_pickup"' in adds
    assert '"dps_wait_for_swarm_tank_ownership"' in adds
    assert "uint32 densityTankSecureAddCount = 0;" in adds
    assert "densityTankSecureAddCount * 10 >= addCount * 9" in adds
    assert "tankThreat >= 2000.0f && tankThreat >= highestPartyThreat * 2.5f" in adds
    assert '"ice_block_swarm_pickup_emergency"' in adds
    assert 'bool tankSwarmAreaPhase = role == "tank" && cohortSwarmActive;' in adds
    assert 'bool secureSwarmAreaPhase = role == "dps" && cohortSwarmActive' in adds
    assert "dpsSwarmDamageRelease || hunterMisdirectionActive" in adds
    assert "bool densityAreaPhase = highDensityPhase || tankSwarmAreaPhase || secureSwarmAreaPhase;" in adds
    assert "bot->GetExactDist2d(densityTank) <= 8.0f" in adds
    assert "(!bot->getAttackers().empty() && !botInsideTankPickup)" in adds
    assert "bot->GetExactDist2d(densityTank) > 8.0f" not in adds
    assert '"consecration_party_pickup"' in adds
    assert "if (highDensityPhase && role == \"healer\" && tryRouteGroupHeal(bot, add))" in adds
    assert_ordered(adds, "add = looseAdd ? looseAdd : densityAnchor;", "misdirection_to_tank", "tank_move_to_add_centroid")


def test_shared_density_latch_uses_cohort_observation_before_swarm_end_clear():
    objective = function_body(read(BOT_MGR), "bool BotWorldPopulationMgr::TryValidationRouteObjective")
    start = objective.index("auto tryValidationRouteAdds")
    end = objective.index("auto markValidationRouteTerminalAfterProgress", start)
    adds = objective[start:end]

    assert "GuidSet cohortAddGuids;" in adds
    assert "if (_validationRouteBossAddDensityPhase && addCount < 3)" in adds
    assert "for (WorldBotState const& cohortState : _bots)" in adds
    assert "Player* observer = GetLoadedBot(cohortState);" in adds
    assert "cohortAddGuids.insert(creature->GetGUID());" in adds
    assert "bool cohortSwarmActive = cohortAddGuids.size() >= 3;" in adds
    assert "|| !cohortSwarmActive" in adds
    assert "|| addCount < 3" not in adds
    assert_ordered(adds, "if (_validationRouteBossAddDensityPhase && addCount < 3)", "bool cohortSwarmActive", "|| !cohortSwarmActive")


def test_density_action_taxonomy_and_stonecore_roster_profile_paths_are_explicit():
    catalog_header = read(ROOT / "src/server/game/Bots/BotCombatActionCatalog.h")
    catalog = read(ROOT / "src/server/game/Bots/BotCombatActionCatalog.cpp")
    profiles = read(STONECORE_ROTATION_SQL)

    assert_ordered(catalog_header, "ProfessionAction,", "ResourceGenerator")
    assert 'case BotCombatActionCategory::ResourceGenerator: return "resource_generator";' in catalog
    assert 'MAP_CATEGORY("resource_generator", ResourceGenerator);' in catalog
    assert "hammer_of_the_righteous,aoe,holy_power,threat" in profiles
    assert "multi_shot,aoe" in profiles
    assert "flamestrike,aoe" in profiles
    assert "chain_lightning,maelstrom_5,aoe" in profiles
    assert "'resource_generator', 'steady_shot,focus_builder'" in profiles
    assert "'resource_generator', 'stormstrike,melee,maelstrom_generator'" in profiles


def test_healer_lifecycle_telemetry_is_cast_scoped_and_uses_actual_heal_info():
    root = Path(__file__).resolve().parents[1]
    header = (root / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text()
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()
    unit = (root / "src/server/game/Entities/Unit/Unit.cpp").read_text()
    spell = (root / "src/server/game/Spells/Spell.cpp").read_text()
    controller = (root / "src/server/game/Bots/BotController.cpp").read_text()

    assert "struct PendingHealCast" in header
    assert "uint64 CastId" in header
    assert "std::set<uint64> AffectedAllyGuids" in header
    assert "uint64 pendingCastId = BeginPendingHealCast(bot, target, spellId);\n    SpellCastResult castResult" in manager
    assert 'bot_healing_lifecycle_v1' in manager
    for field in ("attempted_heal", "effective_heal", "overheal", "mana_delta",
                  "affected_ally_count", "attackers_before", "attackers_after",
                  "threat_before", "threat_after", "candidate_mask", "chosen_action"):
        assert field in manager
    assert "NotifyBotHeal(healer, victim, healInfo.GetSpellInfo()->Id, addhealth + healInfo.GetAbsorb()" in unit
    assert "NotifyBotSpellFinished(playerCaster, m_spellInfo->Id, ok)" in spell
    assert "NotifyBotSpellStarted(bot, lifecycleTarget, attempt.Spell->SpellId, candidateMaskJson, chosenActionJson)" in controller
    assert "CancelBotSpellStart(pendingCastId, bot, ToString(result))" in controller
    assert '"completed"' in manager and '"interrupted"' in manager and '"timeout"' in manager
    assert 'CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events' in manager
    assert 'ClearPendingHealCasts("run_stop")' in manager
    assert 'ClearPendingHealCasts("autonomy_stop")' in manager
    assert 'ClearPendingHealCasts("shutdown")' in manager
    assert "ManaAfterCast = caster->GetPower(POWER_MANA)" in manager
    assert "AttackersAfterCast" in manager and "ThreatAfterCast" in manager
    assert "absorbed_heal" in manager
    assert "no_matching_cast_window" in manager
    assert '_lastHealerCandidateMaskJson = "{}"' in controller
    assert '_lastHealerChosenActionJson = "{}"' in controller


def test_healer_candidate_mask_is_db_driven_and_records_rejections():
    root = Path(__file__).resolve().parents[1]
    profile = (root / "src/server/game/Bots/BotClassSpecActionProfile.cpp").read_text()
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    assert '\\"valid\\":" << (candidate.RejectReason.empty() ? "true" : "false")' in profile
    assert 'candidate.RejectReason = "missing_party_target"' in profile
    assert "BotClassSpecActionProfileStore::Build(bot, role.c_str())" in manager
    assert "candidate.Profile.InjuredHealthPct" in manager
    assert 'candidate.RejectReason = "not_healing_action"' in manager
    assert "return best ? best->SpellId : 0;" in manager


def test_rerun145_protection_pickup_and_passive_swarm_repairs_are_bounded():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    assert '"consecration_healer_multi_trash_pickup"' in manager
    multi_consecration = manager.index('"consecration_healer_multi_trash_pickup"')
    ordinary_righteous_defense = manager.index(
        '"righteous_defense_healer_pickup"', multi_consecration
    )
    assert multi_consecration < ordinary_righteous_defense
    assert "defenseAttackerCount >= 2" in manager[
        multi_consecration - 1200 : multi_consecration
    ]
    assert "bot->GetExactDist2d(defenseTarget) <= 8.0f" in manager[
        multi_consecration - 1200 : multi_consecration
    ]

    assert "engagedAddCount == 0 && passiveSwarmClusterAnchor" in manager
    assert 'activationAction.Type = "auto_attack";' in manager
    assert 'activationAction.AutoAttackMode = "melee";' in manager
    assert '"tank_activate_passive_swarm"' in manager


def test_rerun151_protection_remote_healer_cluster_uses_native_ranged_pickup():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    ranged_pickup = manager.index(
        '"avengers_shield_healer_multi_trash_pickup"'
    )
    ordinary_salvation = manager.index(
        '"hand_of_salvation_healer_trash_threat_drop"', ranged_pickup
    )
    ordinary_righteous_defense = manager.rindex(
        '"righteous_defense_healer_pickup"', 0, ranged_pickup
    )
    branch = manager[ranged_pickup - 2400 : ranged_pickup + 800]

    assert ordinary_righteous_defense < ranged_pickup < ordinary_salvation
    assert "defenseAttackerCount >= 2" in branch
    assert "bot->HasSpell(31935)" in branch
    assert "TryCastCombatSpell(bot, healerClusterTarget, 31935)" in branch
    assert "defenseTarget->getAttackers()" in branch
    assert "distance < healerClusterDistance" in branch
    assert "guid < healerClusterGuid" in branch


def test_rerun162_protection_retention_and_passive_swarm_fallback_are_bounded():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    boss_marker = manager.index(
        "Rerun162 proved the same bounded Protection pickup cadence"
    )
    boss_branch = manager[boss_marker : boss_marker + 1800]
    assert 'role == "tank" && profile.SpecTag == "protection"' in boss_branch
    assert 'profile.SpecTag == "protection_paladin"' not in boss_branch
    assert "&& densityHealer" in boss_branch
    assert "cohortSwarmActive && densityHealer" not in boss_branch
    assert "engagedAddCount >= 12" in boss_branch
    assert "observedListedAttackerCount(densityHealer) >= 2" in boss_branch
    assert "state.DecisionTimer = std::min<uint32>(\n                state.DecisionTimer, 250);" in boss_branch

    trash_marker = manager.index(
        "Rerun153 proved the reactive cadence from rerun152"
    )
    trash_branch = manager[trash_marker : trash_marker + 1900]
    assert "protectionMultiHostileRetention" in trash_branch
    assert "trashThreatControl.EngagedCount >= 3" in trash_branch
    assert "tankOwnsTrashMajority" in trash_branch
    assert "protectionMultiHostileHealerPickup" in trash_branch
    assert "bot->getClass() == CLASS_PALADIN" in trash_branch
    assert 'std::string(GetDungeonRole(defenseTarget)) == "healer"' in trash_branch
    assert "defenseAttackerCount >= 2" in trash_branch
    assert "state.DecisionTimer = std::min<uint32>(\n                state.DecisionTimer, 250);" in trash_branch
    assert trash_marker < manager.index(
        '"consecration_healer_multi_trash_pickup"', trash_marker
    )

    passive_marker = manager.index(
        "Rerun153 reached the passive anchor but had no line of sight"
    )
    passive_branch = manager[passive_marker - 2600 : passive_marker + 1500]
    assert "bot->IsWithinLOSInMap(passiveSwarmClusterAnchor)" in passive_branch
    assert "passiveSwarmActivationNotActionable" in passive_branch
    assert "pendingSwarmActivation" in passive_branch
    assert "!passiveSwarmActivationNotActionable" in passive_branch


def test_rerun162_post_death_safe_anchor_uses_route_movement_z_contract():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    marker = manager.index(
        "Rerun162 selected a remembered post-death anchor"
    )
    branch = manager[marker : marker + 1600]
    assert "safeMap->GetHeight(bot->GetPhaseShift(), safe.X, safe.Y" in branch
    assert "safeFloorZ <= INVALID_HEIGHT" in branch
    assert "std::fabs(safeFloorZ - safe.Z) > 4.0f" in branch
    assert branch.index("std::fabs(safeFloorZ - safe.Z) > 4.0f") < branch.index(
        "float safeDanger = GetLocalDangerScore"
    )


def test_rerun154_feral_high_density_charge_reselects_remote_wave_target():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    marker = manager.index(
        "Rerun154 exposed a declared 20-follower wave"
    )
    branch = manager[marker - 500 : marker + 4300]
    assert "feralChargeProtectsHighDensityParty = engagedAddCount >= 12" in branch
    assert "observedListedAttackerCount(densityHealer) == 0" in branch
    assert "Unit* feralChargeTarget = add;" in branch
    assert "bot->GetExactDist(feralChargeTarget) <= 8.0f" in branch
    assert "candidate->GetVictim() == bot" in branch
    assert 'GetDungeonRole(candidateVictim)) == "tank"' in branch
    assert "bot->GetExactDist(candidate) <= 8.0f" in branch
    assert "distance < remoteChargeDistance" in branch
    assert "guid < remoteChargeGuid" in branch
    assert "TryCastCombatSpell(bot, feralChargeTarget, 16979)" in branch
    assert "state.FeralChargePickupTargetGuid = feralChargeTarget->GetGUID();" in branch
    assert "state.FeralChargePickupUntilMs = NowMs() + 2500;" in branch
    assert "state.DecisionTimer = std::min<uint32>(\n                state.DecisionTimer, 250);" in branch
    assert_ordered(
        branch,
        "Unit* feralChargeTarget = add;",
        "for (Creature* candidate : localAdds)",
        "if (remoteChargeTarget)",
        "TryCastCombatSpell(bot, feralChargeTarget, 16979)",
        "state.FeralChargePickupTargetGuid = feralChargeTarget->GetGUID();",
    )


def test_rerun155_current_healer_threat_preempts_feral_secure_margin_approach():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    marker = manager.index(
        "Rerun155 recovered one of three healer-owned Flayers"
    )
    branch = manager[marker - 2100 : marker + 3000]
    assert "bool feralCurrentHealerThreat = defenseTarget" in branch
    assert 'std::string(GetDungeonRole(defenseTarget)) == "healer"' in branch
    assert "defenseAttackerCount >= 1" in branch
    assert "bool feralHealerHandoffPending = feralCurrentHealerThreat" in branch
    assert "tankOwnsTrashMajority && insecureTrashSwarm" in branch
    assert "&& !feralHealerHandoffPending" in branch
    assert "&& !feralCurrentHealerThreat" in branch
    assert_ordered(
        branch,
        "bool feralCurrentHealerThreat = defenseTarget",
        "bool feralHealerHandoffPending = feralCurrentHealerThreat",
        "Rerun155 recovered one of three healer-owned Flayers",
        "&& !feralHealerHandoffPending",
        "&& !feralCurrentHealerThreat",
        '"feral_approach_insecure_trash_threat_cluster"',
    )


def test_rerun156_active_feral_wave_preempts_pending_swarm_preposition():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    marker = manager.index(
        "Rerun156 exposed a declared 60-follower Feral wave"
    )
    branch = manager[marker - 500 : marker + 1900]
    assert "feralActiveWavePreemptsPendingSwarmPickup" in branch
    assert 'profile.SpecTag == "feral_druid_tank"' in branch
    assert "engagedAddCount >= 12" in branch
    assert "densityHealer" in branch
    assert "observedListedAttackerCount(densityHealer) == 0" in branch
    assert "state.TankPendingSwarmPickupAnchorGuid.Clear();" in branch
    assert "state.TankPendingSwarmPickupUntilMs = 0;" in branch
    assert "state.TankPendingSwarmPickupEngagedHandoff = false;" in branch
    assert "tankPendingSwarmPickup = false;" in branch
    assert "pendingSwarmPickupAnchor = nullptr;" in branch
    assert_ordered(
        manager,
        "bool feralActiveWavePreemptsPendingSwarmPickup",
        "if (feralActiveWavePreemptsPendingSwarmPickup)",
        "if (tankPendingSwarmPickup && pendingSwarmPickupAnchor",
        "bool feralChargeProtectsHighDensityParty = engagedAddCount >= 12",
    )


def test_rerun156_boss_handoff_rebinds_within_original_healer_cluster():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    marker = manager.index(
        "Rerun156 proved the boss handoff discarded a still-valid Azil"
    )
    branch = manager[marker - 300 : marker + 4300]
    assert "state.FeralHealerThreatHandoffRemoteCluster" in branch
    assert "feralHealerHandoffAnchor->GetVictim() != densityHealer" in branch
    assert "for (Creature* candidate : localAdds)" in branch
    assert "candidate->GetVictim() == densityHealer" in branch
    assert "bot->IsValidAttackTarget(candidate)" in branch
    assert "feralHealerHandoffAnchor->GetExactDist2d(candidate)" in branch
    assert "<= 10.0f" in branch
    assert "candidate->GetGUID().GetCounter() < reboundGuid" in branch
    assert "state.FeralHealerThreatHandoffAnchorGuid =" in branch
    assert "feralHealerHandoffAnchor = reboundAnchor;" in branch
    assert "FeralHealerThreatHandoffUntilMs =" not in branch
    assert_ordered(
        branch,
        "if (state.FeralHealerThreatHandoffRemoteCluster",
        "for (Creature* candidate : localAdds)",
        "state.FeralHealerThreatHandoffAnchorGuid =",
        "bool feralHealerRemoteHandoffValid",
    )


def test_rerun164_failed_single_healer_growl_rebinds_generic_fallback():
    manager = read(BOT_MGR)
    marker = manager.index(
        "Rerun164 recovered the first of two Azil followers with Growl"
    )
    branch = manager[marker - 3400 : marker + 900]

    assert "observedListedAttackerCount(densityHealer) == 1" in branch
    assert "TryCastCombatSpell(bot, healerOwnedAdd, 6795)" in branch
    assert 'action = "feral_growl_lingering_healer_swarm_attacker";' in branch
    assert "if (healerOwnedAdd)" in branch
    assert "add = healerOwnedAdd;" in branch
    assert "sharedFocusValid = false;" in branch
    assert_ordered(
        branch,
        "TryCastCombatSpell(bot, healerOwnedAdd, 6795)",
        'action = "feral_growl_lingering_healer_swarm_attacker";',
        "return true;",
        "Rerun164 recovered the first of two Azil followers with Growl",
        "add = healerOwnedAdd;",
        "sharedFocusValid = false;",
    )


def test_rerun165_density_resolver_rejects_buff_without_removing_recovery_fallbacks():
    manager = read(BOT_MGR)
    resolver = function_body(
        manager,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    marker = resolver.index(
        "Rerun165 canary 3 captured a Protection tank owning all 49 Azil"
    )
    branch = resolver[marker - 650 : marker + 850]

    assert "densityOnly && candidate.Category == BotCombatActionCategory::Buff" in branch
    assert 'candidate.RejectReason = "density_buff_not_actionable";' in branch
    assert "BotCombatActionCategory::Defensive" not in branch
    assert "BotCombatActionCategory::ResourceGenerator" not in branch
    assert_ordered(
        branch,
        "if (areaOnly",
        "if (densityOnly && candidate.Category == BotCombatActionCategory::Buff)",
        "SpellInfo const* candidateSpellInfo",
    )
    assert "bestDensityRecovery" in resolver
    assert "bestDensityResourceFallback" in resolver
    assert "bestDensityGenerator" in resolver


def test_rerun169_melee_fallback_exposes_native_range_to_movement_callers():
    manager = read(BOT_MGR)
    resolver = function_body(
        manager,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    marker = resolver.index(
        "Rerun169 canary 3 reached a remote healer-owned cluster"
    )
    branch = resolver[marker - 300 : marker + 1000]

    assert 'action.DebugName = "melee_auto_attack_fallback";' in branch
    assert "action.MinRange = 0.0f;" in branch
    assert "action.MaxRange = std::max(5.0f, bot->GetMeleeRange(target));" in branch
    assert_ordered(
        branch,
        'profile.AutoAttackMode == "melee"',
        'action.DebugName = "melee_auto_attack_fallback";',
        "action.MinRange = 0.0f;",
        "action.MaxRange = std::max(5.0f, bot->GetMeleeRange(target));",
    )


def test_rerun170_defers_passive_azil_followers_until_route_arrival():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = route.index(
        "Rerun170 reached Azil's route generation roughly 80-115 yards"
    )
    branch = route[marker - 500 : marker + 2300]

    assert "addCount > 0 && engagedAddCount == 0" in branch
    assert "Party().ValidationRouteBossProgressTargetGuid.IsEmpty()" in branch
    assert "canonicalRouteDistance > routeArrivalRadius" in branch
    assert_ordered(
        branch,
        "bool cohortSwarmActive = cohortAddGuids.size() >= 3;",
        "addCount > 0 && engagedAddCount == 0",
        "return false;",
        "Party().ValidationRouteBossAddDensityPhase",
    )


def test_rerun197_passive_listed_adds_cannot_own_generic_boss_focus():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun196 reached Azil's final route generation with no party combat"
    )
    branch = objective[marker - 300 : marker + 1900]

    assert_ordered(
        branch,
        "bool unengagedListedBossAdd =",
        "ValidationRouteAddTargetEntries.begin()",
        "!candidate->IsInCombat() && !candidate->GetVictim()",
        "if (unengagedListedBossAdd)",
        "return nullptr;",
        "if (isValidationRouteCombatTarget(creature))",
    )
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun197_feral_majority_healer_flip_uses_bounded_native_fade():
    objective = function_body(
        read(BOT_MGR),
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    marker = objective.index(
        "Rerun196 then captured a distinct Feral"
    )
    branch = objective[marker - 900 : marker + 2600]

    assert_ordered(
        branch,
        "bool feralDruidMajorityHealerThreat =",
        "trashThreatControl.Tank->getClass() == CLASS_DRUID",
        "trashThreatControl.HealerTargetCount >= 4",
        "trashThreatControl.HealerTargetCount * 5",
        ">= trashThreatControl.EngagedCount * 4",
        "|| feralDruidMajorityHealerThreat",
        "state.DecisionTimer, 250",
        "TryCastFriendlySpell(bot, bot, 586)",
        '"fade_early_trash_swarm_threat_drop"',
    )
    assert "SetVictim" not in branch
    assert "AddThreat" not in branch
    assert "NearTeleportTo" not in branch


def test_rerun170_protection_healer_pickup_and_approach_use_urgent_cadence():
    manager = read(BOT_MGR)
    route = function_body(
        manager,
        "bool BotWorldPopulationMgr::TryValidationRouteObjective",
    )
    taunt_marker = route.index(
        "Rerun170 retained 17 eligible healer-target samples"
    )
    taunt_branch = route[taunt_marker - 500 : taunt_marker + 3800]
    move_marker = route.index(
        "Rerun170's longest Protection exposure began with three"
    )
    move_branch = route[move_marker - 500 : move_marker + 1300]

    assert 'cadenceProfile.SpecTag == "protection"' in taunt_branch
    assert "defenseAttackerCount >= 1" in taunt_branch
    assert "bot->HasSpell(62124)" in taunt_branch
    assert "TryCastCombatSpell(bot, healerTauntTarget, 62124)" in taunt_branch
    assert '"hand_of_reckoning_healer_trash_pickup"' in taunt_branch
    assert "state.DecisionTimer, 250);" in taunt_branch
    assert_ordered(
        taunt_branch,
        "Righteous Defense was unavailable",
        "for (Unit* attacker : defenseTarget->getAttackers())",
        "TryCastCombatSpell(bot, healerTauntTarget, 62124)",
        "state.DecisionTimer, 250);",
        "Rerun151 localized Protection's remaining healer exposure",
    )

    assert 'cadenceProfile.SpecTag == "protection"' in move_branch
    assert "target->GetVictim()->ToPlayer()" in move_branch
    assert 'std::string(GetDungeonRole(areaVictim)) == "healer"' in move_branch
    assert "state.DecisionTimer = std::min<uint32>(" in move_branch
    assert "state.DecisionTimer, 250);" in move_branch
    assert_ordered(
        move_branch,
        "MoveBotToProfileRange(state, bot, target, &areaAction)",
        'cadenceProfile.SpecTag == "protection"',
        'GetDungeonRole(areaVictim)) == "healer"',
        "state.DecisionTimer, 250);",
        'action = moved ? "move_to_trash_density"',
    )


def test_rerun157_preserves_global_cooldown_scheduling_identity():
    manager = read(BOT_MGR)
    resolver = function_body(
        manager,
        "ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction",
    )
    executor = function_body(
        manager,
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction",
    )

    assert 'candidate.RejectReason == "global_cooldown"' in resolver
    assert 'globalCooldownSchedulingWait ? "global_cooldown"' in resolver
    assert 'action.DebugName == "global_cooldown"' in executor
    assert "BotActionResult::GlobalCooldown : BotActionResult::NoAction" in executor
    assert "RecordCombatAttempt(*state, bot, target, \"profile_resolve\", &action," in executor
    assert "return invalidResult;" in executor


def test_rerun157_closes_control_race_and_retains_protection_threat_gates():
    manager = read(BOT_MGR)
    action_executor = read(ROOT / "src/server/game/Bots/BotActionExecutor.cpp")
    hostile_check = function_body(
        action_executor,
        "BotActionResult BotActionExecutor::CheckHostileSpell",
    )

    assert "bot->HasUnitState(UNIT_STATE_CONTROLLED)" in hostile_check
    assert "return BotActionResult::Throttled;" in hostile_check
    assert "bool urgentSwarmDamageRelease = cohortSwarmActive && addCount >= 24" in manager
    marker = manager.index("Rerun157 localized 28 of 37 Protection")
    branch = manager[marker : marker + 1800]
    assert 'std::string(GetDungeonRole(defenseTarget)) == "healer"' in branch
    assert "defenseAttackerCount >= 1" in branch
    assert "bot->HasSpell(1022)" in branch
    assert "!defenseTarget->HasAura(1022)" in branch
    assert "TryCastFriendlySpell(bot, defenseTarget, 1022)" in branch
    assert '"hand_of_protection_healer_trash_emergency"' in branch
    assert_ordered(
        manager,
        "Rerun157 localized 28 of 37 Protection",
        '"hand_of_protection_healer_trash_emergency"',
        "Rerun145 localized Protection's only healer exposure",
        '"consecration_healer_multi_trash_pickup"',
    )


def test_rerun158_passive_swarm_activation_uses_native_melee_reach():
    manager = read(BOT_MGR)
    activation = manager.index('activationAction.DebugName = "activate_passive_swarm";')
    branch = manager[activation - 2600 : activation + 3600]

    assert "!bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)" in branch
    assert "bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)" in branch
    assert "bot->IsWithinLOSInMap(passiveSwarmClusterAnchor)" in branch
    assert "passiveSwarmActivationNotActionable" in branch
    assert "!passiveSwarmActivationNotActionable" in branch
    assert "passiveSwarmActivationLineOfSightBlocked" not in branch
    assert "bot->GetExactDist2d(passiveSwarmClusterAnchor) <= 6.0f" not in branch


def test_rerun159_feral_hazard_retention_prefers_native_thrash_with_fallthrough():
    manager = read(BOT_MGR)
    marker = manager.index("Rerun159 localized all Feral healer exposure")
    branch = manager[marker - 300 : marker + 5200]

    assert 'hazardProfile.SpecTag != "feral_druid_tank"' in branch
    assert "engagedCount < 12" in branch
    assert "!areaTarget" in branch
    assert "!bot->HasSpell(77758)" in branch
    assert "!TryCastCombatSpell(bot, areaTarget, 77758)" in branch
    assert '"feral_thrash_hazard_secure_threat_retention"' in branch
    assert "if (tryFeralHazardThrashRetention())" in branch
    assert_ordered(
        manager,
        "Rerun159 localized all Feral healer exposure",
        '"feral_thrash_hazard_secure_threat_retention"',
        '"feral_swipe_hazard_secure_threat_margin"',
        "if (tryFeralHazardThrashRetention())",
        '"tank_hazard_hold_aoe_threat"',
    )


def test_stonecore_quality_repairs_cover_hazards_pet_recovery_and_healer_protection():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()
    header = (root / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text()
    rotation_sql = (root / "sql/custom/world/2026_07_15_00_stonecore_complete_role_rotations.sql").read_text()
    emergency_threat_sql = read(EMERGENCY_ADD_THREAT_SQL)
    hunter_liveness_sql = (root / "sql/custom/world/2026_07_15_02_stonecore_hunter_rotation_liveness.sql").read_text()

    for field in (
        "ValidationRouteHazardSourceEntry",
        "ValidationRouteHazardDetectionSpellId",
        "ValidationRouteHazardDamageSpellId",
        "ValidationRouteHazardShape",
        "ValidationRouteHazardRadiusYards",
    ):
        assert field in header
        assert field in manager
    assert 'HasInArc(float(M_PI), bot)' in manager
    movement = manager[manager.index("auto tryValidationRouteMovementCheck"):manager.index("auto tryValidationRouteAdds")]
    assert "addHazardDefinition(_config.ValidationRouteHazardSourceEntry" in movement
    assert "for (ValidationRouteManifestNode const& node : _validationRouteManifest)" not in movement
    assert "hazardDefinitionFor(hazard->GetEntry(), 0)" in manager
    assert '"hazard_exit_started"' in manager
    assert '"hazard_exit_completed"' in manager
    assert '"hold_hazard_exit_failed"' in manager
    assert "HunterPetRevivePendingUntilMs" in header
    assert '"hunter_pet_revive_submitted"' in manager
    assert '"hunter_pet_revived"' in manager
    assert 'victimRole == "healer" ? 3 : 2' in manager
    assert 'if (botIsTank && victimRole == "healer")' in manager
    assert "score += 30000.0f;" in manager
    assert "bool loosePartyThreat = threatVictim && threatVictim->GetGroup() == bot->GetGroup()" in manager
    assert "victim->GetGroup() != bot->GetGroup()" in manager
    assert '"tank_move_to_add_centroid"' in manager
    assert '"misdirection_to_tank"' in manager
    assert "bool hunterAoeTransferReady = true;" in manager
    assert "bot->GetPower(POWER_FOCUS) >= 40" in manager
    assert "hunterAoeTransferReady\n            && bot->HasSpell(34477)" in manager
    assert "if (useAreaTransfer && bot->isMoving()" in manager
    assert "bot->StopMoving();" in manager
    assert "transferAction.SpellId = 2643;" in manager
    assert 'RecordCombatAttempt(state, bot, add, "misdirection_aoe_transfer"' in manager
    assert "bool hunterTrashAoeTransferReady = true;" in manager
    assert 'RecordCombatAttempt(state, bot, target, "misdirection_aoe_transfer"' in manager
    assert '"swarm_pickup_emergency_defensive"' in manager
    assert "bot->getClass() == CLASS_SHAMAN ? 3 : 5" in manager
    assert "&& (creature->IsInCombat() || creature->GetVictim())" not in manager
    assert '"righteous_defense_healer_pickup"' in manager
    assert '"hand_of_reckoning_add_pickup"' in manager
    assert '"fade_threat_drop"' in manager
    assert '"fade_preemptive_add_wave_threat_drop"' in manager
    assert 'role == "healer" && cohortSwarmActive && !densityTankOwnsSecureMajority' in manager
    assert '"healer_stack_for_add_pickup"' in manager
    assert '"guardian_spirit_self_emergency"' in manager
    assert '"desperate_prayer_self_emergency"' in manager
    assert "healer->getAttackers().empty() || UnitHealthPct(healer) > 0.60f" in manager
    assert "safeAngle - tankTarget->GetOrientation()" in manager
    assert "pickup = tankTarget->GetFirstCollisionPosition(4.0f" in manager
    assert "if (Pet* pet = bot->GetPet())\n                pet->AttackStop();" in manager
    assert '"tank_close_to_healer_adds"' not in manager
    assert '"consecration_healer_pickup"' in manager
    assert '"consecration_party_pickup"' in manager
    assert '"dps_stack_for_add_pickup"' in manager
    assert '"consecration_party_trash_pickup"' in manager
    assert '"dps_stack_for_trash_pickup"' in manager
    assert "bot->GetExactDist2d(densityTank) > 8.0f" not in manager
    assert "densityTankSecureAddCount * 10 >= addCount * 9" in manager
    assert "bool listedBossAdd = _config.ValidationRouteKind == \"boss\"" in manager
    assert 'candidate.RejectReason = "major_tank_defensive_already_active";' in manager
    assert "bot->GetExactDist2d(densityTank) <= 8.0f" in manager
    assert "(!bot->getAttackers().empty() && !botInsideTankPickup)" in manager
    assert "bot->GetExactDist2d(tank) > 8.0f" in manager
    assert "Unit* pickupFocus = tank->GetVictim() ? tank->GetVictim() : nearestAttacker;" in manager
    assert '"hand_of_salvation_healer_threat_drop"' in manager
    assert '"hand_of_protection_healer_emergency"' in manager
    assert "densityHealer->getAttackers().size() >= 5" in manager
    assert "defenseScore += 1000;" in manager
    assert "olderHealerTarget" not in manager
    assert "nearestDefenseAttacker" in manager
    assert '"dps_hold_for_nearby_add_pickup"' in manager
    assert '"tank_auto_attack_density_fallback"' in manager
    assert "urgentHunterPetRecovery" in manager
    assert "addCount >= 3 && !densityDefenseTarget" in manager
    assert "MoveBotToProfileRange(state, bot, target, &profileAction)" in manager
    assert "GetFirstCollisionPosition(profileAction.MinRange" not in manager
    assert "? std::max(12.0f, minRange + 4.0f)" in manager
    assert "auto moveOutOfProfileDeadZone" in manager
    assert "Player* partyRangedAnchor = nullptr;" in manager
    assert "for (float spread : { 3.0f, -3.0f, 0.0f })" in manager
    assert "endpointDistance >= rangeAction.MinRange + 1.0f" in manager
    assert "float absoluteBearing = movingOutward ? reference->GetAngle(bot) : bot->GetAngle(reference);" in manager
    assert "Position rangedPosition = bot->GetFirstCollisionPosition(travelDistance, relativeBearing + angleOffset);" in manager
    assert "for (uint8 ringIndex = 0; ringIndex < 16; ++ringIndex)" in manager
    assert "reference->GetPositionY() + std::sin(angle) * ringRange" in manager
    assert "tankAnchor->GetFirstCollisionPosition" not in manager
    assert "MoveChase(reference, desiredRange)" not in manager
    assert 'state.LastDecisionAction == "validation_route_complete"' in manager
    assert 'state.LastDecisionSituation == "validation_route_manifest"' in manager
    assert "bool _validationRouteObservedDeadScriptTarget = false;" in header
    assert "_validationRouteObservedDeadScriptTarget = true;" in manager
    assert "_validationRouteCompletedPackCount > 0 || _validationRouteObservedDeadScriptTarget" in manager
    assert 'routeArrivalRadius = routeProfile.MovementDirective == "melee" ? 8.0f : 30.0f;' in manager
    assert "_validationRoutePackObservedEngagement || _validationRouteObservedDeadScriptTarget" in manager
    assert '\\"validation_route_observed_dead_script_target\\"' in manager
    assert "float minRange = selfTarget ? 0.0f" in manager
    assert 'candidate.RejectReason = "caster_controlled"' in manager
    assert 'candidate.RejectReason = "caster_prevented"' in manager
    assert "WHEN `action`.`spell_id` = 26573 THEN 0" in emergency_threat_sql
    assert "a.`priority_bucket` = 6" in hunter_liveness_sql
    assert "a.`spell_id` = 1130" in hunter_liveness_sql
    for spell_id in (2948, 92315, 11129, 403, 421, 53595, 26573):
        assert str(spell_id) in rotation_sql


def test_parallel_combat_calibration_is_isolated_and_uses_live_rotations():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()
    header = (root / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text()
    commands = (root / "src/server/scripts/Commands/cs_healerbot.cpp").read_text()
    unit = (root / "src/server/game/Entities/Unit/Unit.cpp").read_text()

    assert "std::vector<WorldBotState> _calibrationBots" in header
    assert "std::map<uint32, CalibrationMetrics> _calibrationMetrics" in header
    assert "std::map<uint32, CalibrationMetrics> _calibrationBestSingleMetrics" in header
    assert "std::map<uint32, CalibrationMetrics> _calibrationBestAoeMetrics" in header
    assert "std::map<uint32, std::string> _lastCombatRejectsByBot" in header
    assert "combat_calibration" in manager
    assert "SelectCalibrationPoolCandidateGuid" in manager
    update = function_body(manager, "void BotWorldPopulationMgr::UpdateCalibrationBot")
    assert "ResolveProfileCombatAction(bot, target, hostileCount, _calibrationAoePhase)" in update
    assert "ExecuteProfileCombatAction(&state, bot, target, &action, hostileCount, _calibrationAoePhase)" in update
    assert "std::max<uint32>(3, uint32(dummies.size()))" in update

    damage = function_body(manager, "void BotWorldPopulationMgr::NotifyCombatDamage")
    assert damage.index("_calibrationMetrics.find") < damage.index("FindCombatLogCohortPlayer(attacker)")
    assert "uint32 measuredDamage = damage ? damage : unmitigatedDamage" in damage
    assert "calibration->second.SpellDamage[spellId] += measuredDamage" in damage
    assert "damageBeforeScriptAdjustment" in unit
    assert "isolated_from_route_telemetry" in manager
    assert "best_windows" in manager
    assert "external_bis_target_configured" in manager
    assert "EnsureCalibrationCohortGroup();" in manager
    assert "stonecore_party_owned_buffs" in manager
    assert "full_raid_reference_auras" in manager
    assert "ApplyCalibrationReferenceConditions(bot, target)" in update
    reference_conditions = function_body(manager, "std::pair<bool, bool> BotWorldPopulationMgr::ApplyCalibrationReferenceConditions")
    for spell_id in ["79102", "53646", "17007", "2895", "8515", "8076", "82930", "79470", "79471", "79472", "2825", "1490", "22959", "81326", "58567"]:
        assert spell_id in reference_conditions
    assert "bot->getClass() != CLASS_PALADIN" in reference_conditions
    assert "reference debuffs on that primary target" in reference_conditions
    assert "sunder->SetStackAmount(3)" in reference_conditions
    assert "target->HasAura(spellId)" in reference_conditions
    assert "ReferenceTargetDebuffsReady" in manager
    assert "ReferenceHeroismWindowObserved" in manager
    assert '\\"reference_setup\\"' in manager
    assert "calibrationGroup->Disband();" in manager
    assert "group->AddMember(bot)" in manager
    assert '\\"grouped\\"' in manager
    reference = json.loads((root / "dataset/combat_calibration/wowsims_cata_p4.json").read_text())
    assert reference["schema"] == "bot_combat_calibration_reference_v1"
    assert {profile["spec"] for profile in reference["profiles"]} == {
        "fire_mage", "survival_hunter", "enhancement_shaman"
    }
    assert "dummy->RemoveOwnedAuras([casterGuid](Aura const* aura)" in manager
    assert "metrics.WindowEndedMs = windowEndedMs;" in manager
    assert "last_action_rejections" in manager
    assert "last_chosen_action" in manager
    assert "Unit* target = dummies.front();" in update
    assert '{ "calibrate", rbac::RBAC_PERM_COMMAND_HEALERBOT' in commands
    assert "StartCombatCalibration" in commands
    assert "StopCombatCalibration" in commands


def test_rerun148_feral_pre_victim_cadence_and_charge_identity_are_bounded():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    assert "engagedAddCount >= 12 && densityHealer" in manager
    assert "observedListedAttackerCount(densityHealer) == 0" in manager
    assert "state.DecisionTimer, 250" in manager
    assert "feralChargePickupTarget = ObjectAccessor::GetUnit(" in manager
    assert "state.FeralChargePickupTargetGuid" in manager
    assert "state.FeralChargePickupUntilMs > feralChargeNowMs" in manager


def test_rerun148_hunter_spell_los_failure_forces_one_alternate_lane_search():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    assert "MoveBotToProfileRange(*state, bot, target, &action, true);" in manager
    assert "if (!forceRangedReposition && distance >= desiredRange - 1.0f" in manager
