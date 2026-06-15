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


def test_server_start_autonomy_disabled_contract():
    conf = read(WORLDSERVER_CONF)
    commands = read(BOT_COMMANDS)
    startup = function_body(commands, "void OnStartup() override")

    assert re.search(r"^BotWorld\.AutoStart\s*=\s*0$", conf, re.MULTILINE)
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
        "ResolveNearPlayerSpawnPlacement(placement)",
        "ResolveConfiguredCenterSpawnPlacement(placement)",
    )
    assert "_config.UseSavedPosition" in resolve_placement
    assert "_config.AllowConfiguredCenterFallback" in resolve_placement


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
        "bot_policy_models",
        "bot_policy_evaluations",
    ]


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

    assert "BOTWORLD_AUTOSTART ?= 0" in makefile
    assert "BOTWORLD_AUTOSTART_RECORDING ?= 0" in makefile
    assert "BOTWORLD_RECORDING_WINDOW_MINUTES ?= 30" in makefile
    assert "BotWorld.AutoStart = $(BOTWORLD_AUTOSTART)" in makefile
    assert "BotWorld.AutoStartRecording = $(BOTWORLD_AUTOSTART_RECORDING)" in makefile
    assert "BotWorld.AutoRecordingWindowMinutes = $(BOTWORLD_RECORDING_WINDOW_MINUTES)" in makefile


def test_player_bot_chase_movement_inform_does_not_deref_non_creature_owner():
    chase = read(CHASE_MOVEMENT)
    inform = function_body(chase, "inline void DoMovementInform")

    assert "if (!owner->IsCreature())" in inform
    assert_ordered(inform, "if (!owner->IsCreature())", "return;", "owner->ToCreature()->AI()")
