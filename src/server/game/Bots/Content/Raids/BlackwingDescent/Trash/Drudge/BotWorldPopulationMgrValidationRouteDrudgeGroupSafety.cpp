#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeCombatEnvelope.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"

#include "Creature.h"
#include "Player.h"

#include <algorithm>

namespace BotWorldPopulationMgrValidationRoute
{
bool DrudgeLaneContext::SeedCombatEnvelopeSafe(
    uint32 slot, float x, float y) const
{
    auto const& config = Manager.Cohort().Config;
    if (Sources.size() != 2 || !Sources[0] || !Sources[1])
        return false;
    return BotRaidDrudgeCombatEnvelope::AcceptsConfiguredSeed(
        slot, config.ValidationRouteSplitSeedRosterSlots,
        config.ValidationRouteSplitLaneARosterSlots,
        config.ValidationRouteSplitLaneBRosterSlots,
        { Sources[0]->GetPositionX(), Sources[0]->GetPositionY() },
        { Sources[1]->GetPositionX(), Sources[1]->GetPositionY() },
        config.ValidationRouteSplitSeedMaxRangeYards, { x, y });
}

bool DrudgeLaneContext::ComputeGroupPositionSafe(Player const* member) const
{
    if (!member)
        return false;
    auto memberRoster = Manager.Cohort().Raid.RosterByGuid.find(
        member->GetGUID().GetCounter());
    if (memberRoster == Manager.Cohort().Raid.RosterByGuid.end()
        || memberRoster->second.Role == "tank")
        return false;
    uint32 const slot = memberRoster->second.SlotIndex + 1;
    auto const& config = Manager.Cohort().Config;
    bool const laneA = std::find(config.ValidationRouteSplitLaneARosterSlots.begin(),
        config.ValidationRouteSplitLaneARosterSlots.end(), slot)
        != config.ValidationRouteSplitLaneARosterSlots.end();
    bool const laneB = std::find(config.ValidationRouteSplitLaneBRosterSlots.begin(),
        config.ValidationRouteSplitLaneBRosterSlots.end(), slot)
        != config.ValidationRouteSplitLaneBRosterSlots.end();
    if (laneA == laneB || !SeedCombatEnvelopeSafe(
            slot, member->GetPositionX(), member->GetPositionY()))
        return false;
    bool const source0Safe = SourceUnionSafeAt(
        0, member->GetPositionX(), member->GetPositionY());
    bool const source1Safe = SourceUnionSafeAt(
        1, member->GetPositionX(), member->GetPositionY());
    float const projection = (member->GetPositionX() - MidpointX) * AxisX
        + (member->GetPositionY() - MidpointY) * AxisY;
    bool const laneSafe = (laneA ? -1.0f : 1.0f) * projection
        >= LaneSeparation * 0.25f;
    float const sameLaneMinimum = std::max(3.0f,
        config.ValidationRouteSplitNavigationMarginYards
            + config.ValidationRouteSplitArrivalToleranceYards * 0.5f);
    bool sameLaneSpacingSafe = true;
    for (WorldBotState const& cohortState : Manager.Party().Bots)
    {
        Player* other = Manager.GetLoadedBot(cohortState);
        if (!other || other == member || !other->IsInWorld()
            || !other->IsAlive() || other->GetMap() != Bot->GetMap())
            continue;
        auto otherRoster = Manager.Cohort().Raid.RosterByGuid.find(
            other->GetGUID().GetCounter());
        if (otherRoster == Manager.Cohort().Raid.RosterByGuid.end()
            || otherRoster->second.Role == "tank")
            continue;
        bool const otherLaneA = std::find(
            config.ValidationRouteSplitLaneARosterSlots.begin(),
            config.ValidationRouteSplitLaneARosterSlots.end(),
            otherRoster->second.SlotIndex + 1)
            != config.ValidationRouteSplitLaneARosterSlots.end();
        if (otherLaneA == laneA && member->GetExactDist2d(other) < sameLaneMinimum)
        {
            sameLaneSpacingSafe = false;
            break;
        }
    }
    if (!BotRaidDrudgeGeometry::DynamicGroupPositionSafe(
            source0Safe, source1Safe, laneSafe, sameLaneSpacingSafe))
        return false;
    bool const prepullStaged = Manager.Party().ValidationRouteDrudgePrepullStaged
        && Manager.Party().ValidationRouteDrudgePrepullAttemptId
            == Manager.Cohort().AttemptId
        && Manager.Party().ValidationRouteDrudgePrepullWipeGeneration
            == Manager.Cohort().Raid.WipeGeneration
        && Manager.Party().ValidationRouteDrudgePrepullRouteGeneration
            == Manager.Party().ValidationRouteGeneration;
    if (prepullStaged && IsDynamicGroupRecoveryActive())
        return true;
    auto memberState = std::find_if(Manager.Party().Bots.begin(),
        Manager.Party().Bots.end(), [member](WorldBotState const& candidate)
        {
            return candidate.Guid == member->GetGUID();
        });
    return memberState != Manager.Party().Bots.end()
        && CachedAnchorSafe(*memberState, member);
}
}
