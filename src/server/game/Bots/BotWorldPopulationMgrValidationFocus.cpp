#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Group.h"
#include "GroupReference.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Unit.h"

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

