#include "Spell.h"

#include "Unit.h"

#include "SpellNativeCastObservation.h"

#include <utility>

void Spell::ObserveNativeCastSubmittedTarget(ObjectGuid submittedTargetGuid)
{
    SpellNativeCastObservationOps::SetSubmittedTarget(
        m_nativeCastObservation, submittedTargetGuid);
}

void Spell::ObserveNativeCastPrepared(std::string sourceScopeJson,
    uint64 observedAtMs)
{
    SpellNativeCastObservationOps::MarkPrepared(
        m_nativeCastObservation, std::move(sourceScopeJson), observedAtMs);
}

void Spell::ObserveNativeCastResult(uint32 result) const
{
    SpellNativeCastObservationOps::RecordResult(
        m_nativeCastObservation, result, uint32(SPELL_CAST_OK));
}

void Spell::ObserveNativeCastUpdate(char const* source, uint32 movementResult)
{
    SpellNativeCastObservationOps::MarkUpdate(
        m_nativeCastObservation, source, movementResult);
}

void Spell::ObserveNativeCastCancelled()
{
    SpellNativeCastObservationOps::MarkCancelled(m_nativeCastObservation);
}

void Spell::ObserveNativeCastFinishing(bool success,
    std::string terminalScopeJson, uint64 observedAtMs)
{
    Unit* terminalTarget = m_targets.GetUnitTarget();
    bool const targetAliveAvailable = terminalTarget != nullptr;
    bool const targetAttackabilityAvailable = terminalTarget != nullptr
        && m_caster != nullptr;
    bool const targetAlive = targetAliveAvailable && terminalTarget->IsAlive();
    bool const targetAttackable = targetAttackabilityAvailable
        && m_caster->IsValidAttackTarget(terminalTarget, m_spellInfo);
    SpellNativeCastObservationOps::MarkFinishing(
        m_nativeCastObservation, success, m_targets.GetUnitTargetGUID(),
        terminalTarget != nullptr, targetAliveAvailable, targetAlive,
        targetAttackabilityAvailable, targetAttackable,
        uint32(m_spellState), std::move(terminalScopeJson), observedAtMs);
}
