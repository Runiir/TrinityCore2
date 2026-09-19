#ifndef TRINITY_SPELL_NATIVE_CAST_OBSERVATION_H
#define TRINITY_SPELL_NATIVE_CAST_OBSERVATION_H

#include "ObjectGuid.h"

#include <atomic>
#include <cstdint>
#include <limits>
#include <string>

inline std::uint64_t NextNativeSpellCastInstanceId()
{
    static std::atomic<std::uint64_t> sequence{0};
    std::uint64_t const value = ++sequence;
    return value ? value : ++sequence;
}

// Value-only facts retained by one Spell.  This is deliberately not a live
// registry: the Spell owns the identity until the existing finish callback
// serializes it into the bounded decision trace.
struct SpellNativeCastObservation
{
    std::uint64_t InstanceId = NextNativeSpellCastInstanceId();
    std::uint32_t SpellId = 0;
    ObjectGuid CasterGuid;
    ObjectGuid OriginalCasterGuid;
    ObjectGuid SubmittedTargetGuid;
    ObjectGuid TerminalTargetGuid;
    bool Prepared = false;
    std::uint64_t PreparedAtMs = 0;
    std::string SourceScopeJson;
    bool NativeFailureResultAvailable = false;
    std::uint32_t LastNativeFailureResult = 0;
    bool MovementCheckAvailable = false;
    std::uint32_t MovementCheckResult = 0;
    std::string TerminalSource = "unknown";
    std::string CancellationOwner = "unknown";
    bool CancellationOwnerAvailable = false;
    bool TerminalTargetPresenceAvailable = false;
    bool TerminalTargetAliveAvailable = false;
    bool TerminalTargetAttackabilityAvailable = false;
    bool TerminalTargetPresent = false;
    bool TerminalTargetAlive = false;
    bool TerminalTargetAttackable = false;
    std::uint32_t PriorState = 0;
    bool FinishingObserved = false;
    bool Finished = false;
    bool Success = false;
    std::uint32_t TerminalOrdinal = 0;
    std::uint64_t FinishedAtMs = 0;
    std::string TerminalScopeJson;
};

namespace SpellNativeCastObservationOps
{
void SetSubmittedTarget(SpellNativeCastObservation& observation,
    ObjectGuid submittedTargetGuid);
void MarkPrepared(SpellNativeCastObservation& observation,
    std::string sourceScopeJson, std::uint64_t observedAtMs);
void RecordResult(SpellNativeCastObservation& observation,
    std::uint32_t result, std::uint32_t successResult);
void MarkUpdate(SpellNativeCastObservation& observation, char const* source,
    std::uint32_t movementResult);
void MarkCancelled(SpellNativeCastObservation& observation);
void MarkFinishing(SpellNativeCastObservation& observation, bool success,
    ObjectGuid terminalTargetGuid, bool terminalTargetPresent,
    bool terminalTargetAliveAvailable, bool terminalTargetAlive,
    bool terminalTargetAttackabilityAvailable, bool terminalTargetAttackable,
    std::uint32_t priorState, std::string terminalScopeJson,
    std::uint64_t observedAtMs);
}

#endif
