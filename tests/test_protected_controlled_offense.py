from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PET_AI = (ROOT / "src/server/game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
UNIT_AI = (ROOT / "src/server/game/AI/CoreAI/UnitAI.cpp").read_text(encoding="utf-8")
UNIT = (ROOT / "src/server/game/Entities/Unit/Unit.cpp").read_text(encoding="utf-8")
AUTHORITY = (ROOT / "src/server/game/Bots/BotRaidAreaAuthority.h").read_text(encoding="utf-8")


def _offensive_target_rejected(*, all_suppressed, entry, spawn_id, raw_guid,
                               protected_entries, protected_spawns, allowed_guids):
    """Executable model of the owner-scoped route authority contract."""
    if all_suppressed:
        return True
    if raw_guid in allowed_guids:
        return False
    return entry in protected_entries or spawn_id in protected_spawns


def test_sustained_authority_blocks_acquired_future_target_but_keeps_current_target():
    # Model the exact regression: the pet/controlled unit acquired current
    # Chainwielder GUID 27 before future Drudges became visible, then the
    # route authority protected the next node while the victim pointer stayed
    # live.
    kwargs = dict(
        protected_entries={42362},
        protected_spawns={250140, 250141},
        allowed_guids={27},
    )
    assert not _offensive_target_rejected(
        all_suppressed=False, entry=42649, spawn_id=250050, raw_guid=27, **kwargs
    )
    assert _offensive_target_rejected(
        all_suppressed=False, entry=42362, spawn_id=250140, raw_guid=59, **kwargs
    )
    assert _offensive_target_rejected(
        all_suppressed=True, entry=42649, spawn_id=250050, raw_guid=27, **kwargs
    )


def test_pet_loop_rechecks_acquired_victim_and_preserves_positive_support():
    need_to_stop = PET_AI[PET_AI.index("bool PetAI::_needToStop"):
                         PET_AI.index("void PetAI::_stopAttack")]
    update = PET_AI[PET_AI.index("void PetAI::UpdateAI"):
                    PET_AI.index("void PetAI::UpdateAllies")]

    assert "ProtectedEncounterTarget(me->GetCharmerOrOwner(), me->GetVictim())" in need_to_stop
    assert "if (_needToStop())" in update
    assert "DoMeleeAttackIfReady();" in update
    assert "offenseSuppressed && !spellInfo->IsPositive()" in update
    assert "if (owner && offenseSuppressed && !spellInfo->IsPositive())" in update
    # The full-offense hold must not leave the pet permanently passive or
    # turn positive autocasts into a blocked path.
    assert "SetReactState(REACT_PASSIVE)" not in update
    assert update.index("offenseSuppressed && !spellInfo->IsPositive()") < update.index("if (spellInfo->IsPositive())")


def test_controlled_melee_and_spell_attack_recheck_at_submission():
    melee = UNIT_AI[UNIT_AI.index("void UnitAI::DoMeleeAttackIfReady"):
                    UNIT_AI.index("bool UnitAI::DoSpellAttackIfReady")]
    spell_attack = UNIT_AI[UNIT_AI.index("bool UnitAI::DoSpellAttackIfReady"):
                           UNIT_AI.index("Unit* UnitAI::SelectTarget")]

    assert "RaidControlledOffenseRejected(me, victim)" in melee
    assert "me->AttackStop();" in melee
    assert "RaidControlledOffenseRejected(me, me->GetVictim())" in spell_attack
    assert "me->AttackStop();" in spell_attack


def test_shared_damage_and_autorepeat_sinks_are_fail_closed():
    attacker = UNIT[UNIT.index("void Unit::AttackerStateUpdate"):
                    UNIT.index("void Unit::HandleProcExtraAttackFor")]
    autorepeat = UNIT[UNIT.index("void Unit::_UpdateAutoRepeatSpell"):
                      UNIT.index("void Unit::SetCurrentCastSpell")]

    assert "RaidControlledUnitOffenseRejected(this, victim)" in attacker
    assert attacker.count("RaidControlledUnitOffenseRejected(this, victim)") == 2
    assert "GetMeleeHitRedirectTarget(victim)" in attacker
    assert "m_targets.GetUnitTarget()" in autorepeat
    assert "InterruptSpell(CURRENT_AUTOREPEAT_SPELL" in autorepeat
    assert autorepeat.index("if (RaidControlledUnitOffenseRejected") < autorepeat.index(
        "m_currentSpells[CURRENT_AUTOREPEAT_SPELL]->CheckCast"
    )

    # Authority is owner-scoped and the identity override still permits the
    # current node's live target rather than suppressing all controlled damage.
    assert "AllowedEncounterGuidsByOwner" in AUTHORITY
    assert "BotRaidAreaAuthority::Clear(GetGUID().GetRawValue())" in UNIT
    assert "if (IsPlayer())" in UNIT[UNIT.index("void Unit::RemoveFromWorld"):
                                      UNIT.index("void Unit::CleanupBeforeRemoveFromMap")]
