from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPELL_INFO = ROOT / "src/server/game/Spells/SpellInfo.h"
UNIT = ROOT / "src/server/game/Entities/Unit/Unit.cpp"
SPELL_MGR = ROOT / "src/server/game/Spells/SpellMgr.cpp"


def _magic_critical_damage(base_damage: int, multiplier: float) -> int:
    return base_damage + int(float(base_damage) * (multiplier - 1.0))


def test_shadow_bite_uses_two_x_crit_without_changing_normal_magic_crits() -> None:
    spell_info = SPELL_INFO.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")
    spell_mgr = SPELL_MGR.read_text(encoding="utf-8")

    assert "float CritDamageMultiplier = 1.5f;" in spell_info
    assert "if (spellProto->CritDamageMultiplier == 1.5f)" in unit
    assert "crit_bonus += damage / 2;" in unit
    assert "crit_bonus += uint32(float(damage) * (spellProto->CritDamageMultiplier - 1.0f));" in unit

    shadow_bite = spell_mgr[spell_mgr.index("ApplySpellFix({ 54049 }") :]
    shadow_bite = shadow_bite[: shadow_bite.index("    });") + len("    });")]
    assert "spellInfo->CritDamageMultiplier = 2.0f;" in shadow_bite
    assert "DmgClass" not in shadow_bite

    base_damage = 100
    assert _magic_critical_damage(base_damage, 1.5) == 150
    assert _magic_critical_damage(base_damage, 2.0) == 200
