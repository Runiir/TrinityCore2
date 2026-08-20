#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"

#include <array>
#include <functional>
#include <iomanip>
#include <map>
#include <sstream>

namespace
{
struct CalibrationExecuteHealthWindow
{
    char const* Phase;
    uint32 StartMs;
    uint32 EndMs;
    uint8 TargetHealthPct;
    uint8 LowerBoundPct;
    bool LowerBoundInclusive;
    uint8 UpperBoundPct;
    bool UpperBoundInclusive;
};

static constexpr uint32 CalibrationSingleTargetDurationMs = 300000;
static constexpr std::array<CalibrationExecuteHealthWindow, 5> CalibrationExecuteHealthWindows = {{
    { "above_90",       0,  30000, 95, 90, false, 100, true  },
    { "between_35_90", 30000, 195000, 50, 35, false,  90, true  },
    { "between_25_35",195000, 225000, 30, 25, false,  35, true  },
    { "between_20_25",225000, 240000, 22, 20, false,  25, true  },
    { "below_20",     240000, 300000, 19,  0, true,   20, false },
}};

char const* RuntimeModeName(BotWorldRuntimeMode mode)
{
    switch (mode)
    {
        case BotWorldRuntimeMode::AlwaysOnAutonomy: return "always_on_autonomy";
        case BotWorldRuntimeMode::CalibrationFixture: return "calibration_fixture";
        case BotWorldRuntimeMode::ReplayFixture: return "replay_fixture";
        case BotWorldRuntimeMode::ManualExperiment: return "manual_experiment";
    }
    return "unknown";
}
}

void BotWorldPopulationMgr::AppendCombatCalibrationSummaryJson(
    std::ostringstream& json, uint64 nowMs,
    std::function<void(std::map<uint32, CalibrationMetrics> const&, bool)> const& writeBots) const
{
    BotCalibrationFixtureContractGenerated::SpecContract const*
        fixtureSpecContract =
            BotCalibrationFixtureContractGenerated::FindSpec(
                Cohort().CalibrationTargetSpec);
    double warmupSeconds = Cohort().CalibrationStartedMs
        ? double((Cohort().CalibrationScoredStartedMs ? Cohort().CalibrationScoredStartedMs : nowMs) - Cohort().CalibrationStartedMs) / 1000.0 : 0.0;
    double scoredSeconds = Cohort().CalibrationScoredStartedMs
        ? double((Cohort().CalibrationScoredEndedMs ? Cohort().CalibrationScoredEndedMs : nowMs) - Cohort().CalibrationScoredStartedMs) / 1000.0 : 0.0;
    std::map<uint32, CalibrationMetrics> const& executeMetricsByGuid =
        Cohort().CalibrationWindowComplete && Cohort().CalibrationPreviousWindowValid
            ? Cohort().CalibrationPreviousMetrics
            : Cohort().CalibrationMetricsByGuid;
    auto const executeMetricsItr = executeMetricsByGuid.find(
        Cohort().CalibrationTargetGuid.GetCounter());
    CalibrationMetrics const* executeMetrics = executeMetricsItr == executeMetricsByGuid.end()
        ? nullptr : &executeMetricsItr->second;
    json << "{\"ok\":" << (Cohort().CalibrationFailureReason.empty() ? "true" : "false")
         << ",\"action\":\"botauto_calibrate_status\",\"cohort_id\":\"" << JsonEscape(Cohort().Id)
         << "\",\"server_epoch\":" << _serverEpoch
         << ",\"attempt_id\":" << Cohort().AttemptId
         << ",\"active\":" << (Cohort().CalibrationActive ? "true" : "false")
         << ",\"failure_reason\":"
         << (Cohort().CalibrationFailureReason.empty()
                ? "null"
                : "\"" + JsonEscape(Cohort().CalibrationFailureReason) + "\"")
         << ",\"runtime_mode\":\"" << RuntimeModeName(Cohort().RuntimeMode) << "\""
         << ",\"non_certifying_assistance\":" << (Cohort().NonCertifyingAssistance ? "true" : "false")
         << ",\"window_complete\":" << (Cohort().CalibrationWindowComplete ? "true" : "false")
         << ",\"mode\":\"" << JsonEscape(Cohort().CalibrationMode) << "\""
         << ",\"target_spec\":\"" << JsonEscape(Cohort().CalibrationTargetSpec) << "\""
         << ",\"target_guid\":" << Cohort().CalibrationTargetGuid.GetCounter()
         << ",\"seed\":" << Cohort().CalibrationSeed
         << ",\"profile_generation\":" << Cohort().PinnedProfileGeneration
         << ",\"profile_content_hash\":\"" << JsonEscape(Cohort().PinnedProfileContentHash) << "\""
         << ",\"runtime_authority\":\"explicit_sql_rule_profiles\""
         << ",\"generic_ml_runtime_authority\":false"
         << ",\"isolated_from_route_telemetry\":true"
         << ",\"damage_basis\":\"effective_or_unmitigated\""
         << ",\"fixture_contract\":{\"schema\":\""
         << BotCalibrationFixtureContractGenerated::Schema
         << "\",\"content_sha256\":\""
         << BotCalibrationFixtureContractGenerated::ContentSha256
         << "\",\"upstream_revision\":\""
         << BotCalibrationFixtureContractGenerated::UpstreamRevision
         << "\"}"
         << ",\"fixture_target\":{\"isolated_single_target\":"
         << (Cohort().CalibrationMode == "single_target_300" ? "true" : "false")
         << ",\"entry\":" << Cohort().CalibrationFixtureTargetEntry
         << ",\"expected\":{\"entry\":"
         << BotCalibrationFixtureContractGenerated::TargetEntry
         << ",\"level\":"
         << Cohort().CalibrationFixtureExpectedTargetLevel
         << ",\"armor\":"
         << Cohort().CalibrationFixtureExpectedTargetArmor
         << ",\"creature_type\":"
         << Cohort().CalibrationFixtureExpectedTargetCreatureType
         << ",\"max_health\":"
         << Cohort().CalibrationFixtureExpectedTargetMaxHealth
         << ",\"passive\":true,\"runtime_min_distance_yards\":"
         << (fixtureSpecContract
                ? fixtureSpecContract->RuntimeMinimumDistanceYards : 0.0f)
         << ",\"runtime_max_distance_yards\":"
         << (fixtureSpecContract
                ? fixtureSpecContract->RuntimeMaximumDistanceYards : 0.0f)
         << '}'
         << ",\"observed_at_provisioning\":{\"observed_at_ms\":"
         << Cohort().CalibrationFixtureTargetProvisionedAtMs
         << ",\"entry\":" << Cohort().CalibrationFixtureTargetEntry
         << ",\"guid\":"
         << Cohort().CalibrationFixtureTargetGuid.GetCounter()
         << ",\"level\":"
         << Cohort().CalibrationFixtureObservedTargetLevel
         << ",\"armor\":"
         << Cohort().CalibrationFixtureObservedTargetArmor
         << ",\"creature_type\":"
         << Cohort().CalibrationFixtureObservedTargetCreatureType
         << ",\"creature_type_mask\":"
         << Cohort().CalibrationFixtureObservedTargetCreatureTypeMask
         << ",\"max_health\":"
         << Cohort().CalibrationFixtureObservedTargetMaxHealth
         << ",\"map_id\":" << Cohort().CalibrationFixtureTargetMapId
         << ",\"x\":" << Cohort().CalibrationFixtureTargetX
         << ",\"y\":" << Cohort().CalibrationFixtureTargetY
         << ",\"z\":" << Cohort().CalibrationFixtureTargetZ << '}'
         << ",\"observed_before_scoring\":{\"observed_at_ms\":"
         << Cohort().CalibrationFixtureTargetObservedBeforeScoringAtMs
         << ",\"before_scoring\":"
         << (Cohort().CalibrationFixtureTargetObservedBeforeScoringAtMs
                && Cohort().CalibrationScoredStartedMs
                && Cohort().CalibrationFixtureTargetObservedBeforeScoringAtMs
                    <= Cohort().CalibrationScoredStartedMs ? "true" : "false")
         << ",\"entry\":" << Cohort().CalibrationFixtureTargetEntry
         << ",\"guid\":"
         << Cohort().CalibrationFixtureBeforeScoringTargetGuid.GetCounter()
         << ",\"level\":"
         << Cohort().CalibrationFixtureBeforeScoringTargetLevel
         << ",\"armor\":"
         << Cohort().CalibrationFixtureBeforeScoringTargetArmor
         << ",\"creature_type\":"
         << Cohort().CalibrationFixtureBeforeScoringTargetCreatureType
         << ",\"creature_type_mask\":"
         << Cohort().CalibrationFixtureBeforeScoringTargetCreatureTypeMask
         << ",\"max_health\":"
         << Cohort().CalibrationFixtureBeforeScoringTargetMaxHealth
         << ",\"map_id\":"
         << Cohort().CalibrationFixtureBeforeScoringTargetMapId
         << ",\"x\":" << Cohort().CalibrationFixtureBeforeScoringTargetX
         << ",\"y\":" << Cohort().CalibrationFixtureBeforeScoringTargetY
         << ",\"z\":" << Cohort().CalibrationFixtureBeforeScoringTargetZ
         << ",\"bot_target_distance\":"
         << Cohort().CalibrationFixtureBeforeScoringBotTargetDistance
         << ",\"in_combat\":"
         << (Cohort().CalibrationFixtureBeforeScoringTargetInCombat ? "true" : "false")
         << ",\"has_victim\":"
         << (Cohort().CalibrationFixtureBeforeScoringTargetHasVictim ? "true" : "false") << '}'
         << ",\"scored_passive_observation\":{\"sample_count\":"
         << Cohort().CalibrationFixtureTargetPassiveObservationSampleCount
         << ",\"target_guid\":"
         << Cohort().CalibrationFixtureTargetGuid.GetCounter()
         << ",\"window_started_at_ms\":"
         << Cohort().CalibrationScoredStartedMs
         << ",\"window_ended_at_ms\":"
         << Cohort().CalibrationScoredEndedMs
         << ",\"first_sample_at_ms\":"
         << Cohort().CalibrationFixtureTargetFirstPassiveObservedAtMs
         << ",\"last_sample_at_ms\":"
         << Cohort().CalibrationFixtureTargetLastPassiveObservedAtMs
         << ",\"maximum_sample_gap_ms\":"
         << Cohort().CalibrationFixtureTargetMaximumPassiveObservationGapMs
         << ",\"victim_observation_sample_count\":"
         << Cohort().CalibrationFixtureTargetVictimObservationSampleCount
         << ",\"target_attack_attempt_event_count\":"
         << Cohort().CalibrationFixtureTargetAttackEventCount
         << ",\"target_originated_damage_event_count\":"
         << Cohort().CalibrationFixtureTargetOriginatedDamageEventCount
         << ",\"target_attack_event_count\":"
         << Cohort().CalibrationFixtureTargetAttackEventCount
                + Cohort().CalibrationFixtureTargetOriginatedDamageEventCount
         << ",\"passive\":"
         << (Cohort().CalibrationFixtureTargetPassiveObservationSampleCount
                && !Cohort().CalibrationFixtureTargetVictimObservationSampleCount
                && !Cohort().CalibrationFixtureTargetAttackEventCount
                && !Cohort().CalibrationFixtureTargetOriginatedDamageEventCount
                ? "true" : "false") << '}'
         << ",\"target_attack_observation_sample_count\":"
         << Cohort().CalibrationFixtureTargetPassiveObservationSampleCount
         << ",\"target_attack_event_count\":"
         << Cohort().CalibrationFixtureTargetAttackEventCount
                + Cohort().CalibrationFixtureTargetOriginatedDamageEventCount
         << ",\"runtime_guid\":"
         << Cohort().CalibrationFixtureTargetGuid.GetCounter()
         << ",\"map_id\":" << Cohort().CalibrationFixtureTargetMapId
         << ",\"x\":" << Cohort().CalibrationFixtureTargetX
         << ",\"y\":" << Cohort().CalibrationFixtureTargetY
         << ",\"z\":" << Cohort().CalibrationFixtureTargetZ
         << ",\"nearest_other_hostile_clearance\":"
         << Cohort().CalibrationFixtureTargetNearestHostileClearance
         << ",\"provisioned_at_ms\":"
         << Cohort().CalibrationFixtureTargetProvisionedAtMs
         << ",\"profile_lane\":\""
         << JsonEscape(Cohort().CalibrationFixtureProfileLane) << "\""
         << ",\"bot_spawn_x\":" << Cohort().CalibrationFixtureBotSpawnX
         << ",\"bot_spawn_y\":" << Cohort().CalibrationFixtureBotSpawnY
         << ",\"bot_spawn_z\":" << Cohort().CalibrationFixtureBotSpawnZ
         << ",\"bot_target_distance\":"
         << Cohort().CalibrationFixtureBotTargetDistance
         << ",\"native_line_of_sight\":"
         << (Cohort().CalibrationFixtureNativeLineOfSight ? "true" : "false")
         << ",\"native_path_reachable\":"
         << (Cohort().CalibrationFixtureNativePathReachable ? "true" : "false")
         << ",\"native_melee_reachable\":"
         << (Cohort().CalibrationFixtureNativeMeleeReachable ? "true" : "false")
         << ",\"native_dry_land\":"
         << (Cohort().CalibrationFixtureNativeDryLand ? "true" : "false")
         << ",\"geometry_validated\":"
         << (Cohort().CalibrationFixtureGeometryValidated ? "true" : "false")
         << ",\"provisioned_before_scoring\":"
         << (Cohort().CalibrationFixtureTargetProvisionedAtMs
                && (!Cohort().CalibrationScoredStartedMs
                    || Cohort().CalibrationFixtureTargetProvisionedAtMs
                        <= Cohort().CalibrationScoredStartedMs)
                ? "true" : "false") << '}'
         << ",\"phase\":\"" << (Cohort().CalibrationScoredStartedMs ? (Cohort().CalibrationWindowComplete ? "complete" : "scored") : "warmup") << "\""
         << ",\"window_seconds\":300"
         << ",\"warmup_seconds\":" << std::fixed << std::setprecision(3) << warmupSeconds
         << ",\"scored_seconds\":" << std::fixed << std::setprecision(3) << scoredSeconds
         << ",\"scored_started_at_ms\":" << Cohort().CalibrationScoredStartedMs
         << ",\"scored_ended_at_ms\":" << Cohort().CalibrationScoredEndedMs
         << ",\"reset_applied\":" << (!Cohort().CalibrationResetId.empty() ? "true" : "false")
         << ",\"reset_id\":\"" << JsonEscape(Cohort().CalibrationResetId) << "\""
         << ",\"cross_window_event_count\":" << Cohort().CalibrationCrossWindowEventCount
         << ",\"excluded_boundary_damage_event_count\":"
         << Cohort().CalibrationExcludedBoundaryDamageEventCount
         << ",\"current_damage_phase\":\"" << JsonEscape(Cohort().CalibrationCurrentDamagePhase) << "\""
         << ",\"normalization\":{\"gear_basis\":\"equipped_clone_average_item_level\""
         << ",\"buff_basis\":\"" << (IsSelfProvidedCalibrationBaseline()
            ? "self_provided_consumables"
            : (Cohort().Config.CombatCalibrationReferenceConditions
                ? "exact_static_fixture_auras" : "stonecore_party_owned_buffs")) << "\""
         << ",\"flask\":" << (IsSelfProvidedCalibrationBaseline()
            || Cohort().Config.CombatCalibrationReferenceConditions ? "true" : "false")
         << ",\"heroism_window_seconds\":0"
         << ",\"external_power_infusion_windows_seconds\":[]"
         << ",\"external_power_infusion_source_count\":0"
         << ",\"dark_intent_base\":false"
         << ",\"dark_intent_proc_uptime_pct\":0"
         << ",\"food_buff_spell_id\":"
         << (IsSelfProvidedCalibrationBaseline() && fixtureSpecContract
                ? fixtureSpecContract->FoodAuraSpellId
                : (Cohort().Config.CombatCalibrationReferenceConditions
                    && (Cohort().CalibrationTargetSpec == "shadow_priest" || Cohort().CalibrationTargetSpec == "balance_druid")
                    ? 87547 : 0))
         << ",\"synapse_springs_windows_seconds\":[]"
         << ",\"dispersion_cast_cap\":0"
         << ",\"potions\":" << (IsSelfProvidedCalibrationBaseline() ? "true" : "false")
         << ",\"engineering_cooldowns\":false"
         << ",\"racial_cooldowns\":false"
         << ",\"dynamic_consumable_actions\":" << (IsSelfProvidedCalibrationBaseline() ? "true" : "false")
         << ",\"consumables\":" << (IsSelfProvidedCalibrationBaseline() ? "true" : "false")
         << ",\"target_debuffs\":" << (Cohort().Config.CombatCalibrationReferenceConditions
            && !IsSelfProvidedCalibrationBaseline() ? "true" : "false")
         << ",\"reference_conditions\":" << (Cohort().Config.CombatCalibrationReferenceConditions
            && !IsSelfProvidedCalibrationBaseline() ? "true" : "false")
         << ",\"reference_class\":\""
         << (IsSelfProvidedCalibrationBaseline()
                ? "self_provided_baseline" : "controlled_live_parity") << "\""
         << ",\"external_bis_target_configured\":false"
         << ",\"execute_threshold_windows\":";
    if (Cohort().CalibrationMode != "single_target_300")
        json << "null";
    else
    {
        json << "{\"schema\":\"wowsims_cata_single_target_health_schedule_v1\""
             << ",\"source_authority\":\"pinned_wowsims_cata_core_test_utils_make_single_target_encounter\""
             << ",\"source_duration_ms\":" << CalibrationSingleTargetDurationMs
             << ",\"source_duration_variation_ms\":0"
             << ",\"source_execute_proportions\":{\"90\":0.9,\"35\":0.35,\"25\":0.25,\"20\":0.2}"
             << ",\"interval_semantics\":\"start_inclusive_end_exclusive\""
             << ",\"fixture_only\":true,\"non_certifying\":true,\"windows\":[";
        for (size_t index = 0; index < CalibrationExecuteHealthWindows.size(); ++index)
        {
            if (index)
                json << ',';
            CalibrationExecuteHealthWindow const& phase = CalibrationExecuteHealthWindows[index];
            CalibrationMetrics::TargetHealthPhaseObservation const* observation = executeMetrics
                ? &executeMetrics->TargetHealthPhaseObservations[index] : nullptr;
            uint64 const minimumHealth = observation && observation->SampleCount
                ? observation->MinimumObservedHealth : 0;
            uint64 const minimumMaxHealth = observation && observation->SampleCount
                ? observation->MinimumObservedMaxHealth : 0;
            uint64 const minimumPreDamageHealth = observation
                && observation->DamageEventSampleCount
                    ? observation->MinimumPreDamageHealth : 0;
            uint64 const minimumProjectedPostDamageHealth = observation
                && observation->DamageEventSampleCount
                    ? observation->MinimumProjectedPostDamageHealth : 0;
            uint64 const minimumDamageEventMaxHealth = observation
                && observation->DamageEventSampleCount
                    ? observation->MinimumDamageEventMaxHealth : 0;
            json << "{\"phase\":\"" << phase.Phase << "\""
                 << ",\"start_ms\":" << phase.StartMs
                 << ",\"end_ms\":" << phase.EndMs
                 << ",\"configured_target_health_pct\":" << uint32(phase.TargetHealthPct)
                 << ",\"health_pct_lower_bound\":" << uint32(phase.LowerBoundPct)
                 << ",\"lower_bound_inclusive\":" << (phase.LowerBoundInclusive ? "true" : "false")
                 << ",\"health_pct_upper_bound\":" << uint32(phase.UpperBoundPct)
                 << ",\"upper_bound_inclusive\":" << (phase.UpperBoundInclusive ? "true" : "false")
                 << ",\"observation\":{\"sample_count\":"
                 << (observation ? observation->SampleCount : 0)
                 << ",\"first_elapsed_ms\":"
                 << (observation ? observation->FirstObservedElapsedMs : 0)
                 << ",\"last_elapsed_ms\":"
                 << (observation ? observation->LastObservedElapsedMs : 0)
                 << ",\"minimum_observed_health\":" << minimumHealth
                 << ",\"maximum_observed_health\":"
                 << (observation ? observation->MaximumObservedHealth : 0)
                 << ",\"minimum_observed_max_health\":" << minimumMaxHealth
                 << ",\"maximum_observed_max_health\":"
                 << (observation ? observation->MaximumObservedMaxHealth : 0)
                 << ",\"damage_event_sample_count\":"
                 << (observation ? observation->DamageEventSampleCount : 0)
                 << ",\"first_damage_event_elapsed_ms\":"
                 << (observation ? observation->FirstDamageEventElapsedMs : 0)
                 << ",\"last_damage_event_elapsed_ms\":"
                 << (observation ? observation->LastDamageEventElapsedMs : 0)
                 << ",\"minimum_pre_damage_health\":" << minimumPreDamageHealth
                 << ",\"maximum_pre_damage_health\":"
                 << (observation ? observation->MaximumPreDamageHealth : 0)
                 << ",\"minimum_projected_post_damage_health\":"
                 << minimumProjectedPostDamageHealth
                 << ",\"maximum_projected_post_damage_health\":"
                 << (observation ? observation->MaximumProjectedPostDamageHealth : 0)
                 << ",\"minimum_damage_event_max_health\":"
                 << minimumDamageEventMaxHealth
                 << ",\"maximum_damage_event_max_health\":"
                 << (observation ? observation->MaximumDamageEventMaxHealth : 0)
                 << ",\"maximum_damage_event\":"
                 << (observation ? observation->MaximumDamageEvent : 0)
                 << "}}";
        }
        json << "]}";
    }
    json << ",\"comparison_policy\":\"sustained_completed_windows_only\"}"
         << ",\"completed_windows\":{\"single_target\":" << Cohort().CalibrationCompletedSingleWindows
         << ",\"aoe\":" << Cohort().CalibrationCompletedAoeWindows << "}"
         << ",\"bots\":";
    writeBots(Cohort().CalibrationMetricsByGuid, false);
    json << ",\"previous_window\":";
    if (!Cohort().CalibrationPreviousWindowValid)
        json << "null";
    else
    {
        json << "{\"mode\":\"" << JsonEscape(Cohort().CalibrationMode) << "\",\"bots\":";
        writeBots(Cohort().CalibrationPreviousMetrics, true);
        json << '}';
    }
    json << ",\"best_windows\":{\"single_target\":";
    if (Cohort().CalibrationBestSingleMetrics.empty())
        json << "null";
    else
        writeBots(Cohort().CalibrationBestSingleMetrics, true);
    json << ",\"aoe\":";
    if (Cohort().CalibrationBestAoeMetrics.empty())
        json << "null";
    else
        writeBots(Cohort().CalibrationBestAoeMetrics, true);
    json << '}';
    json << ",\"failure_reason\":null}";
}
