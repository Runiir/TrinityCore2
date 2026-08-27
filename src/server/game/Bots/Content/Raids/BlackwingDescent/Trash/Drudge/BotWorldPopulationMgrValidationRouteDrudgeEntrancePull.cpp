#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgr.h"

#include "Creature.h"
#include "Player.h"

#include <algorithm>

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
    auto recoveryAnchorFor = [&](uint32 slot) -> MemberAnchor const*
    {
        auto const& anchors = config.ValidationRouteSplitRecoveryMemberAnchors;
        auto const found = std::find_if(anchors.begin(), anchors.end(),
            [slot](MemberAnchor const& anchor)
            {
                return anchor.RosterSlot == slot;
            });
        return found == anchors.end() ? nullptr : &*found;
    };
    auto atAnchor = [&](Player const* member, MemberAnchor const* anchor,
        bool tank)
    {
        if (!member || !anchor)
            return false;
        float const tolerance = tank
            ? config.ValidationRouteSplitTankArrivalToleranceYards
            : config.ValidationRouteSplitArrivalToleranceYards;
        return member->GetExactDist(anchor->X, anchor->Y, anchor->Z) <= tolerance;
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
            if (!atAnchor(member, recoveryAnchorFor(slot),
                    roster->second.Role == "tank"))
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
        bool const arrived = atAnchor(Bot, anchor, AssignedTank);
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
        if (AssignedTank && !NativeChargePending)
        {
            PhaseResult const taunt = RunNativeTauntConfirmation(
                true, false, false);
            if (taunt == PhaseResult::Handled)
                return taunt;
        }
        if (!atAnchor(Bot, entrance, AssignedTank))
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
        if (!atAnchor(Bot, entrance, AssignedTank))
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
        if (!atAnchor(Bot, entrance, AssignedTank))
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
