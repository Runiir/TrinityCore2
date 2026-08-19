"""Canonical Cataclysm consumables for the frozen DPS reference cohort.

The inventory profile is shared by bot provisioning and WoWSims request
materialization.  A potion stack supplies two ordinary item uses: one before
combat and one after the combat potion lockout resets.
"""

from __future__ import annotations

from typing import Any, Mapping


INTELLECT_SPECS = frozenset(
    {
        "affliction_warlock",
        "balance_druid",
        "demonology_warlock",
        "elemental_shaman",
        "fire_mage",
        "shadow_priest",
    }
)
AGILITY_SPECS = frozenset(
    {
        "assassination_rogue",
        "combat_rogue",
        "feral_druid_dps",
        "marksmanship_hunter",
        "survival_hunter",
    }
)
STRENGTH_SPECS = frozenset(
    {
        "arms_warrior",
        "frost_death_knight",
        "fury_warrior",
        "retribution_paladin",
        "unholy_death_knight",
    }
)
CONTROLLED_DPS_SPECS = INTELLECT_SPECS | AGILITY_SPECS | STRENGTH_SPECS


PRIMARY_STAT_CONSUMABLES: dict[str, dict[str, dict[str, Any]]] = {
    "intellect": {
        "flask": {
            "item_id": 58086,
            "item_spell_id": 79470,
            "observed_aura_spell_id": 79470,
        },
        "food": {
            "item_id": 62671,
            "item_spell_id": 87587,
            "observed_aura_spell_id": 87547,
        },
        "potion": {
            "item_id": 58091,
            "item_spell_id": 79476,
            "observed_aura_spell_id": 79476,
        },
    },
    "agility": {
        "flask": {
            "item_id": 58087,
            "item_spell_id": 79471,
            "observed_aura_spell_id": 79471,
        },
        "food": {
            "item_id": 62669,
            "item_spell_id": 87586,
            "observed_aura_spell_id": 87546,
        },
        "potion": {
            "item_id": 58145,
            "item_spell_id": 79633,
            "observed_aura_spell_id": 79633,
        },
    },
    "strength": {
        "flask": {
            "item_id": 58088,
            "item_spell_id": 79472,
            "observed_aura_spell_id": 79472,
        },
        "food": {
            "item_id": 62670,
            "item_spell_id": 87584,
            "observed_aura_spell_id": 87545,
        },
        "potion": {
            "item_id": 58146,
            "item_spell_id": 79634,
            "observed_aura_spell_id": 79634,
        },
    },
}

CONTROLLED_POTION_ITEM_IDS = frozenset(
    int(rows["potion"]["item_id"]) for rows in PRIMARY_STAT_CONSUMABLES.values()
)


def primary_stat_for_spec(spec: str) -> str:
    if spec in INTELLECT_SPECS:
        return "intellect"
    if spec in AGILITY_SPECS:
        return "agility"
    if spec in STRENGTH_SPECS:
        return "strength"
    raise ValueError(f"{spec}: no frozen DPS consumable profile")


def controlled_consumable_profile(spec: str) -> dict[str, Any]:
    stat = primary_stat_for_spec(spec)
    rows = PRIMARY_STAT_CONSUMABLES[stat]
    flask = dict(rows["flask"])
    food = dict(rows["food"])
    potion = dict(rows["potion"])
    return {
        "schema": "cata_controlled_dps_consumables_v1",
        "primary_stat": stat,
        "flask": flask,
        "food": food,
        "prepot": dict(potion),
        "combat_potion": dict(potion),
        "inventory": [
            {
                "item_id": flask["item_id"],
                "slot": 26,
                "count": 20,
                "uses": ["flask_before_scoring"],
            },
            {
                "item_id": food["item_id"],
                "slot": 27,
                "count": 20,
                "uses": ["food_before_scoring"],
            },
            {
                "item_id": potion["item_id"],
                "slot": 28,
                "count": 20,
                "uses": ["prepot_before_combat", "combat_potion_during_combat"],
            },
        ],
    }


def validate_controlled_consumable_profile(
    spec: str, profile: Mapping[str, Any]
) -> None:
    expected = controlled_consumable_profile(spec)
    if dict(profile) != expected:
        raise ValueError(f"{spec}: controlled consumable profile drift")
