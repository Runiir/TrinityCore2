#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"

#include "Creature.h"
#include "Player.h"

#include <algorithm>
#include <cmath>

namespace BotWorldPopulationMgrValidationRoute
{
bool DrudgeLaneContext::NonTankEntranceEnvelopeSafe(
    uint32 slot, float x, float y) const
{
    auto const& config = Manager.Cohort().Config;
    if (Sources.size() != 2 || !Sources[0] || !Sources[1])
        return false;
    bool const laneA = std::find(config.ValidationRouteSplitLaneARosterSlots.begin(),
        config.ValidationRouteSplitLaneARosterSlots.end(), slot)
        != config.ValidationRouteSplitLaneARosterSlots.end();
    bool const laneB = std::find(config.ValidationRouteSplitLaneBRosterSlots.begin(),
        config.ValidationRouteSplitLaneBRosterSlots.end(), slot)
        != config.ValidationRouteSplitLaneBRosterSlots.end();
    MemberAnchor const* entrance = DeclaredRecoveryMemberAnchorFor(slot);
    if (laneA == laneB || !entrance)
        return false;

    // Rush temporarily puts a Drudge on top of its native target.  Treating
    // that moving source as the boundary made the whole raid flee its sealed
    // entrance anchors every twenty seconds.  The stable safety boundary is
    // the pair's home geometry: an accepted point must remain at least as far
    // from both room-side homes as this slot's reviewed entrance anchor.
    float const tolerance = config.ValidationRouteSplitNavigationMarginYards;
    for (Creature const* source : Sources)
    {
        Position const& home = source->GetHomePosition();
        float const pointDistance = std::hypot(x - home.GetPositionX(),
            y - home.GetPositionY());
        float const entranceDistance = std::hypot(
            entrance->X - home.GetPositionX(),
            entrance->Y - home.GetPositionY());
        if (pointDistance + tolerance < entranceDistance)
            return false;
    }
    return true;
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
    if (laneA == laneB)
        return false;
    bool const entranceFormation = IsRecoveryFormationActive();
    bool const source0Safe = entranceFormation || SourceUnionSafeAt(
        0, member->GetPositionX(), member->GetPositionY());
    bool const source1Safe = entranceFormation || SourceUnionSafeAt(
        1, member->GetPositionX(), member->GetPositionY());
    float const projection = (member->GetPositionX() - MidpointX) * AxisX
        + (member->GetPositionY() - MidpointY) * AxisY;
    bool const laneSafe = (laneA ? -1.0f : 1.0f) * projection
        >= BotRaidDrudgeGeometry::ArrivalAdjustedLaneProjectionMinimum(
            HomeLaneProjectionMinimum,
            config.ValidationRouteSplitArrivalToleranceYards,
            IsRecoveryFormationActive(), false, IsEntrancePullEstablished());
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
    bool const explicitRecoveryFormation = IsDynamicGroupRecoveryActive();
    if (!BotRaidDrudgeGeometry::DynamicGroupPositionSafe(
            source0Safe, source1Safe, laneSafe,
            explicitRecoveryFormation || sameLaneSpacingSafe))
        return false;
    auto memberState = std::find_if(Manager.Party().Bots.begin(),
        Manager.Party().Bots.end(), [member](WorldBotState const& candidate)
        {
            return candidate.Guid == member->GetGUID();
        });
    return memberState != Manager.Party().Bots.end()
        && CachedAnchorSafe(*memberState, member)
        && (!entranceFormation || NonTankEntranceEnvelopeSafe(
            slot, member->GetPositionX(), member->GetPositionY()));
}
}
