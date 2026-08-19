#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilDensityCombatResolution.h"

#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <string>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
bool Context::Run(DensityCombatResolutionRequest const& request)
{
    BotWorldPopulationMgr& manager = *request.Manager;
    BotWorldPopulationMgrBotState::WorldBotState& state = *request.State;
    Player* bot = request.Bot;
    BotRolePowerBreakdown const& power = *request.Power;
    BotProgressionStage stage = request.Stage;
    BotProgressionActivity activity = request.Activity;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    AddWaveDensityResult const& density = *request.Density;
    Unit* add = request.Add;
    bool sharedFocusValid = request.SharedFocusValid;
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    uint32 addCount = discovery.AddCount;
    bool highDensityPhase = density.HighDensityPhase;
    bool cohortSwarmActive = discovery.CohortSwarmActive;
    std::string const& role = density.Role;
    BotClassSpecActionProfile const& profile = density.Profile;
    bool dpsSwarmDamageRelease = density.DpsSwarmDamageRelease;
    bool hunterMisdirectionActive = request.HunterMisdirectionActive;
    Creature* densityApproachAnchor = density.DensityApproachAnchor;
    std::function<bool(Unit*)> const& continueStableTankSwarmApproach =
        request.ContinueStableTankSwarmApproach;
    std::function<float(Player*, Unit const*, uint32)> const& routeEngageRange =
        request.RouteEngageRange;

    if (highDensityPhase && !add && densityApproachAnchor)
    {
        ResolvedCombatAction approachAction;
        approachAction.MovementDirective = profile.MovementDirective;
        approachAction.AutoAttackMode = profile.AutoAttackMode;
        approachAction.MinRange = profile.MinRange;
        approachAction.MaxRange = profile.MaxRange;
        bool moved = manager.MoveBotToProfileRange(state, bot, densityApproachAnchor, &approachAction);
        std::string raw = manager.BuildRawJson(bot, densityApproachAnchor);
        std::string semantic = manager.BuildSemanticJson(bot, densityApproachAnchor, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_add_density", densityApproachAnchor, "approach_density_anchor", raw.c_str(), semantic.c_str(),
            bot->GetExactDist(densityApproachAnchor), addCount);
        state.TargetGuid = densityApproachAnchor->GetGUID();
        target = densityApproachAnchor;
        situation = "dungeon_boss";
        action = moved ? "move_to_density_anchor_range" : "hold_density_anchor_range";
        return true;
    }
    if (!add)
    {
        if (!highDensityPhase)
            return false;

        std::string raw = manager.BuildRawJson(bot, nullptr);
        std::string semantic = manager.BuildSemanticJson(bot, nullptr, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_add_density", nullptr, "no_compatible_density_anchor", raw.c_str(), semantic.c_str(), float(addCount));
        state.TargetGuid.Clear();
        target = nullptr;
        situation = "dungeon_boss";
        action = "hold_boss_add_density";
        return true;
    }
    if (!highDensityPhase && !sharedFocusValid)
    {
        manager.Party().ValidationRouteAddFocusGuid = add->GetGUID();
        manager.Party().ValidationRouteAddFocusGeneration = manager.Party().ValidationRouteGeneration;
    }
    if (!bot->IsValidAttackTarget(add))
    {
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_adds", add, "hold_unattackable_focus", raw.c_str(), semantic.c_str(), float(addCount));
        state.TargetGuid = add->GetGUID();
        target = add;
        situation = "dungeon_boss";
        action = "hold_boss_add_focus";
        return true;
    }

    // The boss can remain attackable while a complete add wave activates.
    // Tanks must enter their area-threat profile immediately in that case;
    // otherwise they alternate single-target taunts while healing threat
    // assigns most of an Azil follower wave to the healer.  DPS still wait
    // for secure ownership before using their own area profiles.
    bool tankSwarmAreaPhase = role == "tank" && cohortSwarmActive;
    bool secureSwarmAreaPhase = role == "dps" && cohortSwarmActive
        && (dpsSwarmDamageRelease || hunterMisdirectionActive);
    bool densityAreaPhase = highDensityPhase || tankSwarmAreaPhase || secureSwarmAreaPhase;
    ResolvedCombatAction profileAction = manager.ResolveProfileCombatAction(bot, add,
        densityAreaPhase ? addCount : 0, densityAreaPhase);
    // A tank with an active scripted swarm must not spend native area
    // resources through the ordinary single-target fallback. In particular,
    // Heart Strike can consume the Blood rune needed by the next Blood Boil
    // after the strict area resolver reports only cooldown/resource gates.
    // The invalid-area branch below preserves auto-attack uptime without
    // consuming that resource, while non-swarm and non-tank fallbacks retain
    // their existing behavior.
    bool preserveTankSwarmAreaResources = role == "tank" && cohortSwarmActive;
    bool densitySingleTargetFallback = densityAreaPhase && !profileAction.Valid
        && !preserveTankSwarmAreaResources;
    if (densitySingleTargetFallback)
        profileAction = manager.ResolveProfileCombatAction(bot, add);
    if (densityAreaPhase && !profileAction.Valid)
    {
        if (role == "tank")
        {
            BotActionResult pull = manager.SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::StartOrSwitch,
                add->GetGUID(), BotMeleeAutoAttack::Owner::Threat,
                BotActionArbitration::Priority::ThreatControl,
                "tank_density_autoattack_fallback")
                    ? BotActionResult::Ok : BotActionResult::NoAction;
            if (pull == BotActionResult::Ok)
            {
                std::string raw = manager.BuildRawJson(bot, add);
                std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
                manager.RecordEvent(state, bot, "boss_add_density", add, "tank_auto_attack_density_fallback",
                    raw.c_str(), semantic.c_str(), float(addCount));
                state.TargetGuid = add->GetGUID();
                state.WasInCombat = true;
                target = add;
                situation = "dungeon_boss";
                action = "tank_auto_attack_density_fallback";
                return true;
            }
        }
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_add_density", add, "no_legal_density_action", raw.c_str(), semantic.c_str(), float(addCount));
        state.TargetGuid = add->GetGUID();
        target = add;
        situation = "dungeon_boss";
        action = "hold_boss_add_density";
        return true;
    }
    bool densityGenerator = densityAreaPhase && profileAction.DebugName == "resource_generator";
    if (densityAreaPhase)
    {
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
        char const* densityActionReason = densitySingleTargetFallback
            ? "single_target_fallback_selected"
            : (densityGenerator ? "resource_generator_selected" : "area_action_selected");
        manager.RecordEvent(state, bot, "boss_add_density", add, densityActionReason, raw.c_str(), semantic.c_str(), float(addCount), 0, profileAction.SpellId);
    }
    uint32 spellId = profileAction.SpellId;
    float engageRange = profileAction.MaxRange > 0.0f ? profileAction.MaxRange : routeEngageRange(bot, add, spellId);
    bool approach = bot->GetExactDist(add) > std::max(5.0f, engageRange - 1.0f) || !bot->IsWithinLOSInMap(add);
    bool continuingStableApproach = approach && continueStableTankSwarmApproach(add);
    BotActionResult result = BotActionResult::NoAction;
    if (approach && !continuingStableApproach)
        manager.MoveBotToProfileRange(state, bot, add, &profileAction);
    else if (!approach)
    {
        if (densityAreaPhase)
            result = manager.ExecuteProfileCombatAction(&state, bot, add, &profileAction, addCount, true);
        else
        {
            BotActionResult pull = profileAction.AutoAttackMode == "melee"
                && manager.SubmitMeleeAutoAttackIntent(state,
                    BotMeleeAutoAttack::Kind::StartOrSwitch,
                    add->GetGUID(), BotMeleeAutoAttack::Owner::Profile,
                    BotActionArbitration::Priority::TrainedDamage,
                    "boss_add_melee_engagement")
                        ? BotActionResult::Ok : BotActionResult::NoAction;
            result = manager.ExecuteProfileCombatAction(&state, bot, add, &profileAction);
            if (result == BotActionResult::NoAction)
                result = pull;
        }
    }

    std::string raw = manager.BuildRawJson(bot, add);
    std::string semantic = manager.BuildSemanticJson(bot, add, "dungeon_boss", &power, stage, activity);
    manager.RecordEvent(state, bot, "boss_adds", add,
        continuingStableApproach ? "continue_stable_swarm_approach"
            : (approach ? "approach_target" : ToString(result)),
        raw.c_str(), semantic.c_str(), float(addCount), 0,
        result == BotActionResult::Ok ? spellId : 0);
    state.TargetGuid = add->GetGUID();
    state.WasInCombat = true;
    target = add;
    situation = "dungeon_boss";
    action = continuingStableApproach ? "continue_stable_tank_swarm_approach"
        : (approach ? "move_to_boss_add"
            : (densitySingleTargetFallback ? "focused_attack_boss_add_density"
                : (densityGenerator ? "generate_resource_boss_add_density"
                    : (densityAreaPhase ? "area_attack_boss_add_density" : "switch_to_boss_add"))));
    return true;
}

bool TryDensityCombatResolution(
    DensityCombatResolutionRequest const& request)
{
    return Context::Run(request);
}
}
