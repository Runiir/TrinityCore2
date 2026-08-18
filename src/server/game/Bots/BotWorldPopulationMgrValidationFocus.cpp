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

