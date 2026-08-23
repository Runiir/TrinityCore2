from __future__ import annotations

from pathlib import Path

from tools.bot_ml.review_rotation_mechanics import normalize_runtime_report


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
NOTIFICATIONS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatNotifications.cpp"
JSON = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBotJson.cpp"


def test_shadow_bite_capture_is_bounded_and_observation_only():
    header = HEADER.read_text()
    notifications = NOTIFICATIONS.read_text()
    serialized = JSON.read_text()

    assert "struct PrimaryPetShadowBiteEvent" in header
    assert "std::vector<PrimaryPetShadowBiteEvent> PrimaryPetShadowBiteEvents;" in header
    assert "constexpr uint32 ShadowBiteSpellId = 54049;" in notifications
    assert "exactPetDamage && spellId == ShadowBiteSpellId" in notifications
    assert "PrimaryPetShadowBiteEvents.size() < 128" in notifications
    assert "event.MeasuredDamage = measuredDamage;" in notifications
    assert "event.UnmitigatedDamage = unmitigatedDamage;" in notifications
    assert "event.PetSpellPower = pet->GetBonusDamage();" in notifications
    assert "event.PetSpellCritPct = pet->SpellCritChanceDone" in notifications
    assert "owner->getClass() != CLASS_WARLOCK" in notifications
    assert "aura->GetCasterGUID() != owner->GetGUID()" in notifications
    assert "SPELL_AURA_PERIODIC_DAMAGE" in notifications
    assert "SPELL_AURA_PERIODIC_DAMAGE_PERCENT" not in notifications
    assert "std::sort(spellIds.begin(), spellIds.end());" in notifications
    assert "primary_pet_shadow_bite_events" in serialized
    for field in (
        "elapsed_ms",
        "measured_damage",
        "unmitigated_damage",
        "pet_spell_power",
        "pet_spell_crit_pct",
        "owner_cast_warlock_periodic_damage_aura_spell_ids",
        "owner_cast_warlock_periodic_damage_aura_count",
    ):
        assert field in serialized


def test_normalize_runtime_report_preserves_shadow_bite_event_evidence():
    runtime = {
        "combat_calibration": {
            "phase": "complete",
            "previous_window": {
                "bots": [
                    {
                        "guid": 1306,
                        "primary_pet_shadow_bite_events": [
                            {
                                "elapsed_ms": 2200,
                                "measured_damage": 321,
                                "unmitigated_damage": 347,
                                "pet_spell_power": 812,
                                "pet_spell_crit_pct": 11.25,
                                "owner_cast_warlock_periodic_damage_aura_spell_ids": [
                                    86121,
                                    172,
                                ],
                                "owner_cast_warlock_periodic_damage_aura_count": 2,
                            },
                            {
                                "elapsed_ms": 1100,
                                "measured_damage": 300,
                                "unmitigated_damage": 300,
                                "pet_spell_power": 812,
                                "pet_spell_crit_pct": 11.25,
                                "owner_cast_warlock_periodic_damage_aura_spell_ids": [],
                                "owner_cast_warlock_periodic_damage_aura_count": 0,
                            },
                        ],
                    }
                ]
            },
        }
    }

    normalized = normalize_runtime_report(runtime)

    assert normalized["primary_pet_shadow_bite_events"] == [
        {
            "bot_guid": 1306,
            "elapsed_ms": 1100,
            "measured_damage": 300,
            "unmitigated_damage": 300,
            "pet_spell_power": 812,
            "pet_spell_crit_pct": 11.25,
            "owner_cast_warlock_periodic_damage_aura_spell_ids": [],
            "owner_cast_warlock_periodic_damage_aura_count": 0,
        },
        {
            "bot_guid": 1306,
            "elapsed_ms": 2200,
            "measured_damage": 321,
            "unmitigated_damage": 347,
            "pet_spell_power": 812,
            "pet_spell_crit_pct": 11.25,
            "owner_cast_warlock_periodic_damage_aura_spell_ids": [172, 86121],
            "owner_cast_warlock_periodic_damage_aura_count": 2,
        },
    ]
