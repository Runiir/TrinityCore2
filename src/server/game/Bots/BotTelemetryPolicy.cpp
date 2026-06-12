#include "Bots/BotTelemetryPolicy.h"

#include <algorithm>

namespace
{
bool IsFailureResult(std::string const& result)
{
    return result == "failed"
        || result == "death"
        || result.find("failed") != std::string::npos
        || result.find("blocked") != std::string::npos
        || result.find("out_of_range") != std::string::npos;
}

bool IsReplayEvent(std::string const& event, std::string const& result)
{
    return event == "death"
        || event == "stuck_detected"
        || event == "objective_failed"
        || event == "quest_failure"
        || event == "boss_mechanic_failure"
        || event == "raid_wipe"
        || event == "path_failure"
        || result == "reward_blocked"
        || result == "out_of_range_loot"
        || result == "object_not_found"
        || result == "gossip_failed"
        || result == "interaction_failed";
}

bool IsKeepEvent(std::string const& event)
{
    return event == "death"
        || event == "resurrected"
        || event == "stuck_detected"
        || event == "objective_failed"
        || event == "quest_completed"
        || event == "quest_accepted"
        || event == "boss_killed"
        || event == "raid_boss_killed"
        || event == "raid_wipe"
        || event == "interrupt_failed"
        || event == "gear_upgrade"
        || event == "level_up";
}

bool IsSampleEvent(std::string const& event, std::string const& situation)
{
    return event == "spell_cast"
        || event == "combat_tick"
        || event == "objective_progress"
        || event == "objective_search"
        || event == "move_started"
        || event == "gear_evaluated"
        || event == "mob_killed"
        || situation == "travel"
        || situation == "wander";
}

bool Sample(uint32 sequence, uint32 rate)
{
    rate = std::max<uint32>(1, rate);
    return (sequence % rate) == 0;
}

BotTelemetryPolicyDecision Decide(BotTelemetryPolicyInput const& input, BotTelemetryPolicyConfig const& config, uint32 sequence, bool decision)
{
    BotTelemetryPolicyDecision result;
    std::string const& event = input.eventType;
    std::string const& res = input.result;

    bool failure = input.failure || IsFailureResult(res) || event == "death" || event == "objective_failed" || event == "interrupt_failed";
    bool forced = (failure && config.alwaysRecordFailures)
        || (input.rare && config.alwaysRecordRareStates)
        || (input.intervention && config.alwaysRecordInterventions);

    if (IsReplayEvent(event, res))
    {
        result.importance = BotTelemetryImportance::Replay;
        result.score = 1.0f;
        result.reason = "replay_trigger";
    }
    else if (IsKeepEvent(event) || forced)
    {
        result.importance = BotTelemetryImportance::Keep;
        result.score = forced ? 0.86f : 0.80f;
        result.reason = forced ? "configured_always_record" : "high_value_event";
    }
    else if (event == "combat_started" && input.rare)
    {
        result.importance = BotTelemetryImportance::Clip;
        result.score = 0.78f;
        result.reason = "high_value_combat_start";
    }
    else if (event == "loot_received" && res != "ok")
    {
        result.importance = BotTelemetryImportance::Clip;
        result.score = 0.82f;
        result.reason = "loot_failure";
    }
    else if (decision || IsSampleEvent(event, input.situation))
    {
        result.importance = BotTelemetryImportance::Sample;
        result.score = 0.35f;
        result.reason = "normal_sampled_telemetry";
    }
    else
    {
        result.importance = BotTelemetryImportance::Sample;
        result.score = 0.25f;
        result.reason = "default_sampled_telemetry";
    }

    if (failure)
        result.score = std::max(result.score, 0.90f);
    if (input.rare)
        result.score = std::max(result.score, 0.78f);
    if (input.intervention)
        result.score = std::max(result.score, 0.82f);
    if (event == "quest_completed" || event == "quest_accepted" || event == "boss_killed" || event == "raid_boss_killed")
        result.score = std::max(result.score, 0.80f);

    if (result.score >= config.minReplayImportance || result.importance == BotTelemetryImportance::Replay)
        result.importance = BotTelemetryImportance::Replay;
    else if (result.score >= config.minClipImportance)
        result.importance = BotTelemetryImportance::Clip;

    result.openClip = result.score >= config.minClipImportance;
    result.writeReplay = result.score >= config.minReplayImportance || result.importance == BotTelemetryImportance::Replay;

    bool sampled = !config.smartSampling
        || forced
        || result.importance == BotTelemetryImportance::Keep
        || result.importance == BotTelemetryImportance::Clip
        || result.importance == BotTelemetryImportance::Replay
        || Sample(sequence, decision ? config.normalDecisionSampleRate : config.normalEventSampleRate);

    if (decision)
        result.writeDecision = sampled;
    else
        result.writeEvent = sampled;

    if (!sampled && result.importance == BotTelemetryImportance::Sample)
    {
        result.importance = BotTelemetryImportance::Drop;
        result.reason = "sampled_out";
    }

    return result;
}
}

BotTelemetryPolicyDecision BotTelemetryPolicy::DecideEvent(BotTelemetryPolicyInput const& input, BotTelemetryPolicyConfig const& config, uint32 sequence)
{
    return Decide(input, config, sequence, false);
}

BotTelemetryPolicyDecision BotTelemetryPolicy::DecideDecision(BotTelemetryPolicyInput const& input, BotTelemetryPolicyConfig const& config, uint32 sequence)
{
    return Decide(input, config, sequence, true);
}
