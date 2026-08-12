from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIT = (ROOT / "src/server/game/Entities/Unit/Unit.h").read_text(encoding="utf-8")
PET_AI = (ROOT / "src/server/game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
EXECUTOR = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text(encoding="utf-8")


def test_raid_area_authority_is_transient_and_pet_ai_enforced():
    assert "m_hostileMultiTargetAutocastSuppressed = false" in UNIT
    assert "SetHostileMultiTargetAutocastSuppressed" in UNIT
    assert "IsHostileMultiTargetAutocastSuppressed" in UNIT
    assert "owner->IsHostileMultiTargetAutocastSuppressed()" in PET_AI
    assert "SpellHasHostileMultiTargetSemantics(spellInfo)" in PET_AI
    assert "bot->SetHostileMultiTargetAutocastSuppressed(action.SuppressAreaDamage);" in EXECUTOR
    assert "ToggleAutocast" not in PET_AI


def test_pet_ai_authority_does_not_mutate_persistent_pet_spell_state():
    authority_block = PET_AI[
        PET_AI.index("owner->IsHostileMultiTargetAutocastSuppressed()") - 80:
        PET_AI.index("owner->IsHostileMultiTargetAutocastSuppressed()") + 180
    ]
    assert "continue;" in authority_block
    assert "SetSpellAutocast" not in authority_block
    assert "ToggleCreatureAutocast" not in authority_block
    assert "ToggleAutocast" not in authority_block
