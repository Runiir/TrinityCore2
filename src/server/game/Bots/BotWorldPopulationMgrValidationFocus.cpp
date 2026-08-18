#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupReference.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"
#include "CellImpl.h"
#include "GridNotifiersImpl.h"

#include <chrono>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

Unit* BotWorldPopulationMgr::FindLastKnownValidationRouteFocusTarget(
    Player* bot, std::function<Unit*(Unit*)> const& routeUsableCombatTarget,
    std::function<bool()> const& routeFocusMemoryFresh)
{
    if (!routeFocusMemoryFresh() || !Party().ValidationRouteFocusEntry)
        return nullptr;

    float focusSearchRange = Cohort().Config.ValidationRouteKind == "boss" ? 220.0f : 160.0f;
    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, focusSearchRange);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, focusSearchRange);

    Unit* nearestMatchingEntry = nullptr;
    float nearestMatchingEntryDistance = 0.0f;
    for (WorldObject* object : objects)
    {
        Creature* creature = object ? object->ToCreature() : nullptr;
        if (!creature || creature->GetEntry() != Party().ValidationRouteFocusEntry)
            continue;

        Unit* candidate = routeUsableCombatTarget(creature);
        if (!candidate || !bot->IsValidAttackTarget(candidate))
            continue;

        if (candidate->GetGUID() == Party().ValidationRouteFocusGuid)
            return candidate;
        if (Cohort().Config.ValidationRouteKind != "boss")
            continue;

        float distance = bot->GetExactDist(candidate);
        if (!nearestMatchingEntry || distance < nearestMatchingEntryDistance)
        {
            nearestMatchingEntry = candidate;
            nearestMatchingEntryDistance = distance;
        }
    }

    return Cohort().Config.ValidationRouteKind == "boss" ? nearestMatchingEntry : nullptr;
}

Unit* BotWorldPopulationMgr::FindAuthoritativeValidationRouteFocusTarget(
    Player* bot, std::function<Unit*(Unit*)> const& routeUsableCombatTarget,
    std::function<bool(Creature const*)> const& isValidationRouteScriptTarget,
    std::string& authoritativeFocusFailure)
{
    auto activeCohortFocus = [](Player* member, Unit* focus) -> bool
    {
        return member && focus && (member->IsInCombat() || focus->IsInCombat() || focus->GetVictim());
    };

    auto usableFocus = [&](Unit* focus) -> Unit*
    {
        focus = routeUsableCombatTarget(focus);
        if (!focus)
            return nullptr;
        if (!Party().ValidationRouteFocusGuid.IsEmpty() && focus->GetGUID() == Party().ValidationRouteFocusGuid)
            return focus;
        if (Cohort().Config.ValidationRouteKind != "boss" && !Party().ValidationRouteFocusGuid.IsEmpty())
            return nullptr;
        if (Party().ValidationRouteFocusEntry)
        {
            if (Creature const* creature = focus->ToCreature())
                if (creature->GetEntry() == Party().ValidationRouteFocusEntry)
                    return focus;
        }
        if (Party().ValidationRouteActivationApplied && Cohort().Config.ValidationRouteKind == "boss" && Cohort().Config.ValidationRouteTargetEntry)
        {
            if (Creature const* creature = focus->ToCreature())
                if (isValidationRouteScriptTarget(creature))
                    return focus;
        }
        return nullptr;
    };

    bool sawLoadedCohort = false;
    bool sawSameMapCohort = false;
    bool sawVictimReference = false;
    bool sawStateTargetGuid = false;
    bool sawResolvedStateTarget = false;
    bool sawMemoryFocusGuid = false;
    bool sawResolvedMemoryFocus = false;
    bool sawRejectedReference = false;
    for (WorldBotState const& cohortState : Party().Bots)
    {
        Player* member = GetLoadedBot(cohortState);
        if (!member || member == bot)
            continue;
        sawLoadedCohort = true;
        if (!member->GetMap() || member->GetMap() != bot->GetMap())
            continue;
        sawSameMapCohort = true;

        if (Unit* victim = member->GetVictim())
        {
            sawVictimReference = true;
            if (Unit* focus = usableFocus(victim))
                return focus;
            sawRejectedReference = true;
        }
        if (!cohortState.TargetGuid.IsEmpty())
        {
            sawStateTargetGuid = true;
            if (Unit* resolved = ObjectAccessor::GetUnit(*member, cohortState.TargetGuid))
            {
                sawResolvedStateTarget = true;
                bool activeStateTarget = activeCohortFocus(member, resolved);
                if (activeStateTarget)
                    if (Unit* focus = usableFocus(resolved))
                        return focus;
                if (!activeStateTarget)
                    authoritativeFocusFailure = "authoritative_focus_state_target_inactive";
                else
                    sawRejectedReference = true;
            }
        }
        if (!Party().ValidationRouteFocusGuid.IsEmpty())
        {
            sawMemoryFocusGuid = true;
            if (Unit* resolved = ObjectAccessor::GetUnit(*member, Party().ValidationRouteFocusGuid))
            {
                sawResolvedMemoryFocus = true;
                if (Unit* focus = usableFocus(resolved))
                    return focus;
                sawRejectedReference = true;
            }
        }
    }

    if (!sawLoadedCohort)
        authoritativeFocusFailure = "authoritative_focus_no_loaded_cohort";
    else if (!sawSameMapCohort)
        authoritativeFocusFailure = "authoritative_focus_no_same_map_cohort";
    else if (!sawVictimReference && !sawStateTargetGuid && !sawMemoryFocusGuid)
        authoritativeFocusFailure = "authoritative_focus_no_reference";
    else if ((sawStateTargetGuid && !sawResolvedStateTarget) || (sawMemoryFocusGuid && !sawResolvedMemoryFocus))
        authoritativeFocusFailure = "authoritative_focus_guid_not_resolved";
    else if (sawRejectedReference)
        authoritativeFocusFailure = "authoritative_focus_reference_rejected";
    else
        authoritativeFocusFailure = "authoritative_focus_unavailable";

    if (Player* anchor = FindDungeonAnchor(bot))
    {
        if (Unit* victim = anchor->GetVictim())
        {
            if (Unit* focus = usableFocus(victim))
                return focus;
            authoritativeFocusFailure = "authoritative_focus_anchor_reference_rejected";
        }
        else if (authoritativeFocusFailure == "authoritative_focus_no_reference")
            authoritativeFocusFailure = "authoritative_focus_anchor_no_victim";
    }

    return nullptr;
}


#include <functional>
#include <string>

Unit* BotWorldPopulationMgr::FindValidationRouteGroupFocusTarget(
    Player* bot,
    std::function<Unit*(Unit*)> const& routeUsableValidationFocus,
    std::function<bool()> const& routeFocusMemoryFresh)
{
    if (std::string(GetDungeonRole(bot)) == "tank")
        return nullptr;

    bool livingTankAvailable = false;
    for (WorldBotState const& cohortState : Party().Bots)
        if (Player* member = GetBot(cohortState); member && member->IsAlive()
            && member->GetMap() == bot->GetMap() && std::string(GetDungeonRole(member)) == "tank")
        {
            livingTankAvailable = true;
            break;
        }

    auto activeCohortFocus = [](Player* member, Unit* focus) -> bool
    {
        return member && focus && (member->IsInCombat() || focus->IsInCombat() || focus->GetVictim());
    };
    auto tankOwnsFocus = [&](Player* member, Unit* focus) -> bool
    {
        return member && focus && focus->GetVictim() == member;
    };
    auto activeTankFocus = [&](Unit* focus) -> bool
    {
        if (!focus)
            return false;

        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetBot(cohortState);
            if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap())
                continue;
            if (std::string(GetDungeonRole(member)) != "tank")
                continue;
            if (Cohort().Config.ValidationRouteKind != "boss" && !tankOwnsFocus(member, focus))
                continue;
            if (member->GetVictim() == focus)
                return true;
            if (cohortState.TargetGuid == focus->GetGUID() && activeCohortFocus(member, focus))
                return true;
        }
        return false;
    };

    if (routeFocusMemoryFresh())
        if (Unit* focus = routeUsableValidationFocus(ObjectAccessor::GetUnit(*bot, Party().ValidationRouteFocusGuid)))
            if (Cohort().Config.ValidationRouteKind == "boss" || activeTankFocus(focus))
                return focus;

    Player* anchor = FindDungeonAnchor(bot);
    for (WorldBotState const& cohortState : Party().Bots)
    {
        Player* member = GetBot(cohortState);
        if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap())
            continue;
        if (std::string(GetDungeonRole(member)) != "tank" || cohortState.TargetGuid.IsEmpty())
            continue;

        if (Unit* focus = routeUsableValidationFocus(ObjectAccessor::GetUnit(*bot, cohortState.TargetGuid)))
        {
            if (!activeCohortFocus(member, focus))
                continue;
            if (Cohort().Config.ValidationRouteKind != "boss" && !tankOwnsFocus(member, focus))
                continue;
            return focus;
        }
    }

    if (anchor && anchor != bot)
    {
        if (Unit* focus = routeUsableValidationFocus(anchor->GetVictim()))
            if (Cohort().Config.ValidationRouteKind == "boss" || activeTankFocus(focus))
                return focus;
    }

    Unit* bestFocus = nullptr;
    float bestScore = -1.0f;
    auto considerFocus = [&](Player* member, Unit* focus)
    {
        if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap())
            return;

        focus = routeUsableValidationFocus(focus);
        if (!focus)
            return;

        float score = 1.0f;
        bool memberIsTank = std::string(GetDungeonRole(member)) == "tank";
        if (Cohort().Config.ValidationRouteKind != "boss" && !memberIsTank && livingTankAvailable)
            return;

        if (memberIsTank)
            score += 5.0f;
        if (anchor && member == anchor)
            score += 3.0f;

        auto countVote = [&](Player* voter)
        {
            if (!voter || !voter->IsAlive() || voter->GetMap() != bot->GetMap())
                return;

            if (voter->GetVictim() == focus)
                score += 1.0f;
        };
        if (Group* group = bot->GetGroup())
            for (GroupReference* voteItr = group->GetFirstMember(); voteItr != nullptr; voteItr = voteItr->next())
                countVote(voteItr->GetSource());
        else
        {
            for (WorldBotState const& cohortState : Party().Bots)
            {
                countVote(GetBot(cohortState));
                if (cohortState.TargetGuid == focus->GetGUID())
                    score += 1.0f;
            }
        }

        if (!bestFocus || score > bestScore || (score == bestScore && bot->GetExactDist(focus) < bot->GetExactDist(bestFocus)))
        {
            bestFocus = focus;
            bestScore = score;
        }
    };
    auto considerMember = [&](Player* member)
    {
        considerFocus(member, member ? member->GetVictim() : nullptr);
    };

    if (Group* group = bot->GetGroup())
    {
        for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            considerMember(itr->GetSource());
    }
    else
    {
        for (WorldBotState const& cohortState : Party().Bots)
        {
            Player* member = GetBot(cohortState);
            considerMember(member);
            if (member && !cohortState.TargetGuid.IsEmpty())
            {
                Unit* stateFocus = ObjectAccessor::GetUnit(*bot, cohortState.TargetGuid);
                if (activeCohortFocus(member, stateFocus))
                    considerFocus(member, stateFocus);
            }
        }
    }

    if (bestFocus)
        return bestFocus;

    return nullptr;
}


ObjectGuid BotWorldPopulationMgr::FindValidationRouteTankFocusGuid(
    Player* bot,
    std::function<Unit*(Unit*)> const& routeUsableValidationFocus,
    std::function<bool()> const& routeFocusMemoryFresh)
{
    auto activeCohortFocus = [](Player* member, Unit* focus) -> bool
    {
        return member && focus && (member->IsInCombat() || focus->IsInCombat() || focus->GetVictim());
    };
    auto tankOwnsFocus = [](Player* member, Unit* focus) -> bool
    {
        return member && focus && focus->GetVictim() == member;
    };

    if (routeFocusMemoryFresh())
        if (Unit* focus = routeUsableValidationFocus(ObjectAccessor::GetUnit(*bot, Party().ValidationRouteFocusGuid)))
        {
            if (Cohort().Config.ValidationRouteKind != "boss")
            {
                bool ownedByTank = false;
                for (WorldBotState const& cohortState : Party().Bots)
                {
                    Player* member = GetBot(cohortState);
                    if (member && member != bot && member->IsAlive() && member->GetMap() == bot->GetMap() && std::string(GetDungeonRole(member)) == "tank" && tankOwnsFocus(member, focus))
                    {
                        ownedByTank = true;
                        break;
                    }
                }
                if (!ownedByTank)
                    return ObjectGuid::Empty;
            }
            return focus->GetGUID();
        }

    for (WorldBotState const& cohortState : Party().Bots)
    {
        Player* member = GetBot(cohortState);
        if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap())
            continue;
        if (std::string(GetDungeonRole(member)) != "tank")
            continue;

        if (Unit* victim = routeUsableValidationFocus(member->GetVictim()))
            return victim->GetGUID();
        if (!cohortState.TargetGuid.IsEmpty())
            if (Unit* focus = routeUsableValidationFocus(ObjectAccessor::GetUnit(*member, cohortState.TargetGuid)))
            {
                if (!activeCohortFocus(member, focus))
                    continue;
                if (Cohort().Config.ValidationRouteKind != "boss" && !tankOwnsFocus(member, focus))
                    continue;
                return focus->GetGUID();
            }
    }

    if (Player* anchor = FindDungeonAnchor(bot))
        if (Unit* victim = routeUsableValidationFocus(anchor->GetVictim()))
            return victim->GetGUID();

    return ObjectGuid::Empty;
}

void BotWorldPopulationMgr::RememberValidationRouteFocus(Unit* focus)
{
    if (!focus)
        return;

    Party().ValidationRouteFocusGuid = focus->GetGUID();
    if (Creature const* creature = focus->ToCreature())
        Party().ValidationRouteFocusEntry = creature->GetEntry();
    Party().ValidationRouteFocusMapId = focus->GetMapId();
    Party().ValidationRouteFocusX = focus->GetPositionX();
    Party().ValidationRouteFocusY = focus->GetPositionY();
    Party().ValidationRouteFocusZ = focus->GetPositionZ();
    Party().ValidationRouteFocusSeenMs = NowMs();
    Creature* boss = focus->ToCreature();
    if (Cohort().Config.ValidationRouteKind == "boss"
        && boss
        && focus->GetEntry() == Cohort().Config.ValidationRouteTargetEntry
        && (boss->IsDungeonBoss() || boss->isWorldBoss()))
    {
        Party().ValidationRouteEngagedBossGuid = focus->GetGUID();
        Party().ValidationRouteEngagedBossGeneration = Party().ValidationRouteGeneration;
        Party().ValidationRouteEngagedBossMapId = focus->GetMapId();
        Party().ValidationRouteEngagedBossInstanceId = focus->GetInstanceId();
    }
}

Unit* BotWorldPopulationMgr::MakeExistingValidationRouteCombatReady(
    Player* bot, Creature* creature,
    std::function<bool(Creature const*)> const& isValidationRouteCombatTarget)
{
    if (!Party().ValidationRouteActivationApplied || Cohort().Config.ValidationRouteKind != "boss" || !bot || !bot->IsAlive() || !creature || !creature->IsAlive())
        return nullptr;
    if (!isValidationRouteCombatTarget(creature) || !bot->IsValidAttackTarget(creature))
        return nullptr;

    RememberValidationRouteFocus(creature);
    return creature;
}

Unit* BotWorldPopulationMgr::FindValidationRouteTankFocusTarget(
    Player* bot, std::function<Unit*(Unit*)> const& routeUsableCombatTarget,
    ObjectGuid expectedGuid)
{
    auto activeCohortFocus = [](Player* member, Unit* focus) -> bool
    {
        return member && focus && (member->IsInCombat() || focus->IsInCombat() || focus->GetVictim());
    };

    auto usableExpected = [&](Unit* focus) -> Unit*
    {
        focus = routeUsableCombatTarget(focus);
        if (!focus)
            return nullptr;
        if (!expectedGuid.IsEmpty() && focus->GetGUID() != expectedGuid)
            return nullptr;
        return focus;
    };

    for (WorldBotState const& cohortState : Party().Bots)
    {
        Player* member = GetBot(cohortState);
        if (!member || member == bot || !member->IsAlive() || member->GetMap() != bot->GetMap())
            continue;
        if (std::string(GetDungeonRole(member)) != "tank")
            continue;

        if (Unit* focus = routeUsableCombatTarget(member->GetVictim()))
        {
            RememberValidationRouteFocus(focus);
            return focus;
        }
        if (!cohortState.TargetGuid.IsEmpty())
            if (Unit* focus = usableExpected(ObjectAccessor::GetUnit(*member, cohortState.TargetGuid)))
            {
                if (!activeCohortFocus(member, focus))
                    continue;
                RememberValidationRouteFocus(focus);
                return focus;
            }
    }

    if (Player* anchor = FindDungeonAnchor(bot))
        if (Unit* focus = routeUsableCombatTarget(anchor->GetVictim()))
        {
            RememberValidationRouteFocus(focus);
            return focus;
        }

    return nullptr;
}


float UnitHealthPct(Unit const* unit)
{
    if (!unit || !unit->GetMaxHealth())
        return 0.0f;
    return float(unit->GetHealth()) / float(unit->GetMaxHealth());
}

bool BotWorldPopulationMgr::RecoverAuthoritativeValidationRouteFocus(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity,
    std::function<Unit*()> const& findAuthoritativeRouteFocusTarget,
    std::string const& authoritativeFocusFailure, char const* context)
{
    Unit* focus = findAuthoritativeRouteFocusTarget();
    if (!focus || !focus->IsAlive())
    {
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "validation_route_recovery", &power, stage, activity);
        std::string reason = std::string(context ? context : "assist_unresolved_authoritative_focus") + "_" + authoritativeFocusFailure;
        RecordEvent(state, bot, "validation_route_recovery", nullptr, reason.c_str(), raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
        return false;
    }

    std::string raw = BuildRawJson(bot, focus);
    std::string semantic = BuildSemanticJson(bot, focus, "validation_route_recovery", &power, stage, activity);
    RecordEvent(state, bot, "validation_route_recovery", focus, context ? context : "recover_authoritative_focus", raw.c_str(), semantic.c_str(), UnitHealthPct(focus), Cohort().Config.ValidationRouteTargetEntry);
    state.TargetGuid = focus->GetGUID();
    return true;
}

Unit* BotWorldPopulationMgr::TeacherAssistAuthoritativeValidationFocus(
    WorldBotState& state, Unit* proposedFocus,
    std::function<bool()> const& authoritativeRouteFocusActive,
    std::function<Unit*()> const& findAuthoritativeRouteFocusTarget,
    std::string& authoritativeFocusFailure)
{
    if (!authoritativeRouteFocusActive())
        return proposedFocus;

    Unit* authoritativeFocus = findAuthoritativeRouteFocusTarget();
    if (authoritativeFocus)
    {
        state.ValidationRouteUnresolvedFocusHoldCount = 0;
        return authoritativeFocus;
    }

    ++state.ValidationRouteUnresolvedFocusHoldCount;
    authoritativeFocusFailure = authoritativeFocusFailure.empty() ? "assist_target_search_authoritative_focus" : authoritativeFocusFailure;
    return nullptr;
}
