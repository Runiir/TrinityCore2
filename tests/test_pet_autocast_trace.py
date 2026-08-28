from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PET_AI = (ROOT / "src/server/game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
PET_AI_HEADER = (ROOT / "src/server/game/AI/CoreAI/PetAI.h").read_text(encoding="utf-8")


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
