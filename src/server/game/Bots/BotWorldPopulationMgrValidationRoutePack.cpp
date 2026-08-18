#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "MotionMaster.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <functional>
#include <limits>
#include <memory>
#include <string>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;
using BotWorldPopulationMgrSpellSemantics::NowMs;

BotWorldPopulationMgr::ValidationRoutePackContext
BotWorldPopulationMgr::BuildValidationRoutePackContext(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, bool discoveryLeg,
    ValidationRouteTargetingContext const& targeting)
{
    ValidationRoutePackContext result;
    auto isNaturalValidationRoutePackMember = [=, this, &state, &power](Creature const* creature) -> bool
    {
        if (!bot || !creature || !creature->IsAlive() || !creature->GetHealth() || creature->GetMap() != bot->GetMap())
            return false;
        if (Party().ValidationRoutePendingFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRoutePendingFinalTransitionGuids.end())
            return false;
        if (Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID()) != Party().ValidationRouteFinalTransitionGuids.end())
            return false;
        if (targeting.IsImmediateNextEncounter(creature))
            return false;
        bool nativeCombatObserved = creature->IsInCombat()
            || creature->GetVictim()
            || creature->GetHealth() < creature->GetMaxHealth();
        // A future source remains protected while unengaged.  Once native
        // combat has already linked it to this pull, however, it is part of
        // the current natural pack and must be enrolled so pack-clear and
        // death accounting cannot strand the party on one selected GUID.
        if (targeting.IsFutureCanonicalSource(creature) && !nativeCombatObserved)
            return false;
        if (creature->IsDungeonBoss() || creature->isWorldBoss())
            return false;
        return !creature->IsCritter() && !creature->IsPet() && !creature->IsTotem() && !creature->IsSummon()
            && !creature->IsGuardian() && creature->GetOwnerGUID().IsEmpty();
    };
    auto enrollValidationRoutePackMember = [=, this, &state, &power](Creature const* creature, bool engaged) -> void
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !engaged || !isNaturalValidationRoutePackMember(creature))
            return;

        if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration)
        {
            Party().ValidationRoutePackMemberGuids.clear();
            Party().ValidationRoutePackEngagedGuids.clear();
            Party().ValidationRoutePackDeathGuids.clear();
            Party().ValidationRoutePackTransitionGuids.clear();
            Party().ValidationRoutePackGeneration = Party().ValidationRouteGeneration;
            Party().ValidationRoutePackObservedEngagement = false;
            Party().ValidationRoutePackClearCandidateSinceMs = 0;
        }
        bool memberInserted = Party().ValidationRoutePackMemberGuids.insert(creature->GetGUID()).second;
        bool engagementInserted = Party().ValidationRoutePackEngagedGuids.insert(creature->GetGUID()).second;
        Party().ValidationRoutePackTransitionGuids.erase(creature->GetGUID());
        Party().ValidationRoutePackObservedEngagement = true;
        Party().ValidationRoutePackClearCandidateSinceMs = 0;
        if (memberInserted || engagementInserted)
        {
            std::string raw = BuildRawJson(bot, creature);
            std::string semantic = BuildSemanticJson(bot, creature, "validation_route_pack_enrollment", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_pack_enrolled", creature, "cohort_combat_reference", raw.c_str(), semantic.c_str(), bot ? bot->GetExactDist(creature) : 0.0f, creature->GetEntry());
        }
    };
    auto recordValidationRouteScriptedTransition = [=, this, &state, &power](Creature* creature) -> bool
    {
        if (!creature || Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration
            || Party().ValidationRoutePackEngagedGuids.find(creature->GetGUID()) == Party().ValidationRoutePackEngagedGuids.end()
            || Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID()) != Party().ValidationRoutePackTransitionGuids.end())
            return false;

        uint32 auraId = targeting.ResolvedTransitionAura(creature);
        if (!auraId)
            return false;

        Party().ValidationRoutePackTransitionGuids.insert(creature->GetGUID());
        ObjectGuid transitionedGuid = creature->GetGUID();
        bool declaredByFutureNode = false;
        for (size_t routeIndex = Party().ValidationRouteManifestIndex + 1; routeIndex < Party().ValidationRouteManifest.size(); ++routeIndex)
            if (std::find(Party().ValidationRouteManifest[routeIndex].ScriptedEventEntries.begin(), Party().ValidationRouteManifest[routeIndex].ScriptedEventEntries.end(), creature->GetEntry())
                != Party().ValidationRouteManifest[routeIndex].ScriptedEventEntries.end())
            {
                declaredByFutureNode = true;
                break;
            }
        if (!declaredByFutureNode)
        {
            if (discoveryLeg)
                Party().ValidationRoutePendingFinalTransitionGuids.insert(transitionedGuid);
            else
                Party().ValidationRouteFinalTransitionGuids.insert(transitionedGuid);
        }
        if (Party().ValidationRouteFocusGuid == transitionedGuid)
        {
            Party().ValidationRouteFocusGuid.Clear();
            Party().ValidationRouteFocusEntry = 0;
            Party().ValidationRouteFocusSeenMs = 0;
        }
        for (WorldBotState& cohortState : Party().Bots)
        {
            bool pursuingTransition = cohortState.TargetGuid == transitionedGuid
                || cohortState.ValidationRouteCombatProgressTargetGuid == transitionedGuid
                || cohortState.ValidationRoutePackProgressTargetGuid == transitionedGuid;
            if (!pursuingTransition)
                continue;
            if (Player* member = GetLoadedBot(cohortState))
                member->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            if (cohortState.TargetGuid == transitionedGuid)
                cohortState.TargetGuid.Clear();
            if (cohortState.LastDecisionTargetGuid == transitionedGuid)
                cohortState.LastDecisionTargetGuid.Clear();
            cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
            cohortState.ValidationRoutePackProgressTargetGuid.Clear();
            cohortState.ValidationRouteCombatNoProgressCount = 0;
            cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
            cohortState.ValidationRoutePackNoProgressCount = 0;
            cohortState.ValidationRoutePackNoProgressSinceMs = 0;
            if (cohortState.LastCombatAttempt.TargetGuid == transitionedGuid)
                cohortState.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();
            if (cohortState.LastRouteProgress.TargetGuid == transitionedGuid)
                cohortState.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();
            cohortState.ActivePathValid = false;
        }
        std::string raw = BuildRawJson(bot, creature);
        std::string semantic = BuildSemanticJson(bot, creature, "validation_route_scripted_transition", &power, stage, activity);
        RecordEvent(state, bot, "validation_route_scripted_transition", creature, "manifest_transition_observed", raw.c_str(), semantic.c_str(), UnitHealthPct(creature), auraId);
        return true;
    };
    auto retireStaleValidationRoutePackMembers = [=, this, &state, &power]() -> void
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot || !bot->GetMap()
            || Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration)
            return;

        std::vector<ObjectGuid> memberGuids(Party().ValidationRoutePackMemberGuids.begin(), Party().ValidationRoutePackMemberGuids.end());
        for (ObjectGuid const& guid : memberGuids)
        {
            if (Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end()
                || Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end())
                continue;

            Creature* creature = bot->GetMap()->GetCreature(guid);
            if (creature && (!creature->IsAlive() || !creature->GetHealth()))
                continue;

            bool combatLinked = creature && targeting.IsCombatLinked(creature);
            bool recentProgress = false;
            uint64 nowMs = NowMs();
            static constexpr uint64 PackProgressFreshMs = 10000;
            for (WorldBotState const& cohortState : Party().Bots)
            {
                bool recentCombatAttempt = cohortState.LastCombatAttempt.TargetGuid == guid
                    && cohortState.LastCombatAttempt.RecordedAtMs
                    && nowMs >= cohortState.LastCombatAttempt.RecordedAtMs
                    && nowMs - cohortState.LastCombatAttempt.RecordedAtMs <= PackProgressFreshMs;
                bool recentRouteProgress = cohortState.LastRouteProgress.TargetGuid == guid
                    && cohortState.LastRouteProgress.RecordedAtMs
                    && nowMs >= cohortState.LastRouteProgress.RecordedAtMs
                    && nowMs - cohortState.LastRouteProgress.RecordedAtMs <= PackProgressFreshMs;
                if (recentCombatAttempt || recentRouteProgress)
                {
                    recentProgress = true;
                    break;
                }
            }

            bool naturalMember = creature && isNaturalValidationRoutePackMember(creature);
            bool attackable = creature && bot->IsValidAttackTarget(creature);
            // Combat linkage and recent progress are transient.  For the
            // current non-discovery node, an alive natural attackable member
            // that is still an exact declared/persisted route target remains
            // authoritative until actual death or an explicit scripted/final
            // transition removes it.  Do not use a per-bot path test here:
            // retirement is shared state, and one bot's temporary no-path
            // result must not retire a GUID that another bot can reacquire.
            bool const exactCurrentRouteMember = !discoveryLeg
                && targeting.IsScriptTarget(creature);
            if (naturalMember && attackable
                && (combatLinked || recentProgress || exactCurrentRouteMember))
                continue;

            if (!Party().ValidationRoutePackTransitionGuids.insert(guid).second)
                continue;

            if (Party().ValidationRouteFocusGuid == guid)
            {
                Party().ValidationRouteFocusGuid.Clear();
                Party().ValidationRouteFocusEntry = 0;
                Party().ValidationRouteFocusMapId = 0;
                Party().ValidationRouteFocusX = 0.0f;
                Party().ValidationRouteFocusY = 0.0f;
                Party().ValidationRouteFocusZ = 0.0f;
                Party().ValidationRouteFocusSeenMs = 0;
            }
            for (WorldBotState& cohortState : Party().Bots)
            {
                if (Player* member = GetLoadedBot(cohortState); member && cohortState.TargetGuid == guid)
                    member->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                if (cohortState.TargetGuid == guid)
                    cohortState.TargetGuid.Clear();
                if (cohortState.LastDecisionTargetGuid == guid)
                    cohortState.LastDecisionTargetGuid.Clear();
                if (cohortState.ValidationRouteCombatProgressTargetGuid == guid)
                    cohortState.ValidationRouteCombatProgressTargetGuid.Clear();
                if (cohortState.ValidationRoutePackProgressTargetGuid == guid)
                    cohortState.ValidationRoutePackProgressTargetGuid.Clear();
                if (cohortState.LastCombatAttempt.TargetGuid == guid)
                    cohortState.LastCombatAttempt = WorldBotState::CombatAttemptDiagnostic();
                if (cohortState.LastRouteProgress.TargetGuid == guid)
                    cohortState.LastRouteProgress = WorldBotState::RouteProgressDiagnostic();
                cohortState.ValidationRouteCombatNoProgressCount = 0;
                cohortState.ValidationRouteCombatNoProgressSinceMs = 0;
                cohortState.ValidationRoutePackNoProgressCount = 0;
                cohortState.ValidationRoutePackNoProgressSinceMs = 0;
                cohortState.ActivePathValid = false;
            }

            char const* reason = !creature ? "member_not_loaded"
                : !naturalMember ? "member_no_longer_natural"
                : !attackable ? "member_no_longer_attackable"
                : "member_no_longer_engaged_or_progressing";
            std::ostringstream raw;
            raw << "{\"base\":" << BuildRawJson(bot, creature)
                << ",\"pack_retirement\":{\"guid\":" << guid.GetCounter()
                << ",\"route_generation\":" << Party().ValidationRouteGeneration
                << ",\"combat_linked\":" << (combatLinked ? "true" : "false")
                << ",\"recent_progress\":" << (recentProgress ? "true" : "false")
                << ",\"natural_member\":" << (naturalMember ? "true" : "false")
                << ",\"attackable\":" << (attackable ? "true" : "false") << "}}";
            std::string semantic = BuildSemanticJson(bot, creature, "validation_route_pack_retirement", &power, stage, activity);
            RecordEvent(state, bot, "validation_route_pack_retired", creature, reason, raw.str().c_str(), semantic.c_str(),
                creature ? bot->GetExactDist(creature) : 0.0f, creature ? creature->GetEntry() : 0);
        }
    };
    auto enrollEngagedValidationRoutePackMembers = [=, this, &state, &power]() -> void
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot)
            return;

        targeting.ForEachActiveCombat([&](Creature* creature)
        {
            if (!isNaturalValidationRoutePackMember(creature))
                return;

            enrollValidationRoutePackMember(creature, true);
            recordValidationRouteScriptedTransition(creature);
        });

        // CombatManager references are not guaranteed to exist for every
        // member of a native area pull.  The first Stonecore 5H trace exposed
        // this boundary: the party had ten engaged trash creatures, but only
        // the first selected GUID was in the reference iterator.  Once that
        // GUID died the route ledger could not prove the natural pack clear
        // and sent the whole party into an unnecessary runback.  In the
        // discovery leg, supplement the reference scan with a bounded nearby
        // world scan and enroll every alive natural creature that has native
        // combat/victim/health-loss evidence.  Future canonical sources,
        // bosses, scripted actors, and next-route members remain excluded by
        // isNaturalValidationRoutePackMember().
        if (discoveryLeg && bot->GetMap())
        {
            auto isCurrentNativeNaturalPackMember = [&](Creature const* creature) -> bool
            {
                if (!creature || !creature->IsAlive() || !creature->GetHealth()
                    || creature->GetMap() != bot->GetMap()
                    || !bot->IsValidAttackTarget(creature)
                    || Party().ValidationRoutePendingFinalTransitionGuids.find(creature->GetGUID())
                        != Party().ValidationRoutePendingFinalTransitionGuids.end()
                    || Party().ValidationRouteFinalTransitionGuids.find(creature->GetGUID())
                        != Party().ValidationRouteFinalTransitionGuids.end()
                    || targeting.IsImmediateNextEncounter(creature)
                    || targeting.IsPendingScripted(creature)
                    || creature->IsDungeonBoss() || creature->isWorldBoss()
                    || creature->IsCritter() || creature->IsPet()
                    || creature->IsTotem() || creature->IsSummon()
                    || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
                    return false;

                return creature->IsInCombat() || creature->GetVictim()
                    || creature->GetHealth() < creature->GetMaxHealth();
            };
            std::vector<WorldObject*> nearbyObjects;
            Trinity::AllWorldObjectsInRange nearbyCheck(bot, 80.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> nearbySearcher(
                bot, nearbyObjects, nearbyCheck);
            Cell::VisitAllObjects(bot, nearbySearcher, 80.0f);
            for (WorldObject* object : nearbyObjects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!isCurrentNativeNaturalPackMember(creature))
                    continue;

                enrollValidationRoutePackMember(creature, true);
                recordValidationRouteScriptedTransition(creature);
            }
        }

        // Passive scripted actors do not always create a CombatManager PvE
        // reference when they are only clipped by native area damage.  That
        // is still valid native handoff evidence, but the reference iterator
        // above cannot see it.  Observe only the current node's declared
        // scripted entries, and require combat/victim state or real health
        // loss before enrolling; this never discovers or pulls a future node.
        if (discoveryLeg && bot->GetMap())
        {
            std::vector<WorldObject*> objects;
            Trinity::AllWorldObjectsInRange check(bot, 220.0f);
            Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
            Cell::VisitAllObjects(bot, searcher, 220.0f);
            for (WorldObject* object : objects)
            {
                Creature* creature = object ? object->ToCreature() : nullptr;
                if (!creature || !targeting.IsPendingScripted(creature)
                    || !creature->IsAlive() || !creature->GetHealth()
                    || !bot->IsValidAttackTarget(creature))
                    continue;

                bool nativeCombatObserved = creature->IsInCombat()
                    || creature->GetVictim()
                    || creature->GetHealth() < creature->GetMaxHealth();
                if (!nativeCombatObserved)
                    continue;

                enrollValidationRoutePackMember(creature, true);
                recordValidationRouteScriptedTransition(creature);
            }
        }

        if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration || !bot->GetMap())
            return;
        std::vector<ObjectGuid> memberGuids(Party().ValidationRoutePackMemberGuids.begin(), Party().ValidationRoutePackMemberGuids.end());
        for (ObjectGuid const& guid : memberGuids)
            if (Creature* creature = bot->GetMap()->GetCreature(guid))
                recordValidationRouteScriptedTransition(creature);
        retireStaleValidationRoutePackMembers();
    };
    auto persistedValidationRoutePackHasLiveMembers = [=, this, &state, &power]() -> bool
    {
        if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration)
            return false;
        for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
            if (Party().ValidationRoutePackDeathGuids.find(guid) == Party().ValidationRoutePackDeathGuids.end()
                && Party().ValidationRoutePackTransitionGuids.find(guid) == Party().ValidationRoutePackTransitionGuids.end())
                return true;
        return false;
    };
    auto activeValidationRoutePackTarget = [=, this, &state, &power]() -> Unit*
    {
        if (Party().ValidationRoutePackGeneration != Party().ValidationRouteGeneration || !bot || !bot->GetMap())
            return nullptr;

        Creature* best = nullptr;
        float bestScore = -std::numeric_limits<float>::max();
        for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
        {
            if (Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end()
                || Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end())
                continue;
            Creature* creature = bot->GetMap()->GetCreature(guid);
            if (!creature || !creature->IsAlive() || !creature->GetHealth() || !bot->IsValidAttackTarget(creature))
                continue;
            // Discovery's current scripted actor is enrolled only after its
            // native combat state is observed.  It is then a persisted member
            // of the current pack even when the discovery node has no static
            // PackTargetEntries (Millhouse is the canonical example).  Future
            // scripted actors remain protected until their own transition.
            bool currentDiscoveryPackMember = discoveryLeg
                && Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID()) != Party().ValidationRoutePackMemberGuids.end();
            // Reengagement is restricted to the exact declared pack entries
            // (or the persisted current discovery member). A member that is
            // already in native combat may have moved off the original route
            // corridor, so requiring a fresh path to the navigation anchor
            // would incorrectly discard the real pull and let the tank select
            // an unrelated second creature. Keep the engaged member
            // authoritative; only an unengaged member needs a new path.
            bool const persistedCurrentPackMember =
                Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
                && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())
                    != Party().ValidationRoutePackMemberGuids.end();
            bool const persistedCurrentPackCombat = persistedCurrentPackMember
                && (creature->IsInCombat() || creature->GetVictim());
            if ((!targeting.IsRoutePackEntry(creature->GetEntry()) && !currentDiscoveryPackMember)
                || (!targeting.HasStrictPath(creature)
                    && !persistedCurrentPackCombat))
                continue;
            Unit* victim = creature->GetVictim();
            bool botIsTank = std::string(GetDungeonRole(bot)) == "tank";
            Player* victimPlayer = victim ? victim->ToPlayer() : nullptr;
            std::string victimRole = victimPlayer ? GetDungeonRole(victimPlayer) : "";
            bool victimIsTank = victimRole == "tank";
            float score = (creature->IsInCombat() || victim ? 10000.0f : 0.0f)
                - bot->GetExactDist(creature);
            // Once the current discovery scripted actor has been observed in
            // native combat, it is the handoff target—not ordinary corridor
            // trash.  Keep future scripted actors protected, but give this
            // enrolled actor deterministic focus so its transition aura can
            // actually be reached before the party dies to the surrounding
            // pack.  Without this bias the tank's victim/role score can keep
            // selecting a normal trash mob while AoE still chips the actor.
            if (currentDiscoveryPackMember && targeting.IsPendingScripted(creature))
                score += 50000.0f;
            if (botIsTank && victimRole == "healer")
                score += 30000.0f;
            else if (botIsTank && victim && !victimIsTank)
                score += 20000.0f;
            else if (botIsTank && !victim)
                score += 5000.0f;
            if (victim == bot)
                score += 1000.0f;
            if (!best || score > bestScore)
            {
                best = creature;
                bestScore = score;
            }
        }
        return best;
    };
    auto findNearestTrashClusterMob = [=, this, &state, &power]() -> Unit*
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot)
            return nullptr;
        if (discoveryLeg)
            return targeting.FindForwardDiscovery();

        float radius = Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f ? Cohort().Config.ValidationRouteClusterRadiusYards : 90.0f;
        float searchRange = std::max(40.0f, bot->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) + radius + 40.0f);
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, searchRange);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, searchRange);

        Unit* best = nullptr;
        float bestScore = std::numeric_limits<float>::max();
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!targeting.IsEligibleTrash(creature))
                continue;
            float score = bot->GetExactDist(creature) + creature->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) * 0.25f;
            if (!best || score < bestScore)
            {
                best = creature;
                bestScore = score;
            }
        }
        if (Creature* creature = best ? best->ToCreature() : nullptr)
            enrollValidationRoutePackMember(creature, targeting.IsCombatLinked(creature));
        return best;
    };
    auto findTrashClusterThreatTarget = [=, this, &state, &power]() -> Unit*
    {
        if (Cohort().Config.ValidationRouteKind == "boss" || !bot)
            return nullptr;

        enrollEngagedValidationRoutePackMembers();
        if (Unit* packTarget = activeValidationRoutePackTarget())
            return packTarget;
        if (Unit* scriptedTarget = targeting.FindCurrentDiscoveryScripted())
            return scriptedTarget;
        // A live current-pack member is a hard ownership boundary. If it is
        // temporarily not pathable from this decision point, hold the party
        // rather than pulling a second natural creature and compounding the
        // encounter. The next native combat/path update can reselect the same
        // member through activeValidationRoutePackTarget().
        if (Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration)
            for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
                if (Party().ValidationRoutePackDeathGuids.find(guid)
                        == Party().ValidationRoutePackDeathGuids.end()
                    && Party().ValidationRoutePackTransitionGuids.find(guid)
                        == Party().ValidationRoutePackTransitionGuids.end())
                    return nullptr;
        float radius = discoveryLeg ? 120.0f : (Cohort().Config.ValidationRouteClusterRadiusYards > 1.0f ? Cohort().Config.ValidationRouteClusterRadiusYards : 90.0f);
        float searchRange = std::max(40.0f, bot->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ) + radius + 40.0f);
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, searchRange);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, searchRange);

        Unit* best = nullptr;
        float bestScore = -1.0f;
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!targeting.IsEligibleTrash(creature))
                continue;

            Unit* victim = creature->GetVictim();
            Player* victimPlayer = victim ? victim->ToPlayer() : nullptr;
            std::string victimRole = victimPlayer ? GetDungeonRole(victimPlayer) : "";
            bool looseOnNonTank = victim && victimRole != "tank";
            bool unengaged = !victim;
            float score = 1000.0f - bot->GetExactDist(creature);
            if (victimRole == "healer")
                score += 7500.0f;
            else if (looseOnNonTank)
                score += 5000.0f;
            else if (unengaged)
                score += 1500.0f;
            if (creature == bot->GetVictim())
                score += 250.0f;

            if (!best || score > bestScore)
            {
                best = creature;
                bestScore = score;
            }
        }
        if (Creature* creature = best ? best->ToCreature() : nullptr)
            enrollValidationRoutePackMember(creature, targeting.IsCombatLinked(creature));
        return best;
    };
    result.IsNaturalMember = isNaturalValidationRoutePackMember;
    result.EnrollMember = enrollValidationRoutePackMember;
    result.RecordScriptedTransition = recordValidationRouteScriptedTransition;
    result.RetireStaleMembers = retireStaleValidationRoutePackMembers;
    result.EnrollEngagedMembers = enrollEngagedValidationRoutePackMembers;
    result.HasLiveMembers = persistedValidationRoutePackHasLiveMembers;
    result.ActiveTarget = activeValidationRoutePackTarget;
    result.FindNearestTrash = findNearestTrashClusterMob;
    result.FindTrashThreat = findTrashClusterThreatTarget;
    return result;
}
