#include "Spell.h"

#include "ObjectAccessor.h"
#include "Unit.h"

#include "SpellNativeCastObservation.h"

#include <utility>

namespace
{
// The terminal target of a finishing cast, looked up by GUID in the caster's
// map. SpellCastTargets' cached object pointer is refreshed only by
// Spell::UpdatePointers() (update, cast, delayed handling); a cancel or finish
// reached synchronously from another object's teardown runs without it, after
// the target may already have been deleted. `.botauto stop` logs a cohort's
// bots out in roster order: in the round-4 six-shard batch the disc priest's
// Heal (2050) on the holy paladin (logged out and deleted one bot earlier) was
// cancelled by the priest's CombatStop, and the attackability probe below
// reached CanSeeOrDetect -> IsNeverVisible() through the destroyed Player
// (SIGSEGV executing libstdc++'s __si_class_type_info vtable).
//
// terminal_target_present (native_spell_finish_v2) therefore means "in the
// world in the caster's map, or the caster itself": a creature already on its
// map's remove list or a player in far-teleport transit or on another map is
// reported absent. That is stricter than the bot decision helper
// BotSpellCastTarget::UnitTarget, which still returns such live units; alive
// and attackable are only probed on an in-world target in the caster's map.
Unit* NativeCastTerminalTarget(WorldObject* caster, ObjectGuid const& targetGuid)
{
    if (!caster || targetGuid.IsEmpty())
        return nullptr;
    if (targetGuid == caster->GetGUID())
        return caster->ToUnit();
    // ObjectAccessor reads the caster's map; a caster outside the world has
    // no map to resolve a live target in.
    if (!caster->IsInWorld())
        return nullptr;
    return ObjectAccessor::GetUnit(*caster, targetGuid);
}
}

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
    // Never m_targets.GetUnitTarget(): see NativeCastTerminalTarget.
    ObjectGuid const terminalTargetGuid = m_targets.GetUnitTargetGUID();
    Unit* terminalTarget = NativeCastTerminalTarget(m_caster, terminalTargetGuid);
    bool const targetAliveAvailable = terminalTarget != nullptr;
    bool const targetAttackabilityAvailable = terminalTarget != nullptr
        && m_caster != nullptr;
    bool const targetAlive = targetAliveAvailable && terminalTarget->IsAlive();
    bool const targetAttackable = targetAttackabilityAvailable
        && m_caster->IsValidAttackTarget(terminalTarget, m_spellInfo);
    SpellNativeCastObservationOps::MarkFinishing(
        m_nativeCastObservation, success, terminalTargetGuid,
        terminalTarget != nullptr, targetAliveAvailable, targetAlive,
        targetAttackabilityAvailable, targetAttackable,
        uint32(m_spellState), std::move(terminalScopeJson), observedAtMs);
}
