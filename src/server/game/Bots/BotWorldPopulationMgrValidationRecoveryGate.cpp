#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotRaidAreaAuthority.h"

#include "Creature.h"
#include "GameTime.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <cstdint>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

bool BotWorldPopulationMgr::IsImmediateNextValidationRouteBossTarget(Creature const* creature) const
{
    if (!creature || Cohort().Config.ValidationRouteKind == "boss")
        return false;

    size_t nextIndex = Party().ValidationRouteManifestIndex + 1;
    if (nextIndex >= Party().ValidationRouteManifest.size())
        return false;

    ValidationRouteManifestNode const& nextNode = Party().ValidationRouteManifest[nextIndex];
    if (nextNode.Kind != "boss")
        return false;

    uint32 entry = creature->GetEntry();
    return entry == nextNode.TargetEntry
        || entry == nextNode.OpenerTargetEntry
        || std::find(nextNode.AlternateTargetEntries.begin(),
            nextNode.AlternateTargetEntries.end(), entry)
            != nextNode.AlternateTargetEntries.end();
}

bool BotWorldPopulationMgr::IsImmediateNextValidationRouteEncounterMember(Creature const* creature) const
{
    if (!creature || Cohort().Config.ValidationRouteKind == "boss")
        return false;

    size_t nextIndex = Party().ValidationRouteManifestIndex + 1;
    if (nextIndex >= Party().ValidationRouteManifest.size())
        return false;
    uint32 const entry = creature->GetEntry();
    bool nextEntry = false;
    bool nextSpawn = false;
    // The current non-boss node owns the whole remainder of the route.  A
    // visible later trash pack or boss must not be pulled by a direct cast,
    // auto-attack, pet, multidot/AoE candidate, or range chase.  Keep this
    // identity check manifest-owned instead of adding encounter-specific
    // exceptions for Magmaw or any other boss two nodes ahead.
    for (size_t routeIndex = nextIndex;
        routeIndex < Party().ValidationRouteManifest.size(); ++routeIndex)
    {
        ValidationRouteManifestNode const& nextNode =
            Party().ValidationRouteManifest[routeIndex];
        if (nextNode.Kind != "boss" && nextNode.Kind != "trash")
            continue;

        nextEntry = nextEntry || entry == nextNode.TargetEntry
            || entry == nextNode.OpenerTargetEntry
            || std::find(nextNode.TargetEntries.begin(), nextNode.TargetEntries.end(), entry)
                != nextNode.TargetEntries.end()
            || std::find(nextNode.AlternateTargetEntries.begin(),
                nextNode.AlternateTargetEntries.end(), entry)
                != nextNode.AlternateTargetEntries.end()
            || std::find(nextNode.AddTargetEntries.begin(),
                nextNode.AddTargetEntries.end(), entry)
                != nextNode.AddTargetEntries.end()
            || std::find(nextNode.PackTargetEntries.begin(),
                nextNode.PackTargetEntries.end(), entry)
                != nextNode.PackTargetEntries.end()
            || std::find(nextNode.ScriptedEventEntries.begin(),
                nextNode.ScriptedEventEntries.end(), entry)
                != nextNode.ScriptedEventEntries.end();
        uint32 const spawnId = creature->GetSpawnId();
        nextSpawn = nextSpawn || (nextNode.TargetSpawnId && spawnId == nextNode.TargetSpawnId)
            || std::find(nextNode.SplitSourceGuids.begin(),
                nextNode.SplitSourceGuids.end(), spawnId)
                != nextNode.SplitSourceGuids.end();
    }

    // A live member already enrolled in the current route generation is
    // authoritative even when the current and next nodes reuse an entry or a
    // spawn family. Death and transition ledgers are excluded above, so stale
    // members cannot use this exception to punch through the future guard.
    bool const persistedCurrentMember =
        Party().ValidationRoutePackGeneration == Party().ValidationRouteGeneration
        && Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())
            != Party().ValidationRoutePackMemberGuids.end()
        && Party().ValidationRoutePackDeathGuids.find(creature->GetGUID())
            == Party().ValidationRoutePackDeathGuids.end()
        && Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID())
            == Party().ValidationRoutePackTransitionGuids.end();
    if (persistedCurrentMember)
        return false;
    return nextEntry || nextSpawn;
}

bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending() const
{
    RaidRuntime const& raid = Cohort().Raid;
    if (Cohort().Config.ValidationRouteBossRecovery != ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
        || !raid.Active
        || raid.AttemptId != Cohort().AttemptId
        || !raid.NativeRecoveryHoldActive
        || raid.NativeRecoveryRouteGeneration != Party().ValidationRouteGeneration
        || raid.NativeRecoveryNodeId != Cohort().Config.ValidationRouteNodeId
        || !raid.WipeGeneration)
        return false;

    // NativeRecoveryHoldActive is latched by the exact native all-dead edge
    // and remains authoritative through the first post-resurrection tick.
    // Do not let a transiently incomplete roster or a stale WipeState clear
    // the owner/pet/controlled-unit and route gate before the current wipe's
    // ready-check-backed evidence has been refreshed.
    return !raid.NativeRecoveryEvidenceComplete;
}

void BotWorldPopulationMgr::SuppressNativeRaidRecovery(WorldBotState& state, Player* bot)
{
    if (!bot)
        return;

    uint64 const nowMs = NowMs();
    uint32 const wipeGeneration = Cohort().Raid.WipeGeneration;
    bool const newHold = state.NativeRecoveryHoldWipeGeneration != wipeGeneration;
    bool const periodicVerify = !state.NativeRecoveryHoldLastEnforcedMs
        || nowMs - state.NativeRecoveryHoldLastEnforcedMs >= 1000;
    bool const ownerActive = bot->IsInCombat() || bot->GetVictim()
        || bot->HasUnitState(UNIT_STATE_CASTING | UNIT_STATE_MOVING)
        || bot->GetCurrentSpell(CURRENT_GENERIC_SPELL)
        || bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL)
        || bot->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL);
    auto controlledActive = [](Unit* controlled) -> bool
    {
        return controlled && (controlled->IsInCombat() || controlled->GetVictim()
            || controlled->HasUnitState(UNIT_STATE_CASTING | UNIT_STATE_MOVING)
            || controlled->GetCurrentSpell(CURRENT_GENERIC_SPELL)
            || controlled->GetCurrentSpell(CURRENT_CHANNELED_SPELL)
            || controlled->GetCurrentSpell(CURRENT_AUTOREPEAT_SPELL));
    };
    bool controlledUnitActive = controlledActive(bot->GetPet());
    if (!controlledUnitActive)
        controlledUnitActive = std::any_of(bot->m_Controlled.begin(), bot->m_Controlled.end(), controlledActive);
    uint64 const ownerGuid = bot->GetGUID().GetRawValue();
    if (newHold || periodicVerify)
    {
        BotRaidAreaAuthority::SetAllOffenseSuppressed(ownerGuid, true);
        BotRaidAreaAuthority::Set(ownerGuid, true);
    }
    if (!newHold && !periodicVerify && !ownerActive && !controlledUnitActive)
        return;

    state.NativeRecoveryHoldWipeGeneration = wipeGeneration;
    state.NativeRecoveryHoldLastEnforcedMs = nowMs;

    // Do not force combat state, interrupt native casts, change motion, or
    // mutate controlled units during certification recovery. The authority
    // gates prevent new bot offense; native encounter reset must clear any old
    // activity, and the ready-check predicate independently observes that it
    // did.
    state.ActivePathValid = false;
    state.IsMoving = false;
    state.TargetGuid.Clear();
    state.LastRecoveryMode = "native_full_wipe_only";
    state.LastRecoveryResult = "native_recovery_evidence_pending";
    state.LastNoProgressReason = "native_recovery_evidence_pending";
}
