#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Player.h"

#include <algorithm>
#include <array>

namespace BotWorldPopulationMgrValidationRoute
{
namespace
{
using Context = DrudgeLaneContext;

bool NativeEngaged(Context const& context, Creature const* source)
{
    return source && source->IsAlive()
        && (source->IsInCombat() || source->GetVictim()
            || source->GetHealth() < source->GetMaxHealth()
            || (context.Callbacks.IsCombatLinked
                && context.Callbacks.IsCombatLinked(source)));
}
}

DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunEntrancePullActions()
{
    auto const& config = Manager.Cohort().Config;
    // Stack at the cleared Chainwielder doorway. The old recovery formation
    // stretched the raid through Magmaw's room and made every native Rush a
    // new movement problem instead of an ordinary trash ability.
    static std::array<MemberAnchor, 10> const entranceAnchors = {{
        { 1, -320.0f, -120.0f, 214.0f },
        { 2, -340.0f, -120.0f, 214.0f },
        { 3, -326.0f, -95.0f, 214.0f },
        { 4, -328.0f, -95.0f, 214.0f },
        { 5, -330.0f, -95.0f, 214.0f },
        { 6, -304.0f, -95.0f, 214.0f },
        { 7, -327.0f, -99.0f, 214.0f },
        { 8, -329.0f, -99.0f, 214.0f },
        { 9, -331.0f, -95.0f, 214.0f },
        { 10, -350.0f, -95.0f, 214.0f },
    }};
    auto recoveryAnchorFor = [&](uint32 slot) -> MemberAnchor const*
    {
        auto const found = std::find_if(entranceAnchors.begin(), entranceAnchors.end(),
            [slot](MemberAnchor const& anchor)
            {
                return anchor.RosterSlot == slot;
            });
        return found == entranceAnchors.end() ? nullptr : &*found;
    };
    constexpr float TankDoorwayArrivalToleranceYards = 20.0f;
    constexpr float TankDoorwayCombatToleranceYards = 4.0f;
    // The doorway navigation mesh converges ranged members on the same safe
    // ledge instead of every requested per-slot point. Accept that small area;
    // live combat also checks each Drudge's actual Thunderclap distance.
    constexpr float RangedDoorwayArrivalToleranceYards = 10.5f;
    constexpr float RushBaitArrivalToleranceYards = 3.0f;
    constexpr float RangedDoorwaySafeMaximumY = -90.0f;
    constexpr float DrudgeThunderclapSafeDistanceYards = 18.0f;
    auto isRushBaitSlot = [](uint32 slot)
    {
        return slot == 6 || slot == 10;
    };
    auto doorwayToleranceFor = [=](bool tank, uint32 slot)
    {
        return tank ? TankDoorwayArrivalToleranceYards
            : isRushBaitSlot(slot) ? RushBaitArrivalToleranceYards
                                   : RangedDoorwayArrivalToleranceYards;
    };
    auto atAnchor = [&](Player const* member, MemberAnchor const* anchor,
        bool tank, float toleranceOverride = 0.0f)
    {
        if (!member || !anchor)
            return false;
        float const tolerance = toleranceOverride > 0.0f ? toleranceOverride
            : tank ? config.ValidationRouteSplitTankArrivalToleranceYards
                   : config.ValidationRouteSplitArrivalToleranceYards;
        return member->GetExactDist(anchor->X, anchor->Y, anchor->Z) <= tolerance;
    };
    auto rushBaitIsolationSafe = [&](Player const* member, uint32 slot)
    {
        if (!member)
            return false;
        for (WorldBotState const& otherState : Manager.Party().Bots)
        {
            Player* other = Manager.GetLoadedBot(otherState);
            if (!other || !other->IsInWorld() || !other->IsAlive()
                || other->GetMap() != member->GetMap())
                continue;
            auto const otherRoster = Manager.Cohort().Raid.RosterByGuid.find(
                other->GetGUID().GetCounter());
            if (otherRoster == Manager.Cohort().Raid.RosterByGuid.end()
                || !otherRoster->second.Active || !otherRoster->second.LeaseOwned)
                return false;
            uint32 const otherSlot = otherRoster->second.SlotIndex + 1;
            if (otherSlot == slot || otherRoster->second.Role == "tank"
                || (!isRushBaitSlot(slot) && !isRushBaitSlot(otherSlot)))
                continue;
            if (member->GetExactDist2d(other)
                < DrudgeThunderclapSafeDistanceYards)
                return false;
        }
        return true;
    };
    auto exactRosterAtEntrance = [&]
    {
        if (Manager.Party().Bots.size() != Manager.Cohort().Raid.RosterByGuid.size())
            return false;
        uint32 reached = 0;
        for (WorldBotState const& state : Manager.Party().Bots)
        {
            Player* member = Manager.GetLoadedBot(state);
            auto const roster = member ? Manager.Cohort().Raid.RosterByGuid.find(
                member->GetGUID().GetCounter()) : Manager.Cohort().Raid.RosterByGuid.end();
            if (!member || !member->IsInWorld() || !member->IsAlive()
                || member->GetMap() != Bot->GetMap()
                || roster == Manager.Cohort().Raid.RosterByGuid.end()
                || !roster->second.Active || !roster->second.LeaseOwned)
                return false;
            uint32 const slot = roster->second.SlotIndex + 1;
            bool const tank = roster->second.Role == "tank";
            if ((!tank && member->GetPositionY() > RangedDoorwaySafeMaximumY)
                || (!tank && !rushBaitIsolationSafe(member, slot))
                || !atAnchor(member, recoveryAnchorFor(slot), tank,
                    doorwayToleranceFor(tank, slot)))
                return false;
            ++reached;
        }
        return reached == Manager.Cohort().Raid.RosterByGuid.size();
    };
    if (Sources.size() != 2 || !Sources[0] || !Sources[1]
        || !Sources[0]->IsAlive() || !Sources[1]->IsAlive()
        || config.ValidationRouteSplitSourceGuids.size() != 2
        || config.ValidationRouteSplitSourceGuids[0] != 250140
        || config.ValidationRouteSplitSourceGuids[1] != 250141
        || config.ValidationRouteSplitSeedRosterSlots.empty())
        return PhaseResult::Continue;

    bool const scopedEntranceStage =
        Manager.Party().ValidationRouteDrudgePrepullStaged
        && Manager.Party().ValidationRouteDrudgePrepullAttemptId
            == Manager.Cohort().AttemptId
        && Manager.Party().ValidationRouteDrudgePrepullWipeGeneration
            == Manager.Cohort().Raid.WipeGeneration
        && Manager.Party().ValidationRouteDrudgePrepullRouteGeneration
            == Manager.Party().ValidationRouteGeneration;
    bool const source0Engaged = NativeEngaged(*this, Sources[0]);
    bool const source1Engaged = NativeEngaged(*this, Sources[1]);
    bool const pullStarted = source0Engaged || source1Engaged;
    bool const packLinked = source0Engaged && source1Engaged;
    auto outsideBothDrudges = [&](Player const* member)
    {
        return member && std::all_of(Sources.begin(), Sources.end(),
            [member](Creature const* source)
            {
                return !source || !source->IsAlive()
                    || member->GetExactDist2d(source)
                        >= DrudgeThunderclapSafeDistanceYards;
            });
    };
    MemberAnchor const* entrance = recoveryAnchorFor(OneBasedSlot);
    if (!entrance)
    {
        HoldOffense();
        Record(nullptr, "drudge_entrance_anchor_missing");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }

    auto holdOrMoveTo = [&](MemberAnchor const* anchor,
        char const* moveResult, char const* waitResult) -> PhaseResult
    {
        HoldOffense();
        float const tolerance = pullStarted && AssignedTank
            ? TankDoorwayCombatToleranceYards
            : doorwayToleranceFor(AssignedTank, OneBasedSlot);
        bool const arrived = atAnchor(Bot, anchor, AssignedTank, tolerance)
            && (AssignedTank || (Bot->GetPositionY()
                    <= RangedDoorwaySafeMaximumY
                && rushBaitIsolationSafe(Bot, OneBasedSlot)
                && (!pullStarted || outsideBothDrudges(Bot))));
        bool moved = false;
        std::string rejection;
        if (!arrived && StrictNativePath(anchor->X, anchor->Y, anchor->Z,
                true, false, &rejection))
            moved = Manager.MoveBotToPointWithReferenceFloor(State, Bot,
                anchor->X, anchor->Y, anchor->Z, anchor->Z, false,
                BotMovementArbitration::Owner::Mechanic,
                BotMovementArbitration::Priority::Mechanic);
        if (!arrived && !moved)
        {
            State.LastPathRejectReason = rejection.empty()
                ? "drudge_entrance_native_path_rejected" : rejection;
            State.LastRecoveryResult = State.LastPathRejectReason;
        }
        Record(Sources[0], arrived ? waitResult : moveResult,
            Bot->GetExactDist(anchor->X, anchor->Y, anchor->Z));
        Target = Sources[0];
        State.TargetGuid = Sources[0]->GetGUID();
        return PhaseResult::Handled;
    };

    if (pullStarted)
    {
        if (AssignedTank)
        {
            bool const tankAtEntrance = atAnchor(Bot, entrance, true,
                TankDoorwayCombatToleranceYards);
            PhaseResult const taunt = RunNativeTauntConfirmation(
                true, tankAtEntrance, tankAtEntrance);
            if (taunt == PhaseResult::Handled)
                return taunt;
        }
        bool const safeBackline = AssignedTank
            || (Bot->GetPositionY() <= RangedDoorwaySafeMaximumY
                && rushBaitIsolationSafe(Bot, OneBasedSlot)
                && outsideBothDrudges(Bot));
        float const combatTolerance = AssignedTank
            ? TankDoorwayCombatToleranceYards
            : doorwayToleranceFor(false, OneBasedSlot);
        if (!safeBackline || !atAnchor(Bot, entrance, AssignedTank,
                combatTolerance))
            return holdOrMoveTo(entrance, "drudge_entrance_return_move",
                "drudge_entrance_return_wait");
        if (!packLinked)
        {
            HoldOffense();
            Record(Sources[0], "drudge_entrance_native_pack_link_wait");
            Target = Sources[0];
            State.TargetGuid = Sources[0]->GetGUID();
            return PhaseResult::Handled;
        }
        return PhaseResult::Continue;
    }

    if (!scopedEntranceStage)
    {
        bool const safeBackline = AssignedTank
            || (Bot->GetPositionY() <= RangedDoorwaySafeMaximumY
                && rushBaitIsolationSafe(Bot, OneBasedSlot));
        if (!safeBackline || !atAnchor(Bot, entrance, AssignedTank,
                doorwayToleranceFor(AssignedTank, OneBasedSlot)))
            return holdOrMoveTo(entrance, "drudge_entrance_stage_move",
                "drudge_entrance_stage_wait");
        if (!exactRosterAtEntrance())
        {
            HoldOffense();
            Record(Sources[0], "drudge_entrance_exact_roster_stage_wait");
            Target = Sources[0];
            State.TargetGuid = Sources[0]->GetGUID();
            return PhaseResult::Handled;
        }
        auto& party = Manager.Party();
        party.ValidationRouteDrudgePrepullStaged = true;
        party.ValidationRouteDrudgePrepullAttemptId = Manager.Cohort().AttemptId;
        party.ValidationRouteDrudgePrepullWipeGeneration =
            Manager.Cohort().Raid.WipeGeneration;
        party.ValidationRouteDrudgePrepullRouteGeneration =
            party.ValidationRouteGeneration;
        Record(nullptr, "drudge_entrance_exact_roster_staged");
    }

    uint32 const pullOwnerSlot = config.ValidationRouteSplitSeedRosterSlots.front();
    if (OneBasedSlot != pullOwnerSlot)
    {
        bool const safeBackline = AssignedTank
            || (Bot->GetPositionY() <= RangedDoorwaySafeMaximumY
                && rushBaitIsolationSafe(Bot, OneBasedSlot));
        if (!safeBackline || !atAnchor(Bot, entrance, AssignedTank,
                doorwayToleranceFor(AssignedTank, OneBasedSlot)))
            return holdOrMoveTo(entrance, "drudge_entrance_hold_move",
                "drudge_entrance_hold_wait");
        HoldOffense();
        Record(Sources[0], "drudge_entrance_pull_owner_wait");
        Target = Sources[0];
        State.TargetGuid = Sources[0]->GetGUID();
        return PhaseResult::Handled;
    }

    MemberAnchor const* pullAnchor = DeclaredAnchorFor(pullOwnerSlot);
    if (!pullAnchor || !StrictNativePath(pullAnchor->X, pullAnchor->Y,
            pullAnchor->Z, true, false, nullptr))
    {
        HoldOffense();
        Record(Sources[0], "drudge_entrance_pull_anchor_rejected");
        Target = Sources[0];
        State.TargetGuid = Sources[0]->GetGUID();
        return PhaseResult::Handled;
    }
    if (!atAnchor(Bot, pullAnchor, false))
        return holdOrMoveTo(pullAnchor, "drudge_entrance_pull_owner_approach",
            "drudge_entrance_pull_owner_ready");

    Creature* source = Sources[0];
    ResolvedCombatAction action = Manager.ResolveProfileCombatAction(
        Bot, source, 1, false, 0, false, false, true, false, true);
    float const distance = Bot->GetExactDist(source);
    bool const nativeCastReady = action.Valid && action.Type == "cast"
        && action.SpellId && action.TargetGuid == source->GetGUID()
        && action.MovementDirective == "ranged" && action.MaxRange > 5.0f
        && Bot->IsWithinLOSInMap(source)
        && distance <= config.ValidationRouteSplitSeedMaxRangeYards
        && (action.MinRange <= 0.0f || distance >= action.MinRange)
        && (action.MaxRange <= 0.0f || distance <= action.MaxRange);
    if (!nativeCastReady)
    {
        HoldOffense();
        Record(source, "drudge_entrance_pull_native_action_wait", distance);
        Target = source;
        State.TargetGuid = source->GetGUID();
        return PhaseResult::Handled;
    }

    uint64 const ownerGuid = Bot->GetGUID().GetRawValue();
    BotRaidAreaAuthority::SetAllOffenseSuppressed(ownerGuid, false);
    BotActionResult const result = Manager.ExecuteProfileCombatAction(
        &State, Bot, source, &action, 1, false, 0,
        false, false, true, false, true);
    BotRaidAreaAuthority::SetAllOffenseSuppressed(ownerGuid, true);
    BotRaidAreaAuthority::Set(ownerGuid, true);
    Record(source, result == BotActionResult::Ok
        ? "drudge_entrance_pull_cast_submitted"
        : "drudge_entrance_pull_native_action_rejected",
        distance, action.SpellId);
    Target = source;
    State.TargetGuid = source->GetGUID();
    return PhaseResult::Handled;
}
}
