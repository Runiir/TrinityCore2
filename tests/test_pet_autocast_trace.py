from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PET_AI = (ROOT / "src/server/game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
PET_AI_HEADER = (ROOT / "src/server/game/AI/CoreAI/PetAI.h").read_text(encoding="utf-8")
PET = (ROOT / "src/server/game/Entities/Pet/Pet.cpp").read_text(encoding="utf-8")
PET_COMBAT = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrAfflictionPetCombat.cpp").read_text(encoding="utf-8")
COMBAT_DIAGNOSTICS = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatDiagnostics.cpp").read_text(encoding="utf-8")


def _project_pet_current_generic_spell_id(pet_observation: dict) -> int:
    """Model the final pet telemetry projection from a current Spell object."""

    current_spell = pet_observation.get("current_spell")
    if not current_spell or current_spell["state"] == "finished":
        return 0
    return current_spell["id"]


def test_pet_autocast_trace_is_at_native_selection_seam_and_identifies_spell():
    selection = PET_AI[PET_AI.index("if (!targetSpellStore.empty())") : PET_AI.index("void PetAI::UpdateAllies")]

    assert "spell->GetSpellInfo()" in selection
    assert "selectedSpellInfo->Id" in selection
    assert "selectedSpellInfo->SpellName" in selection
    assert "target->HasAura(selectedSpellInfo->Id)" in selection
    assert 'TC_LOG_TRACE("entities.pet.autocast"' in selection
    assert "spell->prepare(targets);" in selection


def test_pet_autocast_trace_is_rate_limited_without_changing_autocast_state():
    assert "TimeTracker m_autocastTraceTimer;" in PET_AI_HEADER
    assert "m_autocastTraceTimer.Update(diff);" in PET_AI
    assert "m_autocastTraceTimer.Passed()" in PET_AI
    assert "m_autocastTraceTimer.Reset(PET_AUTOCAST_TRACE_INTERVAL)" in PET_AI
    assert "constexpr uint32 PET_AUTOCAST_TRACE_INTERVAL = 1 * IN_MILLISECONDS;" in PET_AI

    trace = PET_AI[PET_AI.index('TC_LOG_TRACE("entities.pet.autocast"') : PET_AI.index("targetSpellStore.erase(it)")]
    assert "ToggleAutocast" not in trace
    assert "SetSpellAutocast" not in trace
    assert "AddAura" not in trace
    assert "CastSpell" not in trace


def test_felhunter_autocasts_are_native_once_and_owner_submits_attack_only():
    add_spell = PET[PET.index("bool Pet::addSpell") : PET.index("bool Pet::learnSpell")]
    toggle = PET[PET.index("void Pet::ToggleAutocast") : PET.index("bool Pet::IsPermanentPetFor")]
    # The two addSpell paths are new-entry setup and restoration of an already
    # loaded enabled entry. Both converge on ToggleAutocast's duplicate guard;
    # neither is a per-tick bot action.
    assert add_spell.count("ToggleAutocast(spellInfo, true)") == 2
    assert "m_spells[spellId] = newspell;" in add_spell
    assert "if (i == m_autospells.size())" in toggle
    assert toggle.count("m_autospells.push_back(spellid)") == 1

    for spell_id in (77645, 80174, 54049, 54424):
        assert str(spell_id) not in PET_COMBAT
    assert "BotNativeAction::PetCommand" in PET_COMBAT
    assert "COMMAND_ATTACK" in PET_COMBAT
    assert "CastSpell" not in PET_COMBAT
    assert "SetSpellAutocast" not in PET_COMBAT
    assert "ToggleAutocast" not in PET_COMBAT

    assert '\\"pet\\":{\\"guid\\":' in COMBAT_DIAGNOSTICS
    assert '\\"current_generic_spell_id\\"' in COMBAT_DIAGNOSTICS
    assert '\\"victim_guid\\"' in COMBAT_DIAGNOSTICS
    assert "GetCurrentSpell(CURRENT_GENERIC_SPELL)" in COMBAT_DIAGNOSTICS


def test_canary120_felhunter_finished_slot_is_not_reported_as_current_cast():
    # The report's 58 observations all identify the same pet (entry 417,
    # guid 2), with 54424 persisted beside victims 0/27/39/76.  The core
    # Spell object supplies the state that distinguishes a stale slot from a
    # live cast; this is the exact object-to-JSON boundary being exercised.
    finished_observations = [
        {
            "guid": 2,
            "entry": 417,
            "victim_guid": victim_guid,
            "current_spell": {"id": 54424, "state": "finished"},
        }
        for victim_guid in (0, 27, 39, 76)
    ]
    live_cast = {
        "guid": 2,
        "entry": 417,
        "victim_guid": 39,
        "current_spell": {"id": 54049, "state": "preparing"},
    }

    assert all(
        _project_pet_current_generic_spell_id(observation) == 0
        for observation in finished_observations
    )
    assert _project_pet_current_generic_spell_id(live_cast) == 54049

    telemetry_read = COMBAT_DIAGNOSTICS[
        COMBAT_DIAGNOSTICS.index("GetCurrentSpell(CURRENT_GENERIC_SPELL)") :
    ]
    assert "current->getState() != SPELL_STATE_FINISHED" in telemetry_read
