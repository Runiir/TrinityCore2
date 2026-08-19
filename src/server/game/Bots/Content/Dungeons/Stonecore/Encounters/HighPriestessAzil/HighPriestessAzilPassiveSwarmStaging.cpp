#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilPassiveSwarmStaging.h"

#include "Bots/BotActionExecutor.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Object.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <vector>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
using BotWorldPopulationMgrSpellSemantics::NowMs;

bool Context::Run(PassiveSwarmStagingRequest const& request)
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
    std::string& situation = *request.Situation;
    std::string& action = *request.Action;
    Unit*& target = *request.Target;
    uint32 engagedAddCount = discovery.EngagedAddCount;
    uint32 addCount = discovery.AddCount;
    std::vector<Creature*> const& localAdds = discovery.LocalAdds;
    std::function<bool(Player*, Unit*)> const& isUsableListedAdd =
        discovery.IsUsableListedAdd;
    bool cohortSwarmActive = discovery.CohortSwarmActive;
    bool sharedLargePassiveSwarmStaging =
        density.SharedLargePassiveSwarmStaging;
    bool densityTankOwnsSecureMajority =
        density.DensityTankOwnsSecureMajority;
    std::string const& role = density.Role;
    BotClassSpecActionProfile const& profile = density.Profile;
    Player* densityTank = density.DensityTank;
    Player* densityDefenseTarget = density.DensityDefenseTarget;
    static constexpr float PassiveTankDensityClusterRadius = 10.0f;

    // Preserve the next native area-threat cast once the current swarm has
    // secure tank ownership. Also hold while a listed wave is visible but has
    // not activated at swarm density yet. Azil can leave one precursor engaged
    // shortly before activating a full follower wave; spending Death and Decay
    // on that precursor leaves only self-centered threat while the tank crosses
    // the platform. Auto-attacks remain active while this hold is in effect,
    // and any party target or three engaged adds resumes the strict area path.
    bool pendingSwarmActivation = cohortSwarmActive && engagedAddCount < 3;
    // Rerun91 showed that a non-Feral tank can hold indefinitely outside a
    // passive follower cluster while DPS waits for ownership. Select the
    // deterministic ten-yard medoid of the visible listed followers instead,
    // so each tank reaches its existing native area-threat pickup radius on
    // the first active decision. A rejected bounded path falls through to
    // the unchanged resource hold below.
    Creature* passiveSwarmClusterAnchor = nullptr;
    uint32 pendingSwarmPickupCoverage = 0;
    float pendingSwarmPickupDistance = std::numeric_limits<float>::max();
    uint32 pendingSwarmPickupGuid = std::numeric_limits<uint32>::max();
    if (pendingSwarmActivation)
        for (Creature* candidate : localAdds)
        {
            if (!candidate)
                continue;
            uint32 coverage = 0;
            for (Creature* neighbor : localAdds)
                if (neighbor && candidate->GetExactDist2d(neighbor)
                    <= PassiveTankDensityClusterRadius)
                    ++coverage;
            float distance = bot->GetExactDist(candidate);
            uint32 guid = candidate->GetGUID().GetCounter();
            if (!passiveSwarmClusterAnchor
                || coverage > pendingSwarmPickupCoverage
                || (coverage == pendingSwarmPickupCoverage
                    && (distance < pendingSwarmPickupDistance
                        || (distance == pendingSwarmPickupDistance
                            && guid < pendingSwarmPickupGuid))))
            {
                passiveSwarmClusterAnchor = candidate;
                pendingSwarmPickupCoverage = coverage;
                pendingSwarmPickupDistance = distance;
                pendingSwarmPickupGuid = guid;
            }
        }
    // Rerun174 reached this passive 60-follower wave immediately after a
    // generation-13 tank resurrection. The tank completed its existing
    // medoid preposition alone while the damage roles still alternated
    // between remote add paths and tactical-path rejection. Its native
    // white swing therefore activated all 60 before the party could burn
    // them: one heal flipped 59 followers, Feral recovered ownership, then
    // died after 31 secure-threat holds with only one add dead. Stage only
    // a proven very-large passive wave around the living tank before that
    // unchanged native activation. Smaller waves and every active-wave,
    // threat, spell-legality, hazard, and boss rule remain unchanged.
    // Rerun176 proved the original staging decision was observer-local.
    // The tank and healer saw the passive 60-follower cluster and held for
    // the party, while every damage role remained outside that local view
    // and alternated route/add movement for 192 tank decisions. Reconstruct
    // the same declared-wave cardinality from the living tank's view so all
    // party members agree on the staging gate. This changes neither the
    // listed-add contract nor activation: only the tank still selects the
    // medoid and submits the native white swing after all members arrive.
    uint32 tankVisiblePassiveSwarmAddCount = 0;
    uint32 tankVisiblePassiveSwarmEngagedCount = 0;
    if (densityTank)
    {
        std::vector<WorldObject*> tankVisibleObjects;
        Trinity::AllWorldObjectsInRange tankVisibleCheck(
            densityTank, 45.0f);
        Trinity::WorldObjectListSearcher<
            Trinity::AllWorldObjectsInRange> tankVisibleSearcher(
                densityTank, tankVisibleObjects, tankVisibleCheck);
        Cell::VisitAllObjects(
            densityTank, tankVisibleSearcher, 45.0f);
        for (WorldObject* object : tankVisibleObjects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!isUsableListedAdd(densityTank, creature)
                || !densityTank->IsWithinLOSInMap(creature))
                continue;
            ++tankVisiblePassiveSwarmAddCount;
            if (creature->GetVictim())
                ++tankVisiblePassiveSwarmEngagedCount;
        }
    }
    bool tankViewProvesLargePassiveSwarm = cohortSwarmActive && densityTank
        && tankVisiblePassiveSwarmEngagedCount == 0
        && tankVisiblePassiveSwarmAddCount >= 24;
    // Rerun178 proved that recomputing the tank-visible staging fact in
    // every bot's handler was still observer-dependent. The tank held the
    // passive 60-follower wave for 192 decisions, while all three damage
    // roles remained 69-87 yards from the route anchor and alternated
    // remote add/route paths behind the rerun170 pre-anchor bypass. Publish
    // only the living tank's proven passive-wave observation as a
    // generation-scoped party fact. The bypass remains unchanged until
    // that proof exists, and native activation remains tank-only below.
    if (role == "tank" && tankViewProvesLargePassiveSwarm)
    {
        manager.Party().ValidationRouteLargePassiveSwarmStaging = true;
        manager.Party().ValidationRouteLargePassiveSwarmStagingGeneration =
            manager.Party().ValidationRouteGeneration;
    }
    else if (!densityTank && sharedLargePassiveSwarmStaging)
    {
        manager.Party().ValidationRouteLargePassiveSwarmStaging = false;
        manager.Party().ValidationRouteLargePassiveSwarmStagingGeneration = 0;
    }
    sharedLargePassiveSwarmStaging =
        manager.Party().ValidationRouteLargePassiveSwarmStaging
        && manager.Party().ValidationRouteLargePassiveSwarmStagingGeneration
            == manager.Party().ValidationRouteGeneration;
    // Rerun182 proved the generation-scoped tank observation was not yet
    // fully authoritative. Remote damage roles still required their own
    // local cohortSwarmActive view, so they alternated staging with passive
    // add or route movement as that view changed. Once the living tank has
    // published the existing 24-plus proof, use that shared fact as the
    // cardinality authority for every member. The proof is still created
    // only from the tank's unchanged unengaged 45-yard observation and is
    // reset with the route generation below.
    bool largePassiveSwarm = densityTank
        && sharedLargePassiveSwarmStaging;
    Unit* largePassiveSwarmEvidenceTarget = passiveSwarmClusterAnchor
        ? static_cast<Unit*>(passiveSwarmClusterAnchor)
        : static_cast<Unit*>(densityTank);
    bool largePassiveSwarmPartyStaged = !largePassiveSwarm;
    uint32 largePassiveSwarmLoadedParticipants = 0;
    uint32 largePassiveSwarmStagedParticipants = 0;
    if (largePassiveSwarm)
    {
        for (BotWorldPopulationMgrBotState::WorldBotState const& cohortState
            : manager.Party().Bots)
        {
            Player* member = manager.GetLoadedBot(cohortState);
            if (!member)
                continue;
            if (!member->IsAlive() || member->GetMap() != bot->GetMap()
                || member->GetGroup() != bot->GetGroup()
                || !manager.IsValidationCohortMemberInOriginalInstance(
                    cohortState, member))
                continue;
            ++largePassiveSwarmLoadedParticipants;
            if (member->GetExactDist2d(densityTank) <= 18.0f)
                ++largePassiveSwarmStagedParticipants;
        }
        largePassiveSwarmPartyStaged =
            largePassiveSwarmLoadedParticipants > 0
            && largePassiveSwarmStagedParticipants
                == largePassiveSwarmLoadedParticipants
                && (!manager.Cohort().Config.TargetPopulation
                    || largePassiveSwarmLoadedParticipants
                        >= manager.Cohort().Config.TargetPopulation);
    }
    if (largePassiveSwarm && role != "tank"
        && !largePassiveSwarmPartyStaged)
    {
        bool alreadyStaged = bot->IsAlive()
            && bot->GetExactDist2d(densityTank) <= 18.0f;
        bool moved = false;
        if (!alreadyStaged && !bot->HasUnitState(UNIT_STATE_CASTING)
            && !bot->IsFalling())
        {
            bool meleeProfile = profile.MovementDirective == "melee"
                || (profile.MaxRange > 0.0f && profile.MaxRange <= 5.0f);
            float stagingRadius = role == "healer"
                ? 4.0f : (meleeProfile ? 6.0f : 12.0f);
            float stagingOffset =
                (bot->GetGUID().GetCounter() % 5) * 0.30f;
            Unit* stagingReference = passiveSwarmClusterAnchor
                ? static_cast<Unit*>(passiveSwarmClusterAnchor)
                : static_cast<Unit*>(bot);
            float stagingAngle = stagingReference->GetAngle(densityTank)
                - densityTank->GetOrientation() + stagingOffset;
            // Rerun182's remote Hunter terminalized after both fixed
            // staging points rejected, while Retribution repeatedly reset
            // an accepted point path and alternated back to passive adds.
            // Maintain one native follow generator at the same role-specific
            // radius instead. This neither teleports nor forces placement;
            // the ordinary movement generator remains responsible for
            // terrain traversal and the unchanged 18-yard check remains the
            // only staging authority.
            bool followingStagingTank =
                bot->GetMotionMaster()->GetCurrentMovementGeneratorType()
                    == FOLLOW_MOTION_TYPE
                && state.ActivePathValid
                && std::fabs(state.ActivePathToX
                    - densityTank->GetPositionX()) <= 0.1f
                && std::fabs(state.ActivePathToY
                    - densityTank->GetPositionY()) <= 0.1f
                && std::fabs(state.ActivePathToZ
                    - densityTank->GetPositionZ()) <= 0.1f;
            if (!followingStagingTank)
            {
                state.ActivePathFromX = bot->GetPositionX();
                state.ActivePathFromY = bot->GetPositionY();
                state.ActivePathFromZ = bot->GetPositionZ();
                state.ActivePathToX = densityTank->GetPositionX();
                state.ActivePathToY = densityTank->GetPositionY();
                state.ActivePathToZ = densityTank->GetPositionZ();
                state.ActivePathValid = true;
                state.LastPathRejectReason.clear();
                state.LastPathChangeMs = NowMs();
                bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                bot->GetMotionMaster()->MoveFollow(
                    densityTank, stagingRadius, stagingAngle);
            }
            moved = true;
        }
        else if (alreadyStaged && bot->isMoving())
            bot->StopMoving();

        std::string raw = manager.BuildRawJson(
            bot, largePassiveSwarmEvidenceTarget);
        std::string semantic = manager.BuildSemanticJson(
            bot, largePassiveSwarmEvidenceTarget, "dungeon_boss",
            &power, stage, activity);
        char const* stagingAction = moved
            ? "stage_for_large_passive_swarm_activation"
            : "hold_for_large_passive_swarm_activation";
        manager.RecordEvent(state, bot, "boss_add_density",
            largePassiveSwarmEvidenceTarget, stagingAction,
            raw.c_str(), semantic.c_str(),
            bot->GetExactDist2d(densityTank),
            largePassiveSwarmStagedParticipants);
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);
        state.TargetGuid = largePassiveSwarmEvidenceTarget->GetGUID();
        target = largePassiveSwarmEvidenceTarget;
        situation = "dungeon_boss";
        action = stagingAction;
        return true;
    }
    if (role == "tank" && pendingSwarmActivation && passiveSwarmClusterAnchor
        && !bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)
        && (bot->GetExactDist2d(passiveSwarmClusterAnchor) > 6.0f
            || bot->IsWithinLOSInMap(passiveSwarmClusterAnchor))
        && !bot->HasUnitState(UNIT_STATE_CASTING) && !bot->IsFalling())
    {
        bool moved = manager.MoveBotToPoint(state, bot,
            passiveSwarmClusterAnchor->GetPositionX(),
            passiveSwarmClusterAnchor->GetPositionY(),
            passiveSwarmClusterAnchor->GetPositionZ());
        if (moved)
        {
            state.TankPendingSwarmPickupAnchorGuid =
                passiveSwarmClusterAnchor->GetGUID();
            state.TankPendingSwarmPickupUntilMs = NowMs() + 4000;
            state.TankPendingSwarmPickupEngagedHandoff = false;
            std::string raw = manager.BuildRawJson(bot, passiveSwarmClusterAnchor);
            std::string semantic = manager.BuildSemanticJson(
                bot, passiveSwarmClusterAnchor, "dungeon_boss",
                &power, stage, activity);
            manager.RecordEvent(state, bot, "boss_add_density",
                passiveSwarmClusterAnchor,
                "tank_preposition_for_pending_swarm_pickup",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(passiveSwarmClusterAnchor),
                pendingSwarmPickupCoverage);
            state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
            target = add;
            situation = "dungeon_boss";
            action = "tank_preposition_for_pending_swarm_pickup";
            return true;
        }
    }
    // Rerun184 activated all 59 staged followers onto the Feral, but the
    // first post-activation density decision still had to enter Bear Form.
    // That spent the opening native GCD, so the healer's first shield
    // overtook the zero-margin white-swing threat before Swipe or Thrash
    // could run. Prepare the unchanged persistent form while the passive
    // wave and party are already staged, then wait only for that form's
    // native GCD before allowing the existing tank-only activation.
    bool feralPassiveSwarmBearFormMissing = role == "tank"
        && profile.SpecTag == "feral_druid_tank"
        && largePassiveSwarm && passiveSwarmClusterAnchor
        && !bot->HasAura(5487);
    if (feralPassiveSwarmBearFormMissing)
        manager.TryEnsurePersistentCombatSetup(
            state, bot, passiveSwarmClusterAnchor);
    SpellInfo const* passiveSwarmBearFormInfo =
        sSpellMgr->GetSpellInfo(5487);
    bool feralPassiveSwarmBearFormGcdPending = role == "tank"
        && profile.SpecTag == "feral_druid_tank"
        && largePassiveSwarm && passiveSwarmClusterAnchor
        && passiveSwarmBearFormInfo
        && bot->GetSpellHistory()->HasGlobalCooldown(
            passiveSwarmBearFormInfo);
    if (feralPassiveSwarmBearFormMissing
        || feralPassiveSwarmBearFormGcdPending)
    {
        char const* preparationAction =
            feralPassiveSwarmBearFormMissing
                ? "feral_prepare_bear_form_before_passive_swarm_activation"
                : "feral_hold_bear_form_gcd_before_passive_swarm_activation";
        std::string raw = manager.BuildRawJson(
            bot, passiveSwarmClusterAnchor);
        std::string semantic = manager.BuildSemanticJson(
            bot, passiveSwarmClusterAnchor, "dungeon_boss",
            &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_add_density",
            passiveSwarmClusterAnchor, preparationAction,
            raw.c_str(), semantic.c_str(),
            bot->GetExactDist2d(passiveSwarmClusterAnchor),
            largePassiveSwarmStagedParticipants, 5487);
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);
        state.TargetGuid = passiveSwarmClusterAnchor->GetGUID();
        target = passiveSwarmClusterAnchor;
        situation = "dungeon_boss";
        action = preparationAction;
        return true;
    }
    if (role == "tank" && largePassiveSwarm
        && !largePassiveSwarmPartyStaged
        && bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)
        && bot->IsWithinLOSInMap(passiveSwarmClusterAnchor))
    {
        if (bot->isMoving())
            bot->StopMoving();
        std::string raw = manager.BuildRawJson(
            bot, passiveSwarmClusterAnchor);
        std::string semantic = manager.BuildSemanticJson(
            bot, passiveSwarmClusterAnchor, "dungeon_boss",
            &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_add_density",
            passiveSwarmClusterAnchor,
            "hold_large_passive_swarm_for_party_staging",
            raw.c_str(), semantic.c_str(),
            float(largePassiveSwarmStagedParticipants),
            largePassiveSwarmLoadedParticipants);
        state.DecisionTimer = std::min<uint32>(
            state.DecisionTimer, 250);
        state.TargetGuid = passiveSwarmClusterAnchor->GetGUID();
        target = passiveSwarmClusterAnchor;
        situation = "dungeon_boss";
        action = "hold_large_passive_swarm_for_party_staging";
        return true;
    }
    // A fully passive Azil follower set can remain visible after the tank
    // reaches its reserved pickup anchor. Visibility keeps the swarm gate
    // active, but with no engaged follower the tank resource hold and DPS
    // ownership wait otherwise have no actor capable of starting the wave.
    // Initiate only the tank's native white swing; the existing area spell
    // remains reserved for the activated wave and every DPS threat gate is
    // unchanged.
    if (role == "tank" && pendingSwarmActivation
        && engagedAddCount == 0 && passiveSwarmClusterAnchor
        && largePassiveSwarmPartyStaged
        && bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)
        && bot->IsWithinLOSInMap(passiveSwarmClusterAnchor))
    {
        manager.SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::StartOrSwitch,
            passiveSwarmClusterAnchor->GetGUID(),
            BotMeleeAutoAttack::Owner::Threat,
            BotActionArbitration::Priority::ThreatControl,
            "tank_activate_passive_swarm");
        BotActionResult activationResult =
            bot->GetVictim() == passiveSwarmClusterAnchor
            ? BotActionResult::Ok : BotActionResult::NoAction;
        if (activationResult == BotActionResult::Ok)
        {
                std::string raw = manager.BuildRawJson(bot, passiveSwarmClusterAnchor);
                std::string semantic = manager.BuildSemanticJson(
                bot, passiveSwarmClusterAnchor, "dungeon_boss",
                &power, stage, activity);
                manager.RecordEvent(state, bot, "boss_add_density",
                passiveSwarmClusterAnchor,
                "tank_activate_passive_swarm",
                raw.c_str(), semantic.c_str(),
                bot->GetExactDist2d(passiveSwarmClusterAnchor),
                pendingSwarmPickupCoverage);
            state.TargetGuid = passiveSwarmClusterAnchor->GetGUID();
            state.WasInCombat = true;
            target = passiveSwarmClusterAnchor;
            situation = "dungeon_boss";
            action = "tank_activate_passive_swarm";
            return true;
        }
    }
    // Rerun153 reached the passive anchor but had no line of sight. The
    // native Attack request returned Ok without establishing a victim,
    // then this resource hold suppressed the existing boss/route fallback
    // for 71 consecutive decisions. A non-visible anchor is not actionable
    // activation evidence; fall through without spending the reserved area
    // spell so ordinary route control can reacquire a reachable target.
    // Rerun158 proved that the six-yard approximation can still be outside
    // the engine's actual melee envelope: ExecuteCombat returned Ok for 150
    // white-swing submissions without combat, a victim, or melee-auto
    // uptime. Only an anchor in native melee range and line of sight may
    // suppress the existing route fallback after bounded prepositioning.
    bool passiveSwarmActivationNotActionable = pendingSwarmActivation
        && passiveSwarmClusterAnchor
        && (!bot->IsWithinMeleeRange(passiveSwarmClusterAnchor)
            || !bot->IsWithinLOSInMap(passiveSwarmClusterAnchor));
    if (role == "tank" && cohortSwarmActive && !densityDefenseTarget
        && (densityTankOwnsSecureMajority
            || (pendingSwarmActivation
                && !passiveSwarmActivationNotActionable)))
    {
        char const* holdAction = pendingSwarmActivation
            ? "hold_pending_swarm_area_threat_resources"
            : "hold_secure_area_threat_resources";
        std::string raw = manager.BuildRawJson(bot, add);
        std::string semantic = manager.BuildSemanticJson(
            bot, add, "dungeon_boss", &power, stage, activity);
        manager.RecordEvent(state, bot, "boss_add_density", add,
            holdAction, raw.c_str(), semantic.c_str(),
            float(engagedAddCount), addCount);
        state.TargetGuid = add ? add->GetGUID() : ObjectGuid::Empty;
        target = add;
        situation = "dungeon_boss";
        action = holdAction;
        return true;
    }

    return false;
}

bool TryPassiveSwarmStaging(
    PassiveSwarmStagingRequest const& request)
{
    return Context::Run(request);
}
}
