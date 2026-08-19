#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotExperienceLearningPolicy.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Creature.h"
#include "Map.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "Unit.h"

#include <algorithm>
#include <sstream>
#include <string>

namespace
{
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

std::string BotWorldPopulationMgr::BuildRawJson(Player* bot, Unit const* target) const
{
    WorldBotState const* state = nullptr;
    for (WorldBotState const& candidate : Party().Bots)
        if (bot && candidate.Guid == bot->GetGUID())
        {
            state = &candidate;
            break;
        }

    std::ostringstream json;
    json << "{\"bot_guid\":" << (bot ? bot->GetGUID().GetCounter() : 0)
         << ",\"map_id\":" << (bot ? bot->GetMapId() : 0)
         << ",\"zone_id\":" << (bot ? bot->GetZoneId() : 0)
         << ",\"area_id\":" << (bot ? bot->GetAreaId() : 0)
         << ",\"level\":" << (bot ? uint32(bot->getLevel()) : 0)
         << ",\"hp_pct\":";
    if (bot && bot->GetMaxHealth())
        json << (float(bot->GetHealth()) / float(bot->GetMaxHealth()));
    else
        json << 0.0f;
    json << ",\"in_combat\":" << (bot && bot->IsInCombat() ? "true" : "false")
         << ",\"moving\":" << (bot && (bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING)) ? "true" : "false")
         << ",\"x\":" << (bot ? bot->GetPositionX() : 0.0f)
         << ",\"y\":" << (bot ? bot->GetPositionY() : 0.0f)
         << ",\"z\":" << (bot ? bot->GetPositionZ() : 0.0f)
         << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
         << ",\"target_entry\":";
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        json << creature->GetEntry();
    else
        json << 0;
    json << ",\"target_level\":" << (target ? uint32(target->getLevel()) : 0)
         << ",\"target_alive\":" << (target && target->IsAlive() ? "true" : "false")
         << ",\"target_cast_spell_id\":";
    if (target)
    {
        if (Spell* spell = target->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            json << (spell->GetSpellInfo() ? spell->GetSpellInfo()->Id : 0);
        else
            json << 0;
    }
    else
        json << 0;
    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();
    bool targetMatchesObjective = state && targetEntry && (state->QuestWork.RequiredEntry <= 0 || uint32(state->QuestWork.RequiredEntry) == targetEntry);
    bool dummyAllowed = false;
    if (state && target)
    {
        QuestObjectivePlan plan;
        dummyAllowed = GetQuestObjectivePlan(bot, state->QuestWork.ActiveQuestId, state->QuestWork.ObjectiveIndex,
            state->QuestWork.ObjectiveType == "use_ability_on_dummy" ? QuestObjectiveType::UseAbilityOnDummy :
            (state->QuestWork.ObjectiveType == "cast_spell_on_target" ? QuestObjectiveType::CastSpellOnTarget : QuestObjectiveType::Kill), plan)
            && IsTrainingDummyAllowedForQuest(plan, target);
    }
    json << ",\"quest_phase\":\"" << JsonEscape(state ? state->QuestWork.Phase : "idle") << "\""
         << ",\"desired_melee_attack_target_guid\":" << (state ? state->DesiredMeleeAttackTargetGuid.GetCounter() : 0)
         << ",\"melee_auto_attack_state\":\"" << JsonEscape(state ? state->MeleeAutoAttackState : "inactive") << "\""
         << ",\"melee_auto_attack_suppression_reason\":\"" << JsonEscape(state ? state->MeleeAutoAttackSuppressionReason : "") << "\""
         << ",\"melee_auto_attack_intent_owner\":\"" << JsonEscape(state ? state->LastMeleeAutoAttackIntentOwner : "none") << "\""
         << ",\"melee_auto_attack_intent_kind\":\"" << JsonEscape(state ? state->LastMeleeAutoAttackIntentKind : "stop") << "\""
         << ",\"melee_auto_attack_intent_reason\":\"" << JsonEscape(state ? state->LastMeleeAutoAttackIntentReason : "") << "\""
         << ",\"melee_auto_attack_outcome\":\"" << JsonEscape(state ? state->LastMeleeAutoAttackOutcome : "not_reconciled") << "\""
         << ",\"melee_auto_attack_intent_priority\":" << (state ? uint32(state->LastMeleeAutoAttackIntentPriority) : 0)
         << ",\"melee_auto_attack_candidate_count\":" << (state ? state->LastMeleeAutoAttackCandidateCount : 0)
         << ",\"active_quest_id\":" << (state ? state->QuestWork.ActiveQuestId : 0)
         << ",\"objective_index\":" << (state ? state->QuestWork.ObjectiveIndex : 0)
         << ",\"objective_type\":\"" << JsonEscape(state ? state->QuestWork.ObjectiveType : "none") << "\""
         << ",\"required_entry\":" << (state && state->QuestWork.RequiredEntry > 0 ? uint32(state->QuestWork.RequiredEntry) : 0)
         << ",\"required_item\":" << (state ? state->QuestWork.RequiredItem : 0)
         << ",\"required_spell\":" << (state ? state->QuestWork.RequiredSpell : 0)
         << ",\"target_matches_objective\":" << (targetMatchesObjective ? "true" : "false")
         << ",\"progress_before\":" << (state ? state->QuestWork.ProgressBefore : 0)
         << ",\"progress_after\":" << (state ? state->QuestWork.ProgressAfter : 0)
         << ",\"loot_result\":\"" << JsonEscape(state ? state->LastLootResult : "none") << "\""
         << ",\"loot_items_count\":" << (state ? state->LastLootItemsCount : 0)
         << ",\"loot_money\":" << (state ? state->LastLootMoney : 0)
         << ",\"loot_state_cleared\":" << (state && state->LastLootStateCleared ? "true" : "false")
         << ",\"no_progress_reason\":\"" << JsonEscape(state ? state->LastNoProgressReason : "") << "\""
         << ",\"cooldown_reason\":\"" << JsonEscape(state ? state->QuestWork.FailedReason : "") << "\""
         << ",\"dummy_allowed_by_quest\":" << (dummyAllowed ? "true" : "false")
         << ",\"route_node_id\":\"" << JsonEscape(Cohort().Config.ValidationRouteNodeId) << "\""
         << ",\"route_generation\":" << Party().ValidationRouteGeneration
         << ",\"boss_add_density_phase\":" << (Party().ValidationRouteBossAddDensityPhase ? "true" : "false")
         << ",\"boss_add_density_generation\":" << Party().ValidationRouteBossAddDensityGeneration
         << ",\"boss_add_escape_active\":" << (Party().ValidationRouteBossAddEscapeActive ? "true" : "false")
         << ",\"boss_add_escape_generation\":" << Party().ValidationRouteBossAddEscapeGeneration
         << ",\"boss_add_escape_issued_count\":" << Party().ValidationRouteBossAddEscapeIssuedGuids.size()
         << ",\"boss_add_escape_point\":{\"x\":" << Party().ValidationRouteBossAddEscapeX
         << ",\"y\":" << Party().ValidationRouteBossAddEscapeY << ",\"z\":" << Party().ValidationRouteBossAddEscapeZ << "}"
         << ",\"native_recovery_episode\":"
         << BuildNativeRecoveryEpisodeJson(state) << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildSemanticJson(Player* bot, Unit const* target, char const* situation, BotRolePowerBreakdown const* power, BotProgressionStage stage, BotProgressionActivity activity) const
{
    float hpPct = 1.0f;
    if (bot && bot->GetMaxHealth())
        hpPct = float(bot->GetHealth()) / float(bot->GetMaxHealth());

    std::string situationType = situation ? situation : "idle";
    bool dungeonTrash = bot && bot->GetMap() && bot->GetMap()->IsNonRaidDungeon() && situationType == "dungeon_trash";
    bool bossEncounter = bot && bot->GetMap() && (situationType == "dungeon_boss" || situationType == "raid_boss");
    bool raidEncounter = bossEncounter && bot && bot->GetMap() && bot->GetMap()->IsRaid();
    bool elite = false;
    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        elite = creature->isElite();
        targetEntry = creature->GetEntry();
    }
    uint32 targetCastSpellId = 0;
    if (target)
        if (Spell* spell = const_cast<Unit*>(target)->GetCurrentSpell(CURRENT_GENERIC_SPELL))
            targetCastSpellId = spell->GetSpellInfo() ? spell->GetSpellInfo()->Id : 0;

    BotRolePowerBreakdown localPower;
    if (!power && bot)
    {
        localPower = BotLongTermProgressionBrain::CalculateRolePower(bot);
        power = &localPower;
        stage = BotLongTermProgressionBrain::ClassifyStage(bot, *power);
    }

    std::ostringstream json;
    SemanticOutcomeStats areaStats = GetSemanticOutcomeStats("area", bot ? bot->GetAreaId() : 0);
    SemanticOutcomeStats mobStats = GetSemanticOutcomeStats("mob", targetEntry);
    SemanticOutcomeStats spellStats = GetSemanticOutcomeStats("spell", targetCastSpellId);
    BotLearnedScore activityLearned = bot ? BotExperienceLearningPolicy::ScoreActivity(bot, activity, Cohort().LearningConfig) : BotLearnedScore();
    BotLearnedScore areaLearned = bot ? BotExperienceLearningPolicy::ScoreArea(bot, bot->GetAreaId(), Cohort().LearningConfig) : BotLearnedScore();
    BotLearnedScore mobLearned = (bot && target) ? BotExperienceLearningPolicy::ScoreMob(bot, target, Cohort().LearningConfig) : BotLearnedScore();
    WorldBotState const* workState = nullptr;
    for (WorldBotState const& state : Party().Bots)
        if (bot && state.Guid == bot->GetGUID())
        {
            workState = &state;
            break;
        }
    bool targetMatchesObjective = workState && targetEntry && (workState->QuestWork.RequiredEntry <= 0 || uint32(workState->QuestWork.RequiredEntry) == targetEntry);

    json << "{\"situation_type\":\"" << JsonEscape(situationType) << "\""
         << ",\"role\":\"" << JsonEscape((dungeonTrash || bossEncounter) ? GetDungeonRole(bot) : "solo") << "\""
         << ",\"activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(activity)) << "\""
         << ",\"validation_route\":{\"route_node_id\":\"" << JsonEscape(Cohort().Config.ValidationRouteNodeId)
         << "\",\"route_generation\":" << Party().ValidationRouteGeneration
         << ",\"boss_add_density_phase\":" << (Party().ValidationRouteBossAddDensityPhase ? "true" : "false")
         << ",\"boss_add_density_generation\":" << Party().ValidationRouteBossAddDensityGeneration
         << ",\"boss_add_escape_active\":" << (Party().ValidationRouteBossAddEscapeActive ? "true" : "false")
         << ",\"boss_add_escape_generation\":" << Party().ValidationRouteBossAddEscapeGeneration
         << ",\"boss_add_escape_issued_count\":" << Party().ValidationRouteBossAddEscapeIssuedGuids.size() << "}"
         << ",\"embedding_features\":{\"schema\":\"bot_semantic_phase6_v1\""
         << ",\"area\":" << BuildEmbeddingFeaturesJson(bot, target, "area", bot ? bot->GetAreaId() : 0, situationType.c_str())
         << ",\"mob\":" << BuildEmbeddingFeaturesJson(bot, target, "mob", targetEntry, situationType.c_str())
         << ",\"spell\":" << BuildEmbeddingFeaturesJson(bot, target, "spell", targetCastSpellId, situationType.c_str()) << "}"
         << ",\"learned_outcomes\":{\"area\":" << BuildOutcomeStatsJson(areaStats)
         << ",\"mob\":" << BuildOutcomeStatsJson(mobStats)
         << ",\"spell\":" << BuildOutcomeStatsJson(spellStats);
    uint32 learnedMechanicKey = 0;
    if (bossEncounter)
        learnedMechanicKey = 11;
    else if (dungeonTrash)
        learnedMechanicKey = 10;
    SemanticOutcomeStats mechanicStats = GetSemanticOutcomeStats("mechanic", learnedMechanicKey);
    json << ",\"mechanic\":" << BuildOutcomeStatsJson(mechanicStats) << "}"
         << ",\"learned_policy\":{\"activity\":" << BotExperienceLearningPolicy::ToJson(activityLearned)
         << ",\"area\":" << BotExperienceLearningPolicy::ToJson(areaLearned)
         << ",\"mob\":" << BotExperienceLearningPolicy::ToJson(mobLearned) << "}"
         << ",\"progression\":{\"main_goal\":\"increase_character_power\""
         << ",\"stage\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(stage)) << "\""
         << ",\"role_power_score\":" << (power ? power->Total : 0.0f)
         << ",\"item_level_score\":" << (power ? power->ItemLevelScore : 0.0f)
         << ",\"role_stat_weight_score\":" << (power ? power->RoleStatWeightScore : 0.0f)
         << ",\"weapon_score\":" << (power ? power->WeaponScore : 0.0f)
         << ",\"trinket_score\":" << (power ? power->TrinketScore : 0.0f)
         << ",\"gold_utility_score\":" << (power ? power->GoldUtilityScore : 0.0f) << "}"
         << ",\"self\":{\"hp_pct\":" << hpPct
         << ",\"low_health\":" << (hpPct < 0.35f ? "true" : "false")
         << ",\"level\":" << (bot ? uint32(bot->getLevel()) : 0)
         << ",\"avg_item_level\":" << (bot ? bot->GetAverageItemLevel() : 0.0f)
         << ",\"free_bag_slots\":" << (bot ? bot->GetFreeInventorySpace() : 0)
         << ",\"gold\":" << (bot ? bot->GetMoney() : 0)
         << ",\"dead\":" << (bot && !bot->IsAlive() ? "true" : "false") << "}"
         << ",\"enemy\":{\"present\":" << (target ? "true" : "false")
         << ",\"elite\":" << (elite ? "true" : "false")
         << ",\"safe_open_world_target\":" << (target && !elite && bot && int32(target->getLevel()) <= int32(bot->getLevel()) + 1 ? "true" : "false") << "}";
    json << ",\"quest_work\":{\"quest_phase\":\"" << JsonEscape(workState ? workState->QuestWork.Phase : "idle") << "\""
         << ",\"active_quest_id\":" << (workState ? workState->QuestWork.ActiveQuestId : 0)
         << ",\"objective_index\":" << (workState ? workState->QuestWork.ObjectiveIndex : 0)
         << ",\"objective_type\":\"" << JsonEscape(workState ? workState->QuestWork.ObjectiveType : "none") << "\""
         << ",\"required_entry\":" << (workState && workState->QuestWork.RequiredEntry > 0 ? uint32(workState->QuestWork.RequiredEntry) : 0)
         << ",\"required_item\":" << (workState ? workState->QuestWork.RequiredItem : 0)
         << ",\"required_spell\":" << (workState ? workState->QuestWork.RequiredSpell : 0)
         << ",\"target_entry\":" << targetEntry
         << ",\"target_matches_objective\":" << (targetMatchesObjective ? "true" : "false")
         << ",\"progress_before\":" << (workState ? workState->QuestWork.ProgressBefore : 0)
         << ",\"progress_after\":" << (workState ? workState->QuestWork.ProgressAfter : 0)
         << ",\"loot_result\":\"" << JsonEscape(workState ? workState->LastLootResult : "none") << "\""
         << ",\"loot_items_count\":" << (workState ? workState->LastLootItemsCount : 0)
         << ",\"loot_money\":" << (workState ? workState->LastLootMoney : 0)
         << ",\"loot_state_cleared\":" << (workState && workState->LastLootStateCleared ? "true" : "false")
         << ",\"no_progress_reason\":\"" << JsonEscape(workState ? workState->LastNoProgressReason : "") << "\""
         << ",\"cooldown_reason\":\"" << JsonEscape(workState ? workState->QuestWork.FailedReason : "") << "\""
         << ",\"dummy_allowed_by_quest\":" << (workState && workState->CurrentDummyAllowedByQuest ? "true" : "false") << "}";
    json << ",\"native_recovery_episode\":"
         << BuildNativeRecoveryEpisodeJson(workState);
    if (dungeonTrash)
    {
        DungeonTrashPackFeatures pack = BuildDungeonTrashPackFeatures(bot, target);
        json << ",\"trash_pack\":" << BuildDungeonTrashPackJson(pack)
             << ",\"trash_learned_stats\":" << BuildOutcomeStatsJson(GetSemanticOutcomeStats("mechanic", 10))
             << ",\"trash_action_scores\":{\"interrupt\":" << pack.InterruptPriority
             << ",\"cc\":" << pack.CcValue
             << ",\"aoe\":" << pack.AoeValue
             << ",\"single_target\":" << (target ? 1.0f : 0.0f)
             << ",\"avoid_pull\":" << pack.PullRisk << "}";
    }
    else
        json << ",\"trash_pack\":null,\"trash_action_scores\":null";
    if (bossEncounter)
    {
        BossMechanicFeatures features = BuildBossMechanicFeatures(bot, target);
        uint32 mechanicKey = features.MoveOut ? 1 : (features.MustInterrupt ? 2 : (features.AddsActive ? 5 : (features.RaidDamage ? 4 : 11)));
        json << ",\"boss_mechanics\":" << BuildBossMechanicsJson(features)
             << ",\"boss_learned_stats\":{\"mechanic\":" << BuildOutcomeStatsJson(GetSemanticOutcomeStats("mechanic", mechanicKey))
             << ",\"boss\":" << BuildOutcomeStatsJson(GetSemanticOutcomeStats("mob", features.BossEntry))
             << ",\"cast_spell\":" << BuildOutcomeStatsJson(GetSemanticOutcomeStats("spell", features.CastSpellId)) << "}"
             << ",\"boss_action_scores\":{\"move_out\":" << (features.MoveOut ? features.DangerScore : 0.0f)
             << ",\"interrupt\":" << features.InterruptPriority
             << ",\"switch_adds\":" << (features.AddsActive ? std::min(1.0f, float(features.AddCount) / 4.0f) : 0.0f)
             << ",\"heal_raid\":" << (features.RaidDamage ? std::max(0.0f, 1.0f - features.LowestAllyHpPct) : 0.0f)
             << ",\"single_target\":" << (target ? 1.0f : 0.0f) << "}";
        if (raidEncounter)
        {
            RaidRoleAssignment assignment = BuildRaidRoleAssignment(bot);
            RaidPositioningAnchors anchors = BuildRaidPositioningAnchors(bot, target, assignment, features);
            RaidMechanicAdapter adapter = BuildRaidMechanicAdapter(bot, target, assignment, features);
            RaidGearTargetPlan gearPlan = BuildRaidGearTargetPlan(bot, power ? *power : localPower, stage);
            WorldBotState const* botState = nullptr;
            for (WorldBotState const& state : Party().Bots)
                if (bot && state.Guid == bot->GetGUID())
                {
                    botState = &state;
                    break;
                }
            WorldBotState emptyState;
            HeroicRaidProgression progression = BuildHeroicRaidProgression(botState ? *botState : emptyState, bot, power ? *power : localPower, stage);
            json << ",\"raid_role_assignment\":" << BuildRaidRoleAssignmentJson(assignment)
                 << ",\"raid_positioning_anchors\":" << BuildRaidPositioningAnchorsJson(anchors)
                 << ",\"raid_mechanic_adapter\":" << BuildRaidMechanicAdapterJson(adapter)
                 << ",\"raid_gear_target_plan\":" << BuildRaidGearTargetPlanJson(gearPlan)
                 << ",\"heroic_raid_progression\":" << BuildHeroicRaidProgressionJson(progression);
        }
    }
    else
        json << ",\"boss_mechanics\":null,\"boss_action_scores\":null";
    if (!raidEncounter)
        json << ",\"raid_role_assignment\":null,\"raid_positioning_anchors\":null,\"raid_mechanic_adapter\":null,\"raid_gear_target_plan\":null,\"heroic_raid_progression\":null";
    std::string role = (dungeonTrash || bossEncounter) ? GetDungeonRole(bot) : "dps";
    BotClassSpecActionProfile semanticProfile = BotClassSpecActionProfileStore::Build(bot, role.c_str());
    RoleSaturationState semanticSaturation = BuildRoleSaturationState(bot, target, role.c_str());
    json
         << ",\"objective_state\":\"increase_character_power\""
         << ",\"zone_quest_portfolio\":" << BotProgressionGoalPolicy::QuestPortfolioSummaryJson(workState && workState->QuestWork.ActiveQuestId ? 1 : 0, workState ? workState->ActiveQuestClusterId : 0, workState ? workState->QuestWork.Phase.c_str() : "idle", workState ? workState->LastNoQuestReason.c_str() : "")
         << ",\"action_category\":\"" << JsonEscape(workState ? workState->LastActionCategory : "wait") << "\""
         << ",\"class_spec_profile\":" << semanticProfile.EmbeddingJson()
         << ",\"role_goal\":\"" << JsonEscape(BotProgressionGoalPolicy::RoleGoal(role)) << "\""
         << ",\"role_saturation_state_json\":" << semanticSaturation.ToJson()
         << ",\"recommended_balance_mode\":\"" << JsonEscape(BotRoleSaturationPolicy::ToString(semanticSaturation.RecommendedBalanceMode)) << "\""
         << ",\"saturation_reason\":\"" << JsonEscape(semanticSaturation.SaturationReason) << "\""
         << ",\"profession_goal\":" << BotProgressionGoalPolicy::ProfessionGoalJson(bot, role, BotLongTermProgressionBrain::ToString(activity))
         << ",\"progression_reason\":" << BotProgressionGoalPolicy::ProgressionReason(bot, BotLongTermProgressionBrain::ToString(activity), situationType.c_str())
         << ",\"objective\":{\"main_goal\":\"increase_character_power\",\"questing_allowed\":" << (Cohort().Config.AllowQuesting ? "true" : "false")
         << ",\"dungeons_allowed\":" << (Cohort().Config.AllowDungeons ? "true" : "false")
         << ",\"raids_allowed\":" << (Cohort().Config.AllowRaids ? "true" : "false") << "}}";
    return json.str();
}

RoleSaturationState BotWorldPopulationMgr::BuildRoleSaturationState(Player const* bot, Unit const* target, char const* role, float encounterDanger, float interruptPressure, bool tankBuster, bool adds, bool noValidActions) const
{
    uint32 areaKey = bot ? bot->GetAreaId() : 0;
    SemanticOutcomeStats areaStats = GetSemanticOutcomeStats("area", areaKey);
    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();
    SemanticOutcomeStats mobStats = GetSemanticOutcomeStats("mob", targetEntry);

    float learnedReward = areaStats.Known ? areaStats.AvgReward : 0.0f;
    if (mobStats.Known)
        learnedReward = (learnedReward + mobStats.AvgReward) * 0.5f;
    float learnedDanger = std::max(areaStats.DangerScore, mobStats.DangerScore);
    uint32 samples = areaStats.Samples + mobStats.Samples;
    float learnedConfidence = samples ? std::min(1.0f, float(samples) / 25.0f) : 0.0f;

    BotRoleSaturationInputs inputs = BotRoleSaturationPolicy::BuildInputs(bot, target, role ? role : "dps", encounterDanger, interruptPressure, tankBuster, adds, learnedReward, learnedDanger, learnedConfidence, noValidActions);
    return BotRoleSaturationPolicy::Evaluate(inputs);
}

std::string BotWorldPopulationMgr::BuildConfigJson() const
{
    BotTelemetryBufferConfig const& telemetry = Cohort().TelemetryBuffer.GetConfig();
    std::ostringstream json;
    json << "{\"name\":\"" << JsonEscape(Cohort().Config.Name)
         << "\",\"type\":\"bot_world_autonomy\""
         << ",\"runtime_mode\":\"" << RuntimeModeName(Cohort().RuntimeMode) << "\""
         << ",\"non_certifying_assistance\":" << (Cohort().NonCertifyingAssistance ? "true" : "false")
         << ",\"active_profile\":" << (Cohort().SelectedProfileName.empty() ? "null" : ("\"" + JsonEscape(Cohort().SelectedProfileName) + "\""))
         << ",\"profile_manifest_path\":\"" << JsonEscape(Cohort().ProfileManifestPath) << "\""
         << ",\"loaded_profile_count\":" << Cohort().RuntimeProfiles.size()
         << ",\"population\":" << Cohort().Config.TargetPopulation
         << ",\"map\":" << Cohort().Config.MapId
         << ",\"zone\":" << Cohort().Config.ZoneId
         << ",\"min_level\":" << uint32(Cohort().Config.MinLevel)
         << ",\"max_level\":" << uint32(Cohort().Config.MaxLevel)
         << ",\"allow_combat\":" << (Cohort().Config.AllowCombat ? "true" : "false")
         << ",\"allow_grinding\":" << (Cohort().Config.AllowGrinding ? "true" : "false")
         << ",\"quest_first\":" << (Cohort().Config.QuestFirst ? "true" : "false")
         << ",\"grind_only_when_no_quest_available\":" << (Cohort().Config.GrindOnlyWhenNoQuestAvailable ? "true" : "false")
         << ",\"progression_enabled\":" << (Cohort().Config.EnableProgression ? "true" : "false")
         << ",\"allow_questing\":" << (Cohort().Config.AllowQuesting ? "true" : "false")
         << ",\"allow_dungeons\":" << (Cohort().Config.AllowDungeons ? "true" : "false")
         << ",\"allow_raids\":" << (Cohort().Config.AllowRaids ? "true" : "false")
         << ",\"dungeon_difficulty\":" << uint32(Cohort().Config.DungeonDifficulty)
         << ",\"raid_size\":" << uint32(Cohort().Config.RaidSize)
         << ",\"raid_difficulty\":" << uint32(Cohort().Config.RaidDifficulty)
         << ",\"track_heroic_raid_progression\":" << (Cohort().Config.TrackHeroicRaidProgression ? "true" : "false")
         << ",\"record_decisions\":" << (Cohort().Config.RecordDecisions ? "true" : "false")
         << ",\"record_perception\":" << (Cohort().Config.RecordPerception ? "true" : "false")
         << ",\"smart_sampling\":" << (Cohort().Config.SmartSampling ? "true" : "false")
         << ",\"always_record_failures\":" << (Cohort().Config.AlwaysRecordFailures ? "true" : "false")
         << ",\"always_record_interventions\":" << (Cohort().Config.AlwaysRecordInterventions ? "true" : "false")
         << ",\"always_record_rare_states\":" << (Cohort().Config.AlwaysRecordRareStates ? "true" : "false")
         << ",\"normal_event_sample_rate\":" << Cohort().Config.NormalEventSampleRate
         << ",\"normal_decision_sample_rate\":" << Cohort().Config.NormalDecisionSampleRate
         << ",\"min_clip_importance\":" << Cohort().Config.MinClipImportance
         << ",\"min_replay_importance\":" << Cohort().Config.MinReplayImportance
         << ",\"update_semantic_outcome_stats\":" << (Cohort().Config.UpdateSemanticOutcomeStats ? "true" : "false")
         << ",\"pool_tag_filter\":\"" << JsonEscape(Cohort().Config.PoolTagFilter) << "\""
         << ",\"exact_party_class_specs\":[";
    for (size_t index = 0; index < Cohort().Config.PoolClassSpecFilter.size(); ++index)
    {
        if (index)
            json << ',';
        json << '\"' << JsonEscape(Cohort().Config.PoolClassSpecFilter[index]) << '\"';
    }
    json << "]"
         << ",\"validation_route\":{\"enabled\":" << (Cohort().Config.ValidationRouteEnable ? "true" : "false")
         << ",\"manifest_path\":\"" << JsonEscape(Cohort().Config.ValidationRouteManifestPath) << "\""
         << ",\"advance_mode\":\"" << JsonEscape(Cohort().Config.ValidationRouteAdvanceMode) << "\""
         << ",\"manifest_index\":" << Party().ValidationRouteManifestIndex
         << ",\"manifest_count\":" << Party().ValidationRouteManifest.size()
         << ",\"manifest_load_error\":\"" << JsonEscape(Party().ValidationRouteManifestLoadError) << "\""
         << ",\"scenario_id\":\"" << JsonEscape(Cohort().Config.ValidationRouteScenarioId) << "\""
         << ",\"node_id\":\"" << JsonEscape(Cohort().Config.ValidationRouteNodeId) << "\""
         << ",\"label\":\"" << JsonEscape(Cohort().Config.ValidationRouteLabel) << "\""
         << ",\"kind\":\"" << JsonEscape(Cohort().Config.ValidationRouteKind) << "\""
         << ",\"node_kind\":\"" << JsonEscape(Cohort().Config.ValidationRouteNodeKind) << "\""
         << ",\"mechanic_profile\":\"" << JsonEscape(Cohort().Config.ValidationRouteMechanicProfile) << "\""
         << ",\"boss_recovery_policy\":\""
         << (Cohort().Config.ValidationRouteBossRecovery == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
             ? "native_full_wipe_only" : "native_encounter") << "\""
         << ",\"map\":" << Cohort().Config.ValidationRouteMapId
         << ",\"x\":" << Cohort().Config.ValidationRouteX
         << ",\"y\":" << Cohort().Config.ValidationRouteY
         << ",\"z\":" << Cohort().Config.ValidationRouteZ
         << ",\"o\":" << Cohort().Config.ValidationRouteO
         << ",\"target_entry\":" << Cohort().Config.ValidationRouteTargetEntry
         << ",\"opener_target_entry\":" << Cohort().Config.ValidationRouteOpenerTargetEntry
         << ",\"pack_generation\":" << Party().ValidationRoutePackGeneration
         << ",\"pack_sequence\":" << Party().ValidationRoutePackSequence
         << ",\"completed_pack_count\":" << Party().ValidationRouteCompletedPackCount
         << ",\"observed_dead_script_target\":" << (Party().ValidationRouteObservedDeadScriptTarget ? "true" : "false")
         << ",\"pack_member_count\":" << Party().ValidationRoutePackMemberGuids.size()
         << ",\"pack_engaged_count\":" << Party().ValidationRoutePackEngagedGuids.size()
         << ",\"pack_death_count\":" << Party().ValidationRoutePackDeathGuids.size()
         << ",\"pack_transition_count\":" << Party().ValidationRoutePackTransitionGuids.size()
         << ",\"pack_observed_engagement\":" << (Party().ValidationRoutePackObservedEngagement ? "true" : "false")
         << ",\"alternate_target_entries\":[";
    for (size_t index = 0; index < Cohort().Config.ValidationRouteAlternateTargetEntries.size(); ++index)
    {
        if (index)
            json << ",";
        json << Cohort().Config.ValidationRouteAlternateTargetEntries[index];
    }
    json << "]"
         << ",\"scripted_event_entries\":[";
    for (size_t index = 0; index < Cohort().Config.ValidationRouteScriptedEventEntries.size(); ++index)
    {
        if (index)
            json << ",";
        json << Cohort().Config.ValidationRouteScriptedEventEntries[index];
    }
    json << "]"
         << ",\"scripted_event_transition_aura_ids\":[";
    for (size_t index = 0; index < Cohort().Config.ValidationRouteScriptedEventTransitionAuraIds.size(); ++index)
    {
        if (index)
            json << ",";
        json << Cohort().Config.ValidationRouteScriptedEventTransitionAuraIds[index];
    }
    json << "]"
         << ",\"scripted_event_require_passive\":" << (Cohort().Config.ValidationRouteScriptedEventRequirePassive ? "true" : "false")
         << ",\"add_target_entries\":[";
    for (size_t index = 0; index < Cohort().Config.ValidationRouteAddTargetEntries.size(); ++index)
    {
        if (index)
            json << ",";
        json << Cohort().Config.ValidationRouteAddTargetEntries[index];
    }
    json << "]"
         << ",\"activation_area_trigger_id\":" << Cohort().Config.ValidationRouteActivationAreaTriggerId
         << ",\"activation_data_id\":" << Cohort().Config.ValidationRouteActivationDataId
         << ",\"activation_data_value\":" << Cohort().Config.ValidationRouteActivationDataValue
         << ",\"activation_spawn_group_id\":" << Cohort().Config.ValidationRouteActivationSpawnGroupId
         << ",\"activation_action_entry\":" << Cohort().Config.ValidationRouteActivationActionEntry
         << ",\"activation_action_id\":" << Cohort().Config.ValidationRouteActivationActionId
         << ",\"activation_summon_entry\":" << Cohort().Config.ValidationRouteActivationSummonEntry
         << ",\"activation_summon_x\":" << Cohort().Config.ValidationRouteActivationSummonX
         << ",\"activation_summon_y\":" << Cohort().Config.ValidationRouteActivationSummonY
         << ",\"activation_summon_z\":" << Cohort().Config.ValidationRouteActivationSummonZ
         << ",\"activation_summon_o\":" << Cohort().Config.ValidationRouteActivationSummonO
         << ",\"opener_summon_entry\":" << Cohort().Config.ValidationRouteOpenerSummonEntry
         << ",\"opener_summon_x\":" << Cohort().Config.ValidationRouteOpenerSummonX
         << ",\"opener_summon_y\":" << Cohort().Config.ValidationRouteOpenerSummonY
         << ",\"opener_summon_z\":" << Cohort().Config.ValidationRouteOpenerSummonZ
         << ",\"opener_summon_o\":" << Cohort().Config.ValidationRouteOpenerSummonO << "}"
         << ",\"telemetry_enabled\":" << (telemetry.Enabled ? "true" : "false")
         << ",\"telemetry_frame_interval_ms\":" << telemetry.FrameIntervalMs
         << ",\"telemetry_pre_event_window_sec\":" << telemetry.PreEventWindowSec
         << ",\"telemetry_post_event_window_sec\":" << telemetry.PostEventWindowSec
         << ",\"telemetry_max_frames_per_bot\":" << telemetry.MaxFramesPerBot
         << ",\"telemetry_max_open_clips_per_bot\":" << telemetry.MaxOpenClipsPerBot
         << ",\"spawn_mode\":\"" << JsonEscape(Cohort().Config.SpawnMode) << "\""
         << ",\"allow_configured_center_fallback\":" << (Cohort().Config.AllowConfiguredCenterFallback ? "true" : "false")
         << ",\"use_saved_position\":" << (Cohort().Config.UseSavedPosition ? "true" : "false")
         << ",\"near_player_radius\":" << Cohort().Config.NearPlayerRadius
         << ",\"death_recovery_mode\":\"" << JsonEscape(Cohort().Config.DeathRecoveryMode) << "\""
         << ",\"teleport_to_center_on_death\":" << (Cohort().Config.TeleportToCenterOnDeath ? "true" : "false")
         << ",\"max_deaths_before_fallback\":" << Cohort().Config.MaxDeathsBeforeFallback
         << ",\"safe_position_memory_sec\":" << Cohort().Config.SafePositionMemorySec
         << ",\"auto_start_recording\":" << (Cohort().Config.AutoStartRecording ? "true" : "false")
         << ",\"auto_recording_window_minutes\":" << Cohort().Config.AutoRecordingWindowMinutes
         << ",\"auto_recording_name_prefix\":\"" << JsonEscape(Cohort().Config.AutoRecordingNamePrefix) << "\""
         << ",\"bot_learning\":{\"enable\":" << (Cohort().LearningConfig.Enabled ? "true" : "false")
         << ",\"min_samples_for_strong_bias\":" << Cohort().LearningConfig.MinSamplesForStrongBias
         << ",\"danger_penalty_weight\":" << Cohort().LearningConfig.DangerPenaltyWeight
         << ",\"progression_reward_weight\":" << Cohort().LearningConfig.ProgressionRewardWeight
         << ",\"recent_failure_penalty_weight\":" << Cohort().LearningConfig.RecentFailurePenaltyWeight
         << ",\"exploration_novelty_weight\":" << Cohort().LearningConfig.ExplorationNoveltyWeight
         << ",\"allow_global_memory_fallback\":" << (Cohort().LearningConfig.AllowGlobalMemoryFallback ? "true" : "false") << "}"
         << ",\"bot_policy_model\":{\"enable\":" << (Cohort().PolicyModelConfig.Enabled ? "true" : "false")
         << ",\"mode\":\"" << JsonEscape(Cohort().PolicyModelConfig.Mode) << "\""
         << ",\"version\":\"" << JsonEscape(Cohort().PolicyModelConfig.Version) << "\""
         << ",\"score_weight\":" << Cohort().PolicyModelConfig.ScoreWeight
         << ",\"fail_closed\":" << (Cohort().PolicyModelConfig.FailClosed ? "true" : "false")
         << ",\"max_decision_latency_ms\":" << Cohort().PolicyModelConfig.MaxDecisionLatencyMs
         << ",\"min_eval_rows\":" << Cohort().PolicyModelConfig.MinEvalRows
         << ",\"max_death_rate\":" << Cohort().PolicyModelConfig.MaxDeathRate
         << ",\"max_stuck_rate\":" << Cohort().PolicyModelConfig.MaxStuckRate
         << ",\"max_failure_rate\":" << Cohort().PolicyModelConfig.MaxFailureRate
         << ",\"assist_allowed\":" << (Cohort().PolicyModelConfig.AssistAllowed ? "true" : "false")
         << ",\"deployment_reason\":\"" << JsonEscape(Cohort().PolicyModelConfig.DeploymentReason) << "\""
         << ",\"artifact_loaded\":" << (Cohort().PolicyModelConfig.ArtifactLoaded ? "true" : "false")
         << ",\"artifact_path\":\"" << JsonEscape(Cohort().PolicyModelConfig.ArtifactPath) << "\""
         << ",\"model_type\":\"" << JsonEscape(Cohort().PolicyModelConfig.ModelType) << "\""
         << ",\"feature_schema_version\":\"" << JsonEscape(Cohort().PolicyModelConfig.FeatureSchemaVersion) << "\"}"
         << ",\"brain_version\":\"" << JsonEscape(Cohort().Config.BrainVersion) << "\"}";
    return json.str();
}
