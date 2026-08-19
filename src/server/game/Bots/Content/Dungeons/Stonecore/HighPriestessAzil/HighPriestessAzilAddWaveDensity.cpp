#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"

#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <limits>
#include <utility>

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
AddWaveDensityResult Context::Run(
    AddWaveDensityRequest const& request)
{
    AddWaveDensityResult result;
    BotWorldPopulationMgr& manager = *request.Manager;
    Player* bot = request.Bot;
    AddWaveDiscoveryResult const& discovery = *request.Discovery;
    std::vector<Creature*> const& localAdds = discovery.LocalAdds;
    Unit* add = discovery.Add;
    bool sharedFocusValid = discovery.SharedFocusValid;
    uint32 addCount = discovery.AddCount;
    uint32 engagedAddCount = discovery.EngagedAddCount;
    bool cohortSwarmActive = discovery.CohortSwarmActive;

    // Rerun170 reached Azil's route generation roughly 80-115 yards from
    // the navigation anchor. Passive followers were already visible there,
    // so the add handler repeatedly diverted the tank among followers at
    // y=1062-1100 while the boss anchor remained at y=985. No boss focus or
    // activation was ever established. A passive, unengaged declared wave
    // before arrival is not encounter evidence; let the unchanged route
    // movement reach the boss anchor first. Any engaged follower or observed
    // boss preserves the existing immediate party-protection path.
    bool sharedLargePassiveSwarmStaging =
        manager.Party().ValidationRouteLargePassiveSwarmStaging
        && manager.Party().ValidationRouteLargePassiveSwarmStagingGeneration
            == manager.Party().ValidationRouteGeneration;
    result.SharedLargePassiveSwarmStaging = sharedLargePassiveSwarmStaging;
    // Rerun196 proved the same pre-arrival diversion survives when an
    // observer sees only one or two passive followers: cohortSwarmActive is
    // false, so the original guard does not run and the selected add keeps
    // replacing route movement.  Local addCount is the exact cardinality
    // authority for this passive-only bypass.  Any engaged local follower,
    // observed boss, route arrival, or shared large-wave staging proof
    // preserves the existing immediate add-defense behavior.
    if (addCount > 0 && engagedAddCount == 0
        && manager.Party().ValidationRouteBossProgressTargetGuid.IsEmpty()
        && request.CanonicalRouteDistance > request.RouteArrivalRadius
        && !sharedLargePassiveSwarmStaging)
    {
        result.BypassPreArrival = true;
        return result;
    }
    if (manager.Party().ValidationRouteBossAddDensityPhase
        && (manager.Party().ValidationRouteBossAddDensityGeneration
                != manager.Party().ValidationRouteGeneration
            || !cohortSwarmActive))
    {
        manager.ResetValidationRouteBossAddDensityState();
    }

    bool observedBossEngagement = manager.Cohort().Config.ValidationRouteKind == "boss"
        && !manager.Party().ValidationRouteBossProgressTargetGuid.IsEmpty();
    Unit* routeBoss = observedBossEngagement
        ? ObjectAccessor::GetUnit(*bot,
            manager.Party().ValidationRouteBossProgressTargetGuid)
        : nullptr;
    bool routeBossAttackable = routeBoss
        && routeBoss->IsAlive()
        && bot->IsValidAttackTarget(routeBoss);
    if (manager.Party().ValidationRouteBossAddDensityPhase && routeBossAttackable)
    {
        manager.ResetValidationRouteBossAddDensityState();
    }
    bool routeBossUnavailable = !routeBoss
        || (routeBoss->IsAlive() && !bot->IsValidAttackTarget(routeBoss));
    if (!manager.Party().ValidationRouteBossAddDensityPhase
        && addCount >= 3
        && observedBossEngagement
        && routeBossUnavailable)
    {
        manager.Party().ValidationRouteBossAddDensityPhase = true;
        manager.Party().ValidationRouteBossAddDensityGeneration =
            manager.Party().ValidationRouteGeneration;
    }

    bool highDensityPhase = manager.Party().ValidationRouteBossAddDensityPhase
        && manager.Party().ValidationRouteBossAddDensityGeneration
            == manager.Party().ValidationRouteGeneration;
    auto explicitListedAttackerCount = [&localAdds](Player const* member) -> size_t
    {
        size_t count = 0;
        for (Creature const* candidate : localAdds)
            if (candidate && candidate->GetVictim() == member)
                ++count;
        return count;
    };
    auto observedListedAttackerCount = [&explicitListedAttackerCount](Player const* member)
        -> size_t
    {
        return member
            ? std::max(member->getAttackers().size(), explicitListedAttackerCount(member))
            : 0;
    };
    // A listed swarm needs party-protection rules as soon as it engages,
    // even while the boss remains attackable.  Waiting for the scripted
    // shield/unavailable phase let Azil followers build lethal healer/DPS
    // threat before the tank's density handler existed.
    // Rerun195 proved that the shared large-passive-swarm fact could remain
    // true while a remote damage role's local 45-yard add view flickered
    // below swarm density. That made densityTank null for that role, so it
    // alternated the existing tank-follow staging with add/route movement
    // and could never satisfy the unchanged all-participant 18-yard gate.
    // The shared proof is already generation-scoped and published only by
    // the living tank's 24-plus unengaged observation. Use it to resolve the
    // same loaded tank/healer participants even when this observer has
    // no local swarm view; all staging movement and tank-only activation
    // conditions below remain unchanged.
    bool swarmDefenseActive = highDensityPhase || cohortSwarmActive
        || sharedLargePassiveSwarmStaging;
    std::string role = manager.GetDungeonRole(bot);
    BotClassSpecActionProfile profile =
        BotClassSpecActionProfileStore::Build(bot, role.c_str());
    // Preserve Blood's 30-second ground threat for a real follower wave.
    // Small precursor sets still receive Blood Boil and ordinary pickup,
    // while non-boss trash keeps Death and Decay available at two targets.
    uint32 reservedAreaSpellId = role == "tank"
        && profile.SpecTag == "blood_death_knight" && addCount < 5 ? 43265 : 0;
    Creature* densityApproachAnchor = nullptr;
    if (highDensityPhase && role != "healer")
    {
        Creature* densityAnchor = nullptr;
        float bestDistance = std::numeric_limits<float>::max();
        float nearestDistance = std::numeric_limits<float>::max();
        uint32 bestAnchorGuid = 0;
        uint32 nearestAnchorGuid = 0;
        bool meleeProfile = profile.MovementDirective == "melee"
            || (profile.MaxRange > 0.0f && profile.MaxRange <= 5.0f);
        float minRange = meleeProfile ? 0.0f : profile.MinRange;
        float maxRange = meleeProfile ? 5.0f : profile.MaxRange;
        for (Creature* candidate : localAdds)
        {
            float distance = bot->GetExactDist(candidate);
            uint32 guid = candidate->GetGUID().GetCounter();
            if (!densityApproachAnchor || distance < nearestDistance
                || (distance == nearestDistance && guid < nearestAnchorGuid))
            {
                densityApproachAnchor = candidate;
                nearestDistance = distance;
                nearestAnchorGuid = guid;
            }
            if ((minRange > 0.0f && distance < minRange)
                || (maxRange > 0.0f && distance > maxRange))
                continue;

            if (!densityAnchor || distance < bestDistance
                || (distance == bestDistance && guid < bestAnchorGuid))
            {
                densityAnchor = candidate;
                bestDistance = distance;
                bestAnchorGuid = guid;
            }
        }
        if (role == "tank")
        {
            Creature* looseAdd = nullptr;
            uint8 loosePriority = 0;
            float looseDistance = std::numeric_limits<float>::max();
            uint32 looseGuid = std::numeric_limits<uint32>::max();
            for (Creature* candidate : localAdds)
            {
                Player* victim = candidate->GetVictim()
                    ? candidate->GetVictim()->ToPlayer() : nullptr;
                std::string victimRole = victim ? manager.GetDungeonRole(victim) : "";
                if (!victim || victim == bot || victimRole == "tank")
                    continue;
                uint8 priority = victimRole == "healer" ? 3 : 2;
                float distance = bot->GetExactDist(candidate);
                uint32 guid = candidate->GetGUID().GetCounter();
                bool nearerSamePriority = priority == loosePriority
                    && (distance < looseDistance
                        || (distance == looseDistance && guid < looseGuid));
                if (!looseAdd || priority > loosePriority || nearerSamePriority)
                {
                    looseAdd = candidate;
                    loosePriority = priority;
                    looseDistance = distance;
                    looseGuid = guid;
                }
            }
            add = looseAdd ? looseAdd : densityAnchor;
        }
        else
            add = densityAnchor;
        sharedFocusValid = false;
    }

    Player* densityTank = nullptr;
    Player* densityHealer = nullptr;
    Player* densityDefenseTarget = nullptr;
    uint32 densityTankOwnedAddCount = 0;
    uint32 densityTankSecureAddCount = 0;
    size_t densityDefenseScore = 0;
    uint8 densityDefenseRolePriority = 0;
    size_t densityDefenseAttackerCount = 0;
    uint32 densityDefenseGuid = std::numeric_limits<uint32>::max();
    if (swarmDefenseActive)
    {
        for (BotWorldPopulationMgrBotState::WorldBotState const& cohortState
            : manager.Party().Bots)
        {
            Player* member = manager.GetLoadedBot(cohortState);
            if (!member || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;
            std::string memberRole = manager.GetDungeonRole(member);
            if (!densityTank && memberRole == "tank")
                densityTank = member;
            if (!densityHealer && memberRole == "healer")
                densityHealer = member;
            size_t attackerCount = observedListedAttackerCount(member);
            if (memberRole == "tank" || !attackerCount)
                continue;

            uint8 rolePriority = memberRole == "healer" ? 2 : 1;
            // Preserve a healer bias without allowing a single healer
            // attacker to hide a lethal swarm on a damage dealer.
            size_t defenseScore = attackerCount
                + (memberRole == "healer" ? 3 : 0);
            // Three attackers can erase a healer in one decision interval.
            // Once that threshold is reached, protect the healer before a
            // larger DPS swarm; damage dealers already stop attacks and
            // stack for pickup while the healer must remain able to cast.
            if (memberRole == "healer" && attackerCount >= 3)
                defenseScore += 1000;
            uint32 guid = member->GetGUID().GetCounter();
            if (!densityDefenseTarget || defenseScore > densityDefenseScore
                || (defenseScore == densityDefenseScore
                    && rolePriority > densityDefenseRolePriority)
                || (defenseScore == densityDefenseScore
                    && rolePriority == densityDefenseRolePriority
                    && attackerCount > densityDefenseAttackerCount)
                || (defenseScore == densityDefenseScore
                    && rolePriority == densityDefenseRolePriority
                    && attackerCount == densityDefenseAttackerCount
                    && guid < densityDefenseGuid))
            {
                densityDefenseTarget = member;
                densityDefenseScore = defenseScore;
                densityDefenseRolePriority = rolePriority;
                densityDefenseAttackerCount = attackerCount;
                densityDefenseGuid = guid;
            }
        }
    }

    if (densityTank)
        for (Creature* candidate : localAdds)
            if (candidate && candidate->GetVictim() == densityTank)
            {
                ++densityTankOwnedAddCount;
                float tankThreat = candidate->GetThreatManager().GetThreat(
                    densityTank, true);
                float highestPartyThreat = 0.0f;
                for (BotWorldPopulationMgrBotState::WorldBotState const& cohortState
                    : manager.Party().Bots)
                {
                    Player* member = manager.GetLoadedBot(cohortState);
                    if (!member || member == densityTank || !member->IsAlive()
                        || member->GetMap() != candidate->GetMap())
                        continue;
                    highestPartyThreat = std::max(highestPartyThreat,
                        candidate->GetThreatManager().GetThreat(member, true));
                }
                // Victim ownership alone is not enough to safely release
                // party AoE: a taunt can put the tank only barely ahead,
                // allowing one area tick to flip the entire swarm.  Wait
                // for both an absolute floor and substantial headroom over
                // the highest party member before treating an add as secure.
                if (tankThreat >= 2000.0f
                    && tankThreat >= highestPartyThreat * 2.5f)
                    ++densityTankSecureAddCount;
            }
    bool densityTankOwnsSecureMajority = addCount > 0
        && densityTankSecureAddCount * 10 >= addCount * 9;
    bool densityTankOwnsVictimMajority = addCount > 0
        && densityTankOwnedAddCount * 10 >= addCount * 8;
    // A very large wave must be burned before its incoming damage exceeds
    // tank cooldown and healer throughput. At that point, 80% current
    // victim ownership is sufficient to release party AoE; demanding 90%
    // of adds at 2.5x threat caused DPS to wait while Corborus grew from 30
    // to 57 adds. Rerun157 proved that treating a 16-20-add burst as that
    // emergency released AoE on taunt ownership without secure headroom and
    // immediately flipped most of the wave. Keep those bounded bursts on
    // the existing strict headroom gate while retaining the emergency below
    // the proven 30-add runaway boundary.
    bool urgentSwarmDamageRelease = cohortSwarmActive && addCount >= 24
        && densityTankOwnsVictimMajority;
    bool dpsSwarmDamageRelease = densityTankOwnsSecureMajority
        || urgentSwarmDamageRelease;
    bool botInsideTankPickup = densityTank
        && bot->GetExactDist2d(densityTank) <= 8.0f;

    result.Add = add;
    result.SharedFocusValid = sharedFocusValid;
    result.HighDensityPhase = highDensityPhase;
    result.SwarmDefenseActive = swarmDefenseActive;
    result.Role = std::move(role);
    result.Profile = std::move(profile);
    result.ReservedAreaSpellId = reservedAreaSpellId;
    result.DensityApproachAnchor = densityApproachAnchor;
    result.DensityTank = densityTank;
    result.DensityHealer = densityHealer;
    result.DensityDefenseTarget = densityDefenseTarget;
    result.DensityTankOwnedAddCount = densityTankOwnedAddCount;
    result.DensityTankSecureAddCount = densityTankSecureAddCount;
    result.DensityTankOwnsSecureMajority = densityTankOwnsSecureMajority;
    result.DensityTankOwnsVictimMajority = densityTankOwnsVictimMajority;
    result.UrgentSwarmDamageRelease = urgentSwarmDamageRelease;
    result.DpsSwarmDamageRelease = dpsSwarmDamageRelease;
    result.BotInsideTankPickup = botInsideTankPickup;
    result.ObservedListedAttackerCount =
        [localAdds](Player const* member) -> size_t
    {
        size_t explicitListedAttackerCount = 0;
        for (Creature const* candidate : localAdds)
            if (candidate && candidate->GetVictim() == member)
                ++explicitListedAttackerCount;
        return member
            ? std::max(member->getAttackers().size(),
                explicitListedAttackerCount)
            : 0;
    };
    return result;
}

AddWaveDensityResult ResolveAddWaveDensity(
    AddWaveDensityRequest const& request)
{
    return Context::Run(request);
}
}
