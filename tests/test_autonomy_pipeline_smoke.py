from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_COMMANDS = ROOT / "src/server/scripts/Commands/cs_healerbot.cpp"
BOT_MGR = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
BOT_POLICY = ROOT / "src/server/game/Bots/BotTelemetryPolicy.cpp"
BOT_BUFFER = ROOT / "src/server/game/Bots/BotTelemetryBuffer.cpp"
BOT_SEGMENTS = ROOT / "src/server/game/Bots/BotExperimentCoordinator.cpp"
WORLDSERVER_CONF = ROOT / "src/server/worldserver/worldserver.conf.dist"
CHASE_MOVEMENT = ROOT / "src/server/game/Movement/MovementGenerators/ChaseMovementGenerator.cpp"


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


def test_server_start_autonomy_enabled_by_default_contract():
    conf = read(WORLDSERVER_CONF)
    commands = read(BOT_COMMANDS)
    startup = function_body(commands, "void OnStartup() override")

    assert re.search(r"^PlayerBot\.Enable\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.Enable\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoStart\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoStartRecording\s*=\s*1$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.AutoRecordingWindowMinutes\s*=\s*15$", conf, re.MULTILINE)
    assert re.search(r"^BotWorld\.TargetPopulation\s*=\s*5$", conf, re.MULTILINE)
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


def test_server_start_autonomy_enabled_spawns_from_pool_without_center_requirement():
    mgr = read(BOT_MGR)
    start_autonomy = function_body(mgr, "bool BotWorldPopulationMgr::StartAutonomy")
    ensure_population = function_body(mgr, "void BotWorldPopulationMgr::EnsurePopulation")
    resolve_placement = function_body(mgr, "bool BotWorldPopulationMgr::ResolveSpawnPlacement")

    assert 'LoadConfig("always_on_autonomy", overrideConfig);' in start_autonomy
    assert "_runtimeMode = BotWorldRuntimeMode::AlwaysOnAutonomy;" in start_autonomy
    assert "_runId = 0;" in start_autonomy
    assert "_experimentId = 0;" in start_autonomy
    assert_ordered(start_autonomy, "_active = true;", "EnsurePopulation();", "return _active;")

    assert "uint32 candidateGuid = SelectPoolCandidateGuid();" in ensure_population
    assert 'sBotMgr->SpawnWorldBotAtSavedPosition("any", std::to_string(candidateGuid))' in ensure_population
    assert 'sBotMgr->SpawnWorldBot("any", std::to_string(candidateGuid)' in ensure_population
    assert 'RecordEvent(_bots.back(), bot, "bot_spawned"' in ensure_population

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
        questing,
        "ObjectAccessor::GetUnit(*bot, state.QuestWork.SelectedTargetGuid)",
        "selectedMatchesPlan",
        "if (!objectiveTarget)",
        "objectiveTarget = SelectQuestObjectiveTarget(bot, plan);",
        "state.QuestWork.SelectedTargetGuid = objectiveTarget->GetGUID();",
        "state.TargetGuid = objectiveTarget->GetGUID();",
        "BotClassSpecActionProfileStore::Build(bot, role.c_str())",
        "result.Action = \"move_to_quest_mob\";",
        "BotActionResult pull = executor.Pull(bot, objectiveTarget);",
    )

    assert "TrySmartGearDecision(state, bot, power, stage, chosenActivity.Activity, situation, action)" in update_bot
    assert "state.LastDecisionHandler = \"smart_loot\";" in update_bot
    assert_ordered(
        update_bot,
        "bool hasNearbyQuestGiver = _config.AllowQuesting && HasNearbySupportedQuestGiver(bot, state);",
        "&& (chosenActivity.Activity == BotProgressionActivity::Questing || hasActiveQuestObjective || _config.QuestFirst || state.NewlyAcceptedQuestId || hasNearbyQuestGiver)",
        "TryQuesting(state, bot, power, stage, chosenActivity.Activity)",
        "TrySmartGearDecision(state, bot, power, stage, chosenActivity.Activity, situation, action)",
        "TryProfessionMemoryAction(state, bot, power, stage, chosenActivity.Activity, situation, action)",
    )
    assert "BotGearUpgradeEvaluation evaluation = BotLongTermProgressionBrain::EvaluateGearUpgrade(bot);" in mgr
    assert "lootDecision = evaluation.Upgrade ? \"need_upgrade\" : (evaluation.CanEquip || hasValue ? \"greed_value\" : \"pass_invalid\")" in mgr
    assert "bot->EquipItem(equipDest, item, true);" in mgr
    assert "RecordEvent(state, bot, \"smart_loot_decision\"" in mgr
    assert "RecordGearEvaluation(state, bot, evaluation" in mgr
    assert "std::string(eventType) == \"smart_loot_decision\"" in mgr
    assert "EvaluateGearTemplate(Player const* bot, ItemTemplate const* proto" in read(ROOT / "src/server/game/Bots/BotLongTermProgressionBrain.h")
    assert "BotLongTermProgressionBrain::EvaluateGearTemplate" in read(ROOT / "src/server/game/Bots/BotLongTermProgressionBrain.cpp")
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
    assert "SELECT source_type, source_entry, recipe_spell_id, item_id FROM bot_memory_recipe_sources" in mgr
    assert "RecordEvent(state, bot, \"profession_recipe_source\"" in mgr
    assert "state.PreferMaterialMemoryAction = true;" in mgr
    assert "situation = \"profession_recipe_acquisition\";" in mgr
    assert "action = \"plan_profession_recipe_source\";" in mgr
    assert "SELECT source_type, source_entry, item_id, observed_count, map_id, x, y, z FROM bot_memory_material_sources" in mgr
    assert "source\\\":\\\"world_item_source_index" in mgr
    assert "FROM creature_loot_template clt INNER JOIN creature c ON c.id = clt.Entry" in mgr
    assert "FROM gameobject_loot_template glt INNER JOIN gameobject g ON g.id = glt.Entry" in mgr
    assert "ORDER BY ((x - %f) * (x - %f) + (y - %f) * (y - %f)) LIMIT 1" in mgr
    assert "INSERT INTO bot_memory_material_sources" in mgr
    assert "bot->GetMotionMaster()->MovePoint(0, x, y, z, true);" in mgr
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


def test_botauto_diagnosis_and_trace_surface():
    mgr_header = read(ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h")
    mgr = read(BOT_MGR)
    commands = read(BOT_COMMANDS)
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    diagnose = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotDiagnosisJson")
    trace = function_body(mgr, "std::string BotWorldPopulationMgr::GetBotTraceJson")
    build_diagnosis = function_body(mgr, "BotWorldPopulationMgr::BotDiagnosis BotWorldPopulationMgr::BuildBotDiagnosis")
    diagnosis_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson")
    snapshot_json = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotDecisionSnapshotJson")
    trace_entries = function_body(mgr, "std::string BotWorldPopulationMgr::BuildBotTraceEntriesJson")
    record_decision = function_body(mgr, "void BotWorldPopulationMgr::RecordDecision")
    record_trace = function_body(mgr, "void BotWorldPopulationMgr::RecordDecisionTrace")
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
        "decision_fingerprint_hash",
        "decision_fingerprint_repeat_count",
        "decision_fingerprint_failure_count",
        "next_expected_action",
        "suggested_investigation",
    ]:
        assert field in diagnosis_json

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
    ]:
        assert field in trace_entries

    assert "RecordDecisionTrace(state" in record_decision
    assert "state.DecisionTrace.push_back(entry)" in record_trace
    assert "state.DecisionTrace.size() > 64" in record_trace
    assert "debug_schema_version" in debug
    assert "diagnosis" in debug


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
    update_bot = function_body(mgr, "void BotWorldPopulationMgr::UpdateBot")
    build_policy = function_body(mgr, "BotWorldPopulationMgr::BotDeathRecoveryPolicy BotWorldPopulationMgr::BuildDeathRecoveryPolicy")

    assert re.search(r"^BotWorld\.TeleportToCenterOnDeath\s*=\s*0$", conf, re.MULTILINE)
    assert "policy.CenterFallbackEnabled = _config.TeleportToCenterOnDeath;" in build_policy
    assert "policy.MaxDeathsBeforeFallback = _config.MaxDeathsBeforeFallback;" in build_policy
    assert "recovery.RepeatedDeath = state.RecentDeathCount >= policy.MaxDeathsBeforeFallback;" in recover
    assert 'mode == "configured_center_fallback" && (!policy.CenterFallbackEnabled || !recovery.RepeatedDeath)' in recover
    assert 'RecordEvent(state, bot, "death_recovery_started"' in update_bot
    assert 'RecordEvent(state, bot, "resurrected"' in update_bot
    assert 'RecordEvent(state, bot, "teleport_fallback_used"' in update_bot
    assert 'RecordEvent(state, bot, "death_recovery_failed"' in update_bot


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
    assert "BOTWORLD_AUTOSTART ?= 1" in makefile
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
