"""A native CastSpell intent casts only a spell the bot actively knows (round 4).

Server-side WorldObject::CastSpell -> Spell::prepare -> Spell::CheckCast has
no spellbook check; only the client opcode path does
(Unit::ProcessPendingSpellCastRequest: Player::HasActiveSpell unless
SPELL_ATTR8_SKIP_IS_KNOWN_CHECK). Encounter duties submit class spells through
BotNativeAction::CastSpell (Chimaeron lust/taunts/support, Nefarian taunts,
Atramedes self casts); the executor now applies the client's rule to all of them.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"
UNIT = ROOT / "src/server/game/Entities/Unit/Unit.cpp"


def test_native_cast_intent_mirrors_the_client_known_spell_rule() -> None:
    source = NATIVE.read_text(encoding="utf-8")
    branch = source[source.index("else if constexpr (std::is_same_v<T, BotNativeAction::CastSpell>)"):]
    branch = branch[:branch.index("else if constexpr", 10)]
    guard = branch.index("!bot->HasActiveSpell(action.SpellId)")
    assert "!resolved.Requested->HasAttribute(SPELL_ATTR8_SKIP_IS_KNOWN_CHECK)" in branch
    assert guard < branch.index('return BotActionArbitration::Outcome::Retryable("native_cast_unknown_spell");')
    assert guard < branch.index("bot->CastSpell(target, resolved.Effective->Id,")
    # The rule mirrored is the core's own client-cast rule.
    unit = UNIT.read_text(encoding="utf-8")
    assert ("!caster->ToPlayer()->HasActiveSpell(spellInfo->Id) "
            "&& !spellInfo->HasAttribute(SPELL_ATTR8_SKIP_IS_KNOWN_CHECK)") in unit
