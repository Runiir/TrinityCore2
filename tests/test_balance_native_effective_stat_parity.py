"""Regression coverage for the native Balance scoring-start stat path."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYER_HEADER = ROOT / "src/server/game/Entities/Player/Player.h"
PLAYER_SOURCE = ROOT / "src/server/game/Entities/Player/Player.cpp"
LEDGER_SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationStatLedger.cpp"
AURA_SOURCE = ROOT / "src/server/game/Spells/Auras/SpellAuraEffects.cpp"


def test_balance_of_power_uses_gained_spirit_only():
    header = PLAYER_HEADER.read_text(encoding="utf-8")
    source = PLAYER_SOURCE.read_text(encoding="utf-8")

    assert "int32 GetRatingFromStatValue(AuraEffect const* aura) const;" in header
    assert "int32 GetBaseRatingValue(CombatRating cr) const" in header
    assert "int32 Player::GetRatingFromStatValue(AuraEffect const* aura) const" in source
    assert "aura->GetId() == SPELL_BALANCE_OF_POWER && stat == STAT_SPIRIT" in source
    assert "statValue - GetCreateStat(stat)" in source
    assert "amount += GetRatingFromStatValue(*i);" in source

    base_spirit = 173.0
    published_spirit = 1623.0
    raw_hit_rating = 289
    native_effective_hit_rating = raw_hit_rating + int(published_spirit - base_spirit)
    assert native_effective_hit_rating == 1739
    assert abs(native_effective_hit_rating / 102.44574 - 17.0041233535) < 0.05


def test_calibration_ledger_keeps_raw_rating_separate_from_effective_percentages():
    source = LEDGER_SOURCE.read_text(encoding="utf-8")

    assert "player->GetBaseRatingValue(type)" in source
    assert "stats.SpellHitPct = player->GetRatingBonusValue(CR_HIT_SPELL);" in source
    assert "PLAYER_FIELD_COMBAT_RATING_1" not in source


def test_moonkin_form_reapplies_missing_passive_and_removes_owned_aura():
    source = AURA_SOURCE.read_text(encoding="utf-8")

    assert "GetMiscValue() == FORM_MOONKIN && !target->HasAura(spellId2)" in source
    assert "target->AddAura(spellId2, target);" in source
    assert "target->RemoveOwnedAura(spellId2, target->GetGUID());" in source
