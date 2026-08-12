from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = (ROOT / "src/server/game/Bots/BotRaidAreaAuthority.h").read_text(encoding="utf-8")
PET_AI = (ROOT / "src/server/game/AI/CoreAI/PetAI.cpp").read_text(encoding="utf-8")
EXECUTOR = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text(encoding="utf-8")
RUNTIME = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")


def test_raid_area_authority_is_transient_and_pet_ai_enforced():
    assert "inline std::unordered_set<uint64> SuppressedOwners" in AUTHORITY
    assert "BotRaidAreaAuthority::IsSuppressed(owner->GetGUID().GetRawValue())" in PET_AI
    assert "SpellHasHostileMultiTargetSemantics(spellInfo)" in PET_AI
    assert "BotRaidAreaAuthority::Set(bot->GetGUID().GetRawValue(), action.SuppressAreaDamage);" in EXECUTOR
    assert "BotRaidAreaAuthority::Set(state.Guid.GetRawValue(), false);" in RUNTIME
    assert "ToggleAutocast" not in PET_AI


def test_pet_ai_authority_does_not_mutate_persistent_pet_spell_state():
    marker = "BotRaidAreaAuthority::IsSuppressed(owner->GetGUID().GetRawValue())"
    authority_block = PET_AI[
        PET_AI.index(marker) - 80:
        PET_AI.index(marker) + 180
    ]
    assert "continue;" in authority_block
    assert "SetSpellAutocast" not in authority_block
    assert "ToggleCreatureAutocast" not in authority_block
    assert "ToggleAutocast" not in authority_block
