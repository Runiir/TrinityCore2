#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeTauntConfirmation.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Creature.h"
#include "GameTime.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <algorithm>
#include <chrono>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

namespace BotWorldPopulationMgrValidationRoute
{
DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunNativeTauntConfirmation(
    bool nativeOwnershipAllowed, bool recoveryAnchorsReachedBeforeTick,
    bool combatTankAnchorsReachedBeforeTick)
{
    bool const nativeActionAllowed = nativeOwnershipAllowed
        && (!NativeChargePending
            || (recoveryAnchorsReachedBeforeTick && combatTankAnchorsReachedBeforeTick));
    if (!AssignedTank || !nativeActionAllowed || !LaneSource)
        return PhaseResult::Continue;

    uint32 sourceSpawnId = 0;
    for (uint32 index = 0;
        index < Manager.Cohort().Config.ValidationRouteSplitSourceGuids.size()
            && index < Sources.size(); ++index)
        if (Sources[index] == LaneSource)
        {
            sourceSpawnId = Manager.Cohort().Config.ValidationRouteSplitSourceGuids[index];
            break;
        }
    BotRaidDrudgeTauntConfirmation::Scope const scope{
        Manager.Cohort().AttemptId,
        Manager.Cohort().Raid.WipeGeneration,
        Manager.Party().ValidationRouteGeneration,
        Bot->GetMapId(),
        Bot->GetInstanceId(),
        LaneSource->GetGUID().GetRawValue(),
        sourceSpawnId,
        Bot->GetGUID().GetCounter() };
    auto& confirmation = State.ValidationRouteDrudgeTaunt;
    uint64 const nowMs = NowMs();
    uint32 const currentVictimGuid = LaneSource->GetVictim()
        ? LaneSource->GetVictim()->GetGUID().GetCounter() : 0;
    BotRaidDrudgeTauntConfirmation::Observation const observation =
        BotRaidDrudgeTauntConfirmation::Observe(
            confirmation, scope, currentVictimGuid, nowMs);

    if (LaneSource->GetVictim() == Bot)
    {
        auto const insert = Manager.Party().ValidationRouteDrudgeOwnershipRosterGuids.insert(
            Bot->GetGUID().GetCounter());
        if (insert.second)
            Record(LaneSource, "drudge_lane_native_ownership", SourceSeparation);
    }
    if (observation == BotRaidDrudgeTauntConfirmation::Observation::Confirmed)
    {
        Manager.Party().ValidationRouteDrudgeTauntRosterGuids.insert(
            Bot->GetGUID().GetCounter());
        Record(LaneSource, "drudge_lane_native_taunt_confirmed",
            SourceSeparation, confirmation.SpellId);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    if (LaneSource->GetVictim() == Bot)
        return PhaseResult::Continue;
    if (observation == BotRaidDrudgeTauntConfirmation::Observation::Pending)
    {
        HoldOffense();
        Record(LaneSource, "drudge_lane_native_taunt_pending",
            SourceSeparation, confirmation.SpellId);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }

    BotClassSpecActionProfile profile =
        BotClassSpecActionProfileStore::Build(Bot, "tank");
    bool candidateSeen = false;
    uint32 candidateSpellId = confirmation.SpellId;
    for (BotActionCandidate const& candidate :
        BotClassSpecActionProfileStore::BuildCandidates(Bot, LaneSource, profile))
        if (candidate.Category == BotCombatActionCategory::Taunt)
        {
            candidateSeen = true;
            candidateSpellId = candidate.SpellId;
            if (candidate.RejectReason.empty())
            {
                BotRaidAreaAuthority::SetAllOffenseSuppressed(
                    Bot->GetGUID().GetRawValue(), false);
                bool const taunted = Manager.TryCastCombatSpell(
                    Bot, LaneSource, candidate.SpellId);
                BotRaidAreaAuthority::SetAllOffenseSuppressed(
                    Bot->GetGUID().GetRawValue(), true);
                if (taunted)
                {
                    BotRaidAreaAuthority::Set(Bot->GetGUID().GetRawValue(), true);
                    BotRaidDrudgeTauntConfirmation::Submit(
                        confirmation, scope, candidate.SpellId, nowMs);
                    Record(LaneSource,
                        "drudge_lane_native_taunt_submitted_pending",
                        SourceSeparation, candidate.SpellId);
                    Target = LaneSource;
                    State.TargetGuid = LaneSource->GetGUID();
                    return PhaseResult::Handled;
                }
            }
            else if (NativeChargePending && candidate.RejectReason == "out_of_range")
            {
                SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(candidate.SpellId);
                float const maxRange = spellInfo
                    ? Bot->GetSpellMaxRangeForTarget(LaneSource, spellInfo) : 0.0f;
                float const distance = Bot->GetExactDist2d(LaneSource);
                float const travel = distance - std::max(5.0f, maxRange - 1.0f);
                if (maxRange > 5.0f && travel > 0.0f && distance > 0.001f)
                {
                    float const recoveryX = Bot->GetPositionX()
                        + (LaneSource->GetPositionX() - Bot->GetPositionX()) * travel / distance;
                    float const recoveryY = Bot->GetPositionY()
                        + (LaneSource->GetPositionY() - Bot->GetPositionY()) * travel / distance;
                    float const recoveryZ = Bot->GetPositionZ()
                        + (LaneSource->GetPositionZ() - Bot->GetPositionZ()) * travel / distance;
                    float const projection = (recoveryX - MidpointX) * AxisX
                        + (recoveryY - MidpointY) * AxisY;
                    if (LaneSign * projection >= Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards * 0.5f
                        && StrictTankRecoveryPath(recoveryX, recoveryY, recoveryZ)
                        && Manager.MoveBotToPoint(State, Bot, recoveryX, recoveryY,
                            recoveryZ, false,
                            BotMovementArbitration::Owner::Mechanic,
                            BotMovementArbitration::Priority::Mechanic))
                    {
                        if (confirmation.Pending)
                            BotRaidDrudgeTauntConfirmation::DeferRetry(confirmation, nowMs);
                        Record(LaneSource, "drudge_lane_native_taunt_approach",
                            distance, candidate.SpellId);
                        Target = LaneSource;
                        State.TargetGuid = LaneSource->GetGUID();
                        return PhaseResult::Handled;
                    }
                }
            }
        }

    if (confirmation.Pending)
    {
        BotRaidDrudgeTauntConfirmation::DeferRetry(confirmation, nowMs);
        HoldOffense();
        Record(LaneSource, candidateSeen
            ? "drudge_lane_native_taunt_unconfirmed_retry_backoff"
            : "drudge_lane_native_taunt_pending",
            SourceSeparation, candidateSpellId);
        Target = LaneSource;
        State.TargetGuid = LaneSource->GetGUID();
        return PhaseResult::Handled;
    }
    return PhaseResult::Continue;
}
}
