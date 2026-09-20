"""Source-shape checks and hand arithmetic for proposed Balance stat changes.

These do not execute aura application, casting-speed handlers or spell-group
stacking. Passing them is not behavioral proof or native repair acceptance.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYER_HEADER = ROOT / "src/server/game/Entities/Player/Player.h"
PLAYER_SOURCE = ROOT / "src/server/game/Entities/Player/Player.cpp"
LEDGER_SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationStatLedger.cpp"
AURA_SOURCE = ROOT / "src/server/game/Spells/Auras/SpellAuraEffects.cpp"
AURA_LIFECYCLE_SOURCE = ROOT / "src/server/game/Spells/Auras/SpellAuras.cpp"
AURA_OBSERVATION_SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationAuraObservation.cpp"
CALIBRATION_METRICS_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationMetrics.h"


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
    assert "float const castSpeed = unit->GetFloatValue(UNIT_MOD_CAST_SPEED);" in source
    assert "stats.SpellSpeedMultiplier = castSpeed > 0.0f ? 1.0f / castSpeed : 1.0f;" in source
    assert "castHaste * castSpeed" not in source
    assert "PLAYER_FIELD_COMBAT_RATING_1" not in source


def test_moonkin_form_materializes_owner_passive_and_removes_owned_aura():
    source = AURA_SOURCE.read_text(encoding="utf-8")

    assert "apply && GetMiscValue() == FORM_MOONKIN" in source
    assert "target->AddAura(spellId2, target)" in source
    assert "BuildEffectMaskForOwner" in source
    assert "AddStaticApplication(target, ownerEffectMask)" in source
    assert "target->RemoveOwnedAura(spellId2, target->GetGUID());" in source


def test_area_aura_owner_application_is_preserved_without_changing_propagation():
    source = AURA_LIFECYCLE_SOURCE.read_text(encoding="utf-8")

    assert "target == GetUnitOwner() && GetSpellInfo()->Effects[i].IsAreaAuraEffect()" in source
    assert "GetSpellInfo()->Effects[i].Effect != SPELL_EFFECT_APPLY_AURA" in source
    assert "Area auras normally materialize through FillTargetMap" in source


def test_calibration_observes_moonkin_aura_owner_application():
    source = AURA_OBSERVATION_SOURCE.read_text(encoding="utf-8")
    metrics = CALIBRATION_METRICS_HEADER.read_text(encoding="utf-8")

    assert "std::array<uint32, 5> OwnerAuraSpellIds" in source
    assert "24604, 76659, 82925, 82926, 24907" in source
    assert "std::array<OwnerAuraObservation, 5> OwnerAuraObservations" in metrics


def test_moonkin_cast_speed_handler_trace_preserves_native_arithmetic():
    source = AURA_SOURCE.read_text(encoding="utf-8")

    assert "BOT_CALIBRATION_MOONKIN_CAST_SPEED_HANDLER" in source
    assert "GetFloatValue(UNIT_MOD_CAST_SPEED)" in source
    assert "cast_speed_before" in source
    assert "cast_speed_after" in source
    assert "target->ApplyCastTimePercentMod((float)GetAmount(), apply" in source
