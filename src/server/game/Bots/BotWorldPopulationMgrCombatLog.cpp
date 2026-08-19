#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeThreatSeedState.h"
#include "Creature.h"
#include "GameTime.h"
#include "Log.h"
#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Totem.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <string>
#include <utility>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

Player* CombatOwnerPlayer(Unit* unit)
{
    if (!unit)
        return nullptr;

    if (Player* player = unit->GetCharmerOrOwnerPlayerOrPlayerItself())
        return player;

    // Resolve nested summon ownership (for example elemental -> totem ->
    // player). The generic helper only checks one owner GUID level.
    Unit* current = unit;
    for (uint8 depth = 0; depth < 4 && current; ++depth)
    {
        current = current->IsTotem() ? current->ToTotem()->GetOwner() : current->GetCharmerOrOwner();
        if (!current)
            break;
        if (Player* player = current->ToPlayer())
            return player;
    }

    return nullptr;
}
}

uint64 BotWorldPopulationMgr::BeginPendingHealCast(Player* bot, Unit* target, uint32 spellId, std::string const& candidateMaskJson, std::string const& chosenActionJson)
{
    if (!bot || !target || !spellId || GetDungeonRole(bot) != std::string("healer"))
        return 0;

    PendingHealCast cast;
    cast.CastId = Party().NextHealCastId++;
    cast.BotGuid = bot->GetGUID();
    cast.SpellId = spellId;
    cast.ChosenTargetGuid = target->GetGUID();
    cast.StartedAtMs = NowMs();
    SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
    uint32 castTime = info ? std::max<int32>(0, info->CalcCastTime(bot->getLevel())) : 0;
    cast.DeadlineMs = cast.StartedAtMs + std::max<uint32>(5000, castTime + 3000);
    cast.ManaBefore = bot->GetPower(POWER_MANA);
    cast.AttackersBefore = uint32(bot->GetThreatManager().GetThreatenedByMeList().size());
    for (auto const& [guid, ref] : bot->GetThreatManager().GetThreatenedByMeList())
        if (ref)
            cast.ThreatBefore += ref->GetThreat();
    uint32 key = bot->GetGUID().GetCounter();
    auto mask = Party().LastCombatMaskByBot.find(key);
    auto chosen = Party().LastChosenCombatByBot.find(key);
    cast.CandidateMaskJson = !candidateMaskJson.empty() ? candidateMaskJson : (mask == Party().LastCombatMaskByBot.end() ? "{}" : mask->second);
    cast.ChosenActionJson = !chosenActionJson.empty() ? chosenActionJson : (chosen == Party().LastChosenCombatByBot.end() ? "{}" : chosen->second);
    uint64 castId = cast.CastId;
    Party().PendingHealCasts.emplace(castId, std::move(cast));
    return castId;
}

uint64 BotWorldPopulationMgr::NotifyBotSpellStarted(Player* caster, Unit* target, uint32 spellId, std::string const& candidateMaskJson, std::string const& chosenActionJson)
{
    return BeginPendingHealCast(caster, target, spellId, candidateMaskJson, chosenActionJson);
}

void BotWorldPopulationMgr::CancelBotSpellStart(uint64 castId, Player* caster, char const* reason)
{
    auto itr = Party().PendingHealCasts.find(castId);
    if (itr == Party().PendingHealCasts.end())
        return;
    PendingHealCast cast = itr->second;
    Party().PendingHealCasts.erase(itr);
    FlushPendingHealCast(cast, caster, "rejected", reason);
}

void BotWorldPopulationMgr::NotifyCreatureDeath(Creature* killed)
{
    if (!Cohort().Active || !killed || !Cohort().Config.ValidationRouteEnable || Cohort().Config.ValidationRouteKind != "boss"
        || killed->IsAlive() || killed->GetHealth()
        || (!killed->IsDungeonBoss() && !killed->isWorldBoss())
        || killed->GetEntry() != Cohort().Config.ValidationRouteTargetEntry
        || Party().ValidationRouteEngagedBossGuid != killed->GetGUID()
        || Party().ValidationRouteEngagedBossGeneration != Party().ValidationRouteGeneration
        || Party().ValidationRouteEngagedBossMapId != killed->GetMapId()
        || Party().ValidationRouteEngagedBossInstanceId != killed->GetInstanceId())
        return;

    Party().ValidationRouteConfirmedBossDeathGuid = killed->GetGUID();
    Party().ValidationRouteConfirmedBossDeathGeneration = Party().ValidationRouteGeneration;
    Party().ValidationRouteConfirmedBossDeathMapId = killed->GetMapId();
    Party().ValidationRouteConfirmedBossDeathInstanceId = killed->GetInstanceId();

    if (Party().ValidationRouteRecordedKillGuids.find(killed->GetGUID()) != Party().ValidationRouteRecordedKillGuids.end())
        return;

    WorldBotState* reporterState = nullptr;
    Player* reporter = nullptr;
    for (WorldBotState& state : Party().Bots)
    {
        Player* candidate = GetLoadedBot(state);
        if (!candidate || !candidate->IsInWorld()
            || state.ValidationRouteGeneration != Party().ValidationRouteGeneration
            || state.ValidationCohortMapId != killed->GetMapId()
            || state.ValidationCohortInstanceId != killed->GetInstanceId())
            continue;
        reporterState = &state;
        reporter = candidate;
        break;
    }
    if (!reporterState || !reporter)
        return;

    Party().ValidationRouteRecordedKillGuids.insert(killed->GetGUID());
    Party().ValidationRouteBossDeathEvidence.push_back({Cohort().Config.ValidationRouteNodeId, Party().ValidationRouteGeneration, Cohort().Config.ValidationRouteKind, killed->GetGUID(), killed->GetEntry(), "confirmed_unit_death"});
    ++Cohort().Metrics.Kills;
    reporterState->LastKilledTargetGuid = killed->GetGUID();
    std::string raw = BuildRawJson(reporter, killed);
    std::string semantic = BuildSemanticJson(reporter, killed, "validation_route_boss_outcome", nullptr);
    RecordEvent(*reporterState, reporter, "boss_killed", killed, "confirmed_unit_death", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Metrics.Kills);

    if (Cohort().Config.ValidationRouteKind == "boss")
    {
        uint64 nowMs = NowMs();
        for (WorldBotState& state : Party().Bots)
        {
            state.TargetGuid.Clear();
            state.ValidationRouteCombatProgressTargetGuid.Clear();
            state.ValidationRoutePackProgressTargetGuid.Clear();
            state.ValidationRouteCombatNoProgressCount = 0;
            state.ValidationRouteCombatNoProgressSinceMs = 0;
            state.ValidationRoutePackNoProgressCount = 0;
            state.ValidationRoutePackNoProgressSinceMs = 0;
            state.ValidationRouteUnresolvedFocusHoldCount = 0;
            state.ValidationRouteTerminalState = true;
            state.ValidationRouteTerminalAtMs = nowMs;
            state.ValidationRouteTerminalGeneration = Party().ValidationRouteGeneration;
            state.ValidationRouteTerminalReason = "boss_killed";
            state.LoopRecoveryCooldownUntilMs = nowMs + 60000;
        }
        if (!Party().ValidationRouteManifest.empty() && Cohort().Config.ValidationRouteAdvanceMode == "terminal")
        {
            Party().ValidationRouteManifestAdvancePending = true;
            Party().ValidationRouteManifestAdvanceGeneration = Party().ValidationRouteGeneration;
            Party().ValidationRouteManifestAdvanceReason = "boss_killed";
        }
        RecordEvent(*reporterState, reporter, "validation_route_terminal", killed, "boss_killed", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Config.ValidationRouteTargetEntry);
    }
}

void BotWorldPopulationMgr::NotifyBotHeal(Unit* healer, Unit* target, uint32 spellId, uint32 attemptedHeal, uint32 effectiveHeal, uint32 absorbedHeal)
{
    if (!healer || !target || !spellId)
        return;
    Unit* owner = healer;
    if (healer->GetTypeId() == TYPEID_UNIT && (healer->IsTotem() || healer->IsPet()))
        owner = healer->GetOwner();
    Player* bot = owner ? owner->ToPlayer() : nullptr;
    if (!bot)
        return;

    uint64 now = NowMs();
    PendingHealCast* best = nullptr;
    for (auto& [id, cast] : Party().PendingHealCasts)
        if (cast.BotGuid == bot->GetGUID() && cast.SpellId == spellId
            && now >= cast.StartedAtMs && now <= cast.DeadlineMs
            && (cast.ChosenTargetGuid == target->GetGUID() || cast.SpellFinished)
            && (!best || cast.StartedAtMs > best->StartedAtMs))
            best = &cast;
    if (!best)
    {
        TC_LOG_DEBUG("server", "Unattributed bot heal bot=%s spell=%u target=%s attempted=%u effective=%u absorbed=%u reason=no_matching_cast_window",
            bot->GetGUID().ToString().c_str(), spellId, target->GetGUID().ToString().c_str(), attemptedHeal, effectiveHeal, absorbedHeal);
        return;
    }
    best->AttemptedHeal += attemptedHeal;
    best->EffectiveHeal += effectiveHeal;
    best->AbsorbedHeal += absorbedHeal;
    best->AffectedAllyGuids.insert(target->GetGUID().GetRawValue());
    best->LastHealAtMs = now;
}

void BotWorldPopulationMgr::ResetCombatLog()
{
    Party().CombatLogAbilities.clear();
    Party().CombatLogSecondBuckets.clear();
    Party().CombatLogRecentEvents.clear();
    Party().CombatLogEventCount = 0;
    Party().CombatLogRecentEventsDropped = 0;
}

Player* BotWorldPopulationMgr::FindCombatLogCohortPlayer(Unit* unit) const
{
    Player* player = CombatOwnerPlayer(unit);
    if (!player)
        return nullptr;

    for (WorldBotState const& state : Party().Bots)
        if (state.Guid == player->GetGUID())
            return GetLoadedBot(state) == player ? player : nullptr;
    return nullptr;
}

void BotWorldPopulationMgr::AddCombatLogAggregate(CombatLogPerspective perspective, Player* actor, Unit* source,
    Unit* target, uint32 spellId, uint32 effectType, uint32 amount, uint32 rawAmount, uint32 absorbedAmount,
    uint64 timestampMs)
{
    if (!actor || !source || !target)
        return;

    bool const sourceIsPet = source != actor && CombatOwnerPlayer(source) == actor;

    CombatLogAbilityKey key;
    key.RouteGeneration = Party().ValidationRouteGeneration;
    key.Perspective = perspective;
    key.ActorGuid = actor->GetGUID().GetCounter();
    key.SourceEntry = source->GetEntry();
    key.SpellId = spellId;
    key.TargetEntry = target->GetEntry();
    key.EffectType = effectType;

    CombatLogAbilityAggregate& aggregate = Party().CombatLogAbilities[key];
    if (!aggregate.EventCount)
    {
        aggregate.RouteNodeId = Cohort().Config.ValidationRouteNodeId;
        aggregate.RouteLabel = Cohort().Config.ValidationRouteLabel;
        aggregate.ActorName = actor->GetName();
        aggregate.ActorRole = GetDungeonRole(actor);
        aggregate.ActorClassId = actor->getClass();
        aggregate.SourceName = source->GetName();
        aggregate.SpellName = spellId ? (sSpellMgr->GetSpellInfo(spellId) ? sSpellMgr->GetSpellInfo(spellId)->SpellName : "Unknown") : "Melee";
        aggregate.TargetName = target->GetName();
        aggregate.FirstAtMs = timestampMs;
        aggregate.SourceIsPet = sourceIsPet;
    }

    float distance = source->GetExactDist(target);
    aggregate.LastAtMs = timestampMs;
    ++aggregate.EventCount;
    aggregate.Amount += amount;
    aggregate.RawAmount += rawAmount;
    aggregate.AbsorbedAmount += absorbedAmount;
    aggregate.MovingEvents += source->isMoving() ? 1 : 0;
    aggregate.DistanceTotal += distance;
    if (aggregate.MinDistance < 0.0f || distance < aggregate.MinDistance)
        aggregate.MinDistance = distance;
    aggregate.MaxDistance = std::max(aggregate.MaxDistance, distance);
    Party().CombatLogSecondBuckets[std::make_tuple(Party().ValidationRouteGeneration, perspective,
        actor->GetGUID().GetCounter(), sourceIsPet, timestampMs / 1000)] += amount;
}

void BotWorldPopulationMgr::AddCombatLogEvent(char const* kind, Player* actor, Unit* source, Unit* target,
    uint32 spellId, uint32 effectType, uint32 schoolMask, uint32 amount, uint32 rawAmount,
    uint32 absorbedAmount, uint64 timestampMs)
{
    if (!actor || !source || !target)
        return;

    CombatLogEvent event;
    event.TimestampMs = timestampMs;
    event.RouteGeneration = Party().ValidationRouteGeneration;
    event.RouteNodeId = Cohort().Config.ValidationRouteNodeId;
    event.Kind = kind ? kind : "unknown";
    event.ActorGuid = actor->GetGUID().GetCounter();
    event.ActorName = actor->GetName();
    event.ActorRole = GetDungeonRole(actor);
    event.ActorClassId = actor->getClass();
    event.SourceGuid = source->GetGUID().GetCounter();
    event.SourceEntry = source->GetEntry();
    event.SourceName = source->GetName();
    event.TargetGuid = target->GetGUID().GetCounter();
    event.TargetEntry = target->GetEntry();
    event.TargetName = target->GetName();
    event.SpellId = spellId;
    event.SpellName = spellId ? (sSpellMgr->GetSpellInfo(spellId) ? sSpellMgr->GetSpellInfo(spellId)->SpellName : "Unknown") : "Melee";
    event.EffectType = effectType;
    event.SchoolMask = schoolMask;
    event.Amount = amount;
    event.RawAmount = rawAmount;
    event.AbsorbedAmount = absorbedAmount;
    event.SourceX = source->GetPositionX();
    event.SourceY = source->GetPositionY();
    event.SourceZ = source->GetPositionZ();
    event.TargetX = target->GetPositionX();
    event.TargetY = target->GetPositionY();
    event.TargetZ = target->GetPositionZ();
    event.Distance = source->GetExactDist(target);
    event.SourceMoving = source->isMoving();
    event.SourceIsPet = source != actor && CombatOwnerPlayer(source) == actor;
    Party().CombatLogRecentEvents.push_back(std::move(event));
    static constexpr size_t MaxRecentCombatEvents = 4096;
    if (Party().CombatLogRecentEvents.size() > MaxRecentCombatEvents)
    {
        Party().CombatLogRecentEvents.pop_front();
        ++Party().CombatLogRecentEventsDropped;
    }
}

uint64 BotWorldPopulationMgr::NotifyNativeCreatureSpellStarted(Creature* caster, Unit* target, uint32 spellId)
{
    if (!Cohort().Active || !caster || !target
        || Cohort().Config.ValidationRouteMechanicProfile != "trash_two_tank_charge_lanes"
        || spellId != Cohort().Config.ValidationRouteChargeSpellId
        || caster->GetEntry() != Cohort().Config.ValidationRouteMinimumDistanceSourceEntry)
        return 0;

    uint32 const sourceSpawnId = uint32(caster->GetSpawnId());
    bool const exactSource = std::find(
        Cohort().Config.ValidationRouteSplitSourceGuids.begin(),
        Cohort().Config.ValidationRouteSplitSourceGuids.end(), sourceSpawnId)
        != Cohort().Config.ValidationRouteSplitSourceGuids.end();
    if (!exactSource)
        return 0;

    uint64 const observedAtMs = NowMs();
    bool const sameSourceRecoveryMissed = std::any_of(
        Party().ValidationRouteDrudgeChargeObservations.begin(),
        Party().ValidationRouteDrudgeChargeObservations.end(),
        [this, sourceSpawnId](ValidationRouteDrudgeChargeObservation const& observation)
        {
            return observation.SourceSpawnId == sourceSpawnId
                && observation.Landed && !observation.ReseparationRecorded
                && observation.AttemptId == Cohort().AttemptId
                && observation.WipeGeneration == Cohort().Raid.WipeGeneration
                && observation.RouteGeneration == Party().ValidationRouteGeneration;
        });
    if (sameSourceRecoveryMissed && Cohort().ValidationAttemptFailureReason.empty())
    {
        // The native 20-second clock is the production deadline. Preserve the
        // new native observation below, but terminal-latch the experiment as
        // soon as the same source begins another Rush before the authoritative
        // head observation has exact-roster closure. This converts an
        // unrecoverable queue into a prompt gameplay failure instead of a
        // telemetry/CPU flood.
        Cohort().ValidationAttemptFailureReason =
            "drudge_reseparation_deadline_missed";
        Cohort().ValidationAttemptFailureAttemptId = Cohort().AttemptId;
        Cohort().ValidationAttemptFailureRouteGeneration =
            Party().ValidationRouteGeneration;
    }
    bool const currentScopeHasChargeObservation = std::any_of(
        Party().ValidationRouteDrudgeChargeObservations.begin(),
        Party().ValidationRouteDrudgeChargeObservations.end(),
        [this](ValidationRouteDrudgeChargeObservation const& observation)
        {
            return observation.AttemptId == Cohort().AttemptId
                && observation.WipeGeneration == Cohort().Raid.WipeGeneration
                && observation.RouteGeneration == Party().ValidationRouteGeneration;
        });
    if (!currentScopeHasChargeObservation)
    {
        using namespace BotRaidDrudgeThreatSeed;
        State seedState;
        seedState.Identity = {
            Party().ValidationRouteDrudgeThreatSeedAttemptId,
            Party().ValidationRouteDrudgeThreatSeedWipeGeneration,
            Party().ValidationRouteDrudgeThreatSeedRouteGeneration
        };
        seedState.Closed = Party().ValidationRouteDrudgeThreatSeedClosed;
        seedState.Complete = Party().ValidationRouteDrudgeThreatSeedComplete;
        seedState.Failure = Party().ValidationRouteDrudgeThreatSeedFailure;
        Scope const currentScope = {
            Cohort().AttemptId,
            Cohort().Raid.WipeGeneration,
            Party().ValidationRouteGeneration
        };
        for (ValidationRouteDrudgeThreatSeedEvidence const& evidence :
            Party().ValidationRouteDrudgeThreatSeedEvidenceRows)
            if (evidence.ActionSucceeded && evidence.ProfileActionValid
                && evidence.AttemptId == currentScope.AttemptId
                && evidence.WipeGeneration == currentScope.WipeGeneration
                && evidence.RouteGeneration == currentScope.RouteGeneration
                && evidence.SourceLane < seedState.SeededLanes.size())
                seedState.SeededLanes[evidence.SourceLane] = true;
        Input rushInput;
        rushInput.Type = Event::FirstNativeRush;
        rushInput.Identity = currentScope;
        Result const transition = Advance(seedState, rushInput);
        if (transition.ScopeReset)
        {
            Party().ValidationRouteDrudgeThreatSeedRosterGuids.clear();
            Party().ValidationRouteDrudgeThreatSeedEvidenceRows.clear();
        }
        Party().ValidationRouteDrudgeThreatSeedAttemptId = transition.Next.Identity.AttemptId;
        Party().ValidationRouteDrudgeThreatSeedWipeGeneration = transition.Next.Identity.WipeGeneration;
        Party().ValidationRouteDrudgeThreatSeedRouteGeneration = transition.Next.Identity.RouteGeneration;
        Party().ValidationRouteDrudgeThreatSeedClosed = transition.Next.Closed;
        Party().ValidationRouteDrudgeThreatSeedComplete = transition.Next.Complete;
        Party().ValidationRouteDrudgeThreatSeedFailure = transition.Next.Failure;
    }

    // Closing the native clock edge cannot depend on evidence eligibility.
    // A Rush aimed at a foreign player or an unexpected non-player is still
    // the first Rush and permanently ends the seed window.  Retain foreign
    // player targets below so acceptance can reject their roster/lane; a
    // non-player target remains fail-closed even though no player-shaped
    // observation can be serialized.
    uint64 const priorMs = Party().ValidationRouteDrudgeLastChargeMsBySpawn[sourceSpawnId];
    Player* targetPlayer = target->ToPlayer();
    if (!targetPlayer || caster->GetMap() != targetPlayer->GetMap())
    {
        Party().ValidationRouteDrudgeLastChargeMsBySpawn[sourceSpawnId] = observedAtMs;
        ++Party().ValidationRouteDrudgeChargePreparedCount;
        return 0;
    }

    // The first cast has no native interval evidence. A later cast is valid
    // only when it is not earlier than the exact declared 20-second cadence;
    // preserve the observed delta rather than inventing a tolerance.
    Party().ValidationRouteDrudgeChargeIntervalValid = priorMs
        && observedAtMs - priorMs >= Cohort().Config.ValidationRouteChargeNativeIntervalMs;
    Party().ValidationRouteDrudgeLastChargeMsBySpawn[sourceSpawnId] = observedAtMs;
    Party().ValidationRouteDrudgeChargeObservedDistance = caster->GetExactDist(targetPlayer);
    Party().ValidationRouteDrudgeChargeRangeValid =
        Party().ValidationRouteDrudgeChargeObservedDistance
            <= Cohort().Config.ValidationRouteChargeRangeYards;
    Party().ValidationRouteDrudgeChargeObservedAtMs = observedAtMs;
    Party().ValidationRouteDrudgeChargeSourceGuid = caster->GetGUID();
    Party().ValidationRouteDrudgeChargeTargetGuid = targetPlayer->GetGUID();
    Party().ValidationRouteDrudgeChargeSourceSpawnId = sourceSpawnId;
    ++Party().ValidationRouteDrudgeChargeGeneration;
    ValidationRouteDrudgeChargeObservation observation;
    observation.Sequence = Party().ValidationRouteDrudgeChargeGeneration;
    observation.AttemptId = Cohort().AttemptId;
    observation.WipeGeneration = Cohort().Raid.WipeGeneration;
    observation.RouteGeneration = Party().ValidationRouteGeneration;
    observation.ObservedAtMs = observedAtMs;
    observation.ObservedIntervalMs = priorMs ? observedAtMs - priorMs : 0;
    observation.SourceGuid = caster->GetGUID();
    observation.TargetGuid = targetPlayer->GetGUID();
    observation.TargetRawGuid = targetPlayer->GetGUID().GetRawValue();
    observation.SourceSpawnId = sourceSpawnId;
    observation.SelectedDistance = Party().ValidationRouteDrudgeChargeObservedDistance;
    observation.SourceCombatReach = caster->GetCombatReach();
    observation.TargetCombatReach = targetPlayer->GetCombatReach();
    observation.SameMap = caster->IsInMap(targetPlayer);
    observation.SamePhase = caster->IsInPhase(targetPlayer);
    observation.RangeValid = caster->IsWithinCombatRange(
        targetPlayer, Cohort().Config.ValidationRouteChargeRangeYards);
    Party().ValidationRouteDrudgeChargeRangeValid = observation.RangeValid;
    observation.IntervalValid = Party().ValidationRouteDrudgeChargeIntervalValid;
    // Capture the native threat list only on each source's first Rush edge.
    // This is bounded evidence for the selector's real candidate set; it does
    // not add threat, rewrite the spell target, or otherwise affect native
    // combat behavior.
    if (!priorMs)
    {
        static constexpr size_t MaxNativeThreatCandidates = 32;
        uint32 const sourceLaneIndex = sourceSpawnId
            == Cohort().Config.ValidationRouteSplitSourceGuids[0] ? 0 : 1;
        auto const& nativeThreatList = caster->GetThreatManager().GetUnsortedThreatList();
        size_t nativeThreatCandidateCount = 0;
        for (ThreatReference const* reference : nativeThreatList)
            if (reference && reference->GetVictim())
                ++nativeThreatCandidateCount;
        observation.NativeThreatCandidatesCount = uint32(std::min<size_t>(
            nativeThreatCandidateCount, std::numeric_limits<uint32>::max()));
        observation.NativeThreatCandidatesComplete = nativeThreatCandidateCount
            <= MaxNativeThreatCandidates;
        observation.NativeThreatCandidatesTruncated = nativeThreatCandidateCount
            > MaxNativeThreatCandidates;
        for (ThreatReference const* reference : nativeThreatList)
        {
            if (!reference || !reference->GetVictim())
                continue;

            Unit* candidate = reference->GetVictim();
            ValidationRouteDrudgeThreatCandidateEvidence candidateEvidence;
            candidateEvidence.Guid = candidate->GetGUID().GetCounter();
            candidateEvidence.RawGuid = candidate->GetGUID().GetRawValue();
            candidateEvidence.Threat = reference->GetThreat();
            candidateEvidence.Distance = caster->GetExactDist(candidate);
            candidateEvidence.SourceCombatReach = caster->GetCombatReach();
            candidateEvidence.CandidateCombatReach = candidate->GetCombatReach();
            candidateEvidence.IsPlayer = candidate->ToPlayer() != nullptr;
            candidateEvidence.Alive = candidate->IsAlive();
            candidateEvidence.SameMap = caster->IsInMap(candidate);
            candidateEvidence.SamePhase = caster->IsInPhase(candidate);
            candidateEvidence.Available = reference->IsAvailable();
            candidateEvidence.LineOfSight = caster->IsWithinLOSInMap(candidate);
            candidateEvidence.InRange = candidateEvidence.Distance
                <= Cohort().Config.ValidationRouteChargeRangeYards;
            candidateEvidence.NativeCombatRange = caster->IsWithinCombatRange(
                candidate, Cohort().Config.ValidationRouteChargeRangeYards);
            candidateEvidence.Role = "unregistered";
            bool registered = false;
            bool crossLane = false;
            bool activeLease = false;
            if (Player* candidatePlayer = candidate->ToPlayer())
            {
                auto candidateRoster = Cohort().Raid.RosterByGuid.find(
                    candidatePlayer->GetGUID().GetCounter());
                if (candidateRoster != Cohort().Raid.RosterByGuid.end())
                {
                    registered = true;
                    candidateEvidence.Role = candidateRoster->second.Role;
                    candidateEvidence.Slot = candidateRoster->second.SlotIndex + 1;
                    bool const candidateLaneA = std::find(
                        Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
                        Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(),
                        candidateEvidence.Slot)
                        != Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
                    candidateEvidence.Lane = candidateLaneA ? 0 : 1;
                    crossLane = candidateEvidence.Lane != sourceLaneIndex;
                    activeLease = candidateRoster->second.Active
                        && candidateRoster->second.LeaseOwned;
                }
            }
            candidateEvidence.CrossLane = crossLane;
            // SMART_TARGET_FARTHEST with playerOnly=1, range=80 and LOS=1
            // chooses from available player threat references regardless of
            // raid role or lane. Keep that native predicate distinct from the
            // tactic's desired cross-lane non-tank seed/selection predicate.
            candidateEvidence.NativeSelectorEligible = candidateEvidence.IsPlayer
                && candidateEvidence.Available && candidateEvidence.LineOfSight
                && candidateEvidence.NativeCombatRange;
            candidateEvidence.TacticCrossLaneEligible =
                candidateEvidence.NativeSelectorEligible && registered && activeLease
                && candidate->IsAlive() && candidate->GetMap() == caster->GetMap()
                && candidateEvidence.CrossLane && candidateEvidence.Role != "tank";
            observation.NativeThreatCandidates.push_back(std::move(candidateEvidence));
            if (observation.NativeThreatCandidates.size() >= MaxNativeThreatCandidates)
                break;
        }
    }
    ++Party().ValidationRouteDrudgeChargePreparedCount;
    if (Party().ValidationRouteDrudgeChargeObservations.size() >= 32)
    {
        Party().ValidationRouteDrudgeChargeQueueOverflow = true;
        Party().ValidationRouteDrudgeChargeObservations.pop_front();
    }
    Party().ValidationRouteDrudgeChargeObservations.push_back(std::move(observation));
    return Party().ValidationRouteDrudgeChargeGeneration;
}

void BotWorldPopulationMgr::NotifyNativeCreatureSpellLanded(
    Creature* caster, Unit* target, uint32 spellId, uint64 observationSequence)
{
    if (!Cohort().Active || !caster || !target || !observationSequence
        || Cohort().Config.ValidationRouteMechanicProfile != "trash_two_tank_charge_lanes"
        || spellId != Cohort().Config.ValidationRouteChargeSpellId)
        return;

    auto observation = std::find_if(
        Party().ValidationRouteDrudgeChargeObservations.begin(),
        Party().ValidationRouteDrudgeChargeObservations.end(),
        [this, caster, target, observationSequence](ValidationRouteDrudgeChargeObservation const& candidate)
        {
            return candidate.Sequence == observationSequence
                && !candidate.Landed
                && candidate.AttemptId == Cohort().AttemptId
                && candidate.WipeGeneration == Cohort().Raid.WipeGeneration
                && candidate.RouteGeneration == Party().ValidationRouteGeneration
                && candidate.SourceGuid == caster->GetGUID()
                && candidate.TargetGuid == target->GetGUID();
        });
    if (observation == Party().ValidationRouteDrudgeChargeObservations.end())
        return;

    observation->Landed = true;
    Party().ValidationRouteDrudgeChargeLandedGeneration = observation->Sequence;
    ++Party().ValidationRouteDrudgeChargeDeliveredCount;
    ++Party().ValidationRouteDrudgeDeliveredBySpawn[observation->SourceSpawnId];
    if (observation->IntervalValid && observation->ObservedIntervalMs > 0)
        ++Party().ValidationRouteDrudgeValidIntervalsBySpawn[observation->SourceSpawnId];
}

