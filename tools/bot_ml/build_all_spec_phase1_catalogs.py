from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from tools.bot_ml.cata_dps_consumables import (
    CONTROLLED_DPS_SPECS,
    controlled_consumable_profile,
    validate_controlled_consumable_profile,
)

try:
    from .build_validation_provisioning import talent_data, validate_talent_manifest
    from .wowsims_gear_binding import (
        ENCHANT_APPLICABILITY_AUTHORITY,
        TRANSFORM_SCHEMA,
        selected_numeric_fixture_gear_label,
        validate_profile_local_legality,
        validate_profile_source_binding,
    )
except ImportError:
    from build_validation_provisioning import talent_data, validate_talent_manifest
    from wowsims_gear_binding import (
        ENCHANT_APPLICABILITY_AUTHORITY,
        TRANSFORM_SCHEMA,
        selected_numeric_fixture_gear_label,
        validate_profile_local_legality,
        validate_profile_source_binding,
    )

REPO_ROOT = Path(__file__).resolve().parents[2]
WOWSIMS_REPOSITORY = "https://github.com/wowsims/cata"
WOWSIMS_REVISION = "70d87383a9b92f30fb9e370c4676d3ce33b6e6b6"
WOWSIMS_RAW = f"https://raw.githubusercontent.com/wowsims/cata/{WOWSIMS_REVISION}"
ICY_JSON = "https://static.icy-veins.com/json/cata-talent-calculator"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "dataset/all_spec_phase1_catalogs"
TARGET_CATALOG_PATH = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
REFERENCE_CATALOG_PATH = REPO_ROOT / "experiments/configs/all_spec_references_cata_p4_v1.json"
CALIBRATION_CATALOG_PATH = REPO_ROOT / "experiments/configs/all_spec_calibration_scenarios_v1.json"
PAIRWISE_CATALOG_PATH = REPO_ROOT / "experiments/configs/stonecore_pairwise_constraints_v1.json"
PROVISIONING_PATH = REPO_ROOT / "experiments/configs/validation_provisioning_cata_001.json"
ACTION_PROFILES_PATH = REPO_ROOT / "experiments/configs/cata_434_action_profiles.json"
COMBAT_LOOT_PATH = REPO_ROOT / "experiments/configs/cata_434_combat_loot_profiles.json"
WOWSIMS_GEAR_PROFILES_PATH = REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
DPS_ACCEPTANCE_PATH = REPO_ROOT / "experiments/configs/cata_raid_dps_acceptance_v1.json"
DBC_DIR = REPO_ROOT / "data/dbc/enUS"

ROGUE_POISON_OWNERS = {"assassination_rogue", "combat_rogue"}
ROGUE_POISON_CONSUMABLES = (
    {"item_id": 43233, "slot": 23, "count": 20},
    {"item_id": 43231, "slot": 24, "count": 20},
)
DEFAULT_PLAYER_CONSUMABLES = (
    {"item_id": 58085, "slot": 40, "count": 20},
    {"item_id": 58086, "slot": 41, "count": 20},
    {"item_id": 58257, "slot": 42, "count": 20},
)

CLASS_META = {
    "warrior": {"class_id": 1, "race": 1, "archetype": "strength"},
    "paladin": {"class_id": 2, "race": 1, "archetype": "strength"},
    "hunter": {"class_id": 3, "race": 3, "archetype": "agility"},
    "rogue": {"class_id": 4, "race": 1, "archetype": "agility"},
    "priest": {"class_id": 5, "race": 1, "archetype": "intellect"},
    "death_knight": {"class_id": 6, "race": 1, "archetype": "strength"},
    "shaman": {"class_id": 7, "race": 11, "archetype": "intellect"},
    "mage": {"class_id": 8, "race": 1, "archetype": "intellect"},
    "warlock": {"class_id": 9, "race": 1, "archetype": "intellect"},
    "druid": {"class_id": 11, "race": 4, "archetype": "intellect"},
}

# One consolidated source pass covers every supported WoWSims record. The six
# unsupported healer/Frost records below are the only scoped second-pass rows.
TARGETS = [
    ("protection_warrior", "warrior", "protection", "tank", "Protwar", None),
    ("protection_paladin", "paladin", "protection", "tank", "Protpally", None),
    ("blood_death_knight", "death_knight", "blood", "tank", "Blooddk", None),
    ("feral_druid_tank", "druid", "guardian", "tank", "Feraltank", "tank"),
    ("holy_paladin", "paladin", "holy", "healer", "Holypally", None),
    ("discipline_priest", "priest", "discipline", "healer", "Discpriest", None),
    ("holy_priest", "priest", "holy", "healer", "Holypriest", None),
    ("restoration_shaman", "shaman", "restoration", "healer", "Restosham", None),
    ("restoration_druid", "druid", "restoration", "healer", "Restodruid", None),
    ("arms_warrior", "warrior", "arms", "dps", "Armswar", None),
    ("fury_warrior", "warrior", "fury", "dps", "Furywar", None),
    ("retribution_paladin", "paladin", "retribution", "dps", "Retpally", None),
    ("beast_mastery_hunter", "hunter", "beast_mastery", "dps", "Bmhunter", None),
    ("marksmanship_hunter", "hunter", "marksmanship", "dps", "Mmhunter", None),
    ("survival_hunter", "hunter", "survival", "dps", "Svhunter", None),
    ("assassination_rogue", "rogue", "assassination", "dps", "Assarogue", None),
    ("combat_rogue", "rogue", "combat", "dps", "Combatrog", None),
    ("subtlety_rogue", "rogue", "subtlety", "dps", "Subrogue", None),
    ("frost_death_knight", "death_knight", "frost", "dps", "Frostdk", None),
    ("unholy_death_knight", "death_knight", "unholy", "dps", "Unholydk", None),
    ("elemental_shaman", "shaman", "elemental", "dps", "Elesham", None),
    ("enhancement_shaman", "shaman", "enhancement", "dps", "Enhsham", None),
    ("arcane_mage", "mage", "arcane", "dps", "Arcanemage", None),
    ("fire_mage", "mage", "fire", "dps", "Firemage", None),
    ("frost_mage", "mage", "frost", "dps", "Frostmage", None),
    ("affliction_warlock", "warlock", "affliction", "dps", "Afflock", None),
    ("demonology_warlock", "warlock", "demonology", "dps", "Demolock", None),
    ("destruction_warlock", "warlock", "destruction", "dps", "Destrolock", None),
    ("shadow_priest", "priest", "shadow", "dps", "Shadowpr", None),
    ("balance_druid", "druid", "balance", "dps", "Baladruid", None),
    ("feral_druid_dps", "druid", "feral", "dps", "Feraldps", "dps"),
]

WOWSIMS_SUPPORT = {
    "protection_paladin": "beta",
    "holy_paladin": "unsupported",
    "discipline_priest": "unsupported",
    "holy_priest": "unsupported",
    "restoration_shaman": "unsupported",
    "restoration_druid": "unsupported",
    "frost_mage": "unsupported",
}

TALENT_VARIANT = {
    "fury_warrior": 1,
    "frost_death_knight": 2,
    "elemental_shaman": 0,
    "demonology_warlock": 1,
    "feral_druid_dps": 0,
    "feral_druid_tank": 0,
}

# Numeric result fixtures can intentionally use a different legal build from
# the UI preset. Keep the canonical live target aligned with the fixture that
# produced the pinned reference value.
RESULT_TALENT_OVERRIDE = {
    "survival_hunter": "03-2302-23203003023022121311",
}

# Gear identity is deliberately separate from the specialization join key.
# Most generated validation profiles use the specialization id, while these
# checked-in WoWSims overlays reproduce the exact preset used by the pinned
# numeric reference.  Every catalog/provisioning consumer must carry this id
# verbatim; it is not an alias that may be substituted at runtime.
CANONICAL_GEAR_PROFILE_IDS = {
    "balance_druid": "wowsims_cata_p4_balance_druid",
    "enhancement_shaman": "wowsims_cata_p4_enhancement_shaman",
    "fire_mage": "wowsims_cata_p4_fire_mage",
    "shadow_priest": "wowsims_cata_p4_shadow_priest",
    "survival_hunter": "wowsims_cata_p4_survival_hunter",
}

def canonical_gear_profile_id(target_id: str) -> str:
    return CANONICAL_GEAR_PROFILE_IDS.get(target_id, target_id)


def gear_profile_runtime_manifest(target_id: str) -> str:
    profiles = json.loads(
        WOWSIMS_GEAR_PROFILES_PATH.read_text(encoding="utf-8")
    ).get("profiles", {})
    if canonical_gear_profile_id(target_id) in profiles:
        return "experiments/configs/wowsims_cata_p4_gear_profiles.json"
    return "experiments/configs/cata_434_combat_loot_profiles.json"

GEAR_PATH = {
    "protection_warrior": "ui/warrior/protection/gear_sets/p4_bis.gear.json",
    "protection_paladin": "ui/paladin/protection/gear_sets/T12.gear.json",
    "blood_death_knight": "ui/death_knight/blood/gear_sets/p3-balanced.gear.json",
    "feral_druid_tank": "ui/druid/guardian/gear_sets/p4.gear.json",
    "holy_paladin": "ui/paladin/holy/gear_sets/p4.gear.json",
    "discipline_priest": "ui/priest/discipline/gear_sets/p4.gear.json",
    "holy_priest": "ui/priest/holy/gear_sets/p4.gear.json",
    "restoration_shaman": "ui/shaman/restoration/gear_sets/p4.gear.json",
    "restoration_druid": "ui/druid/restoration/gear_sets/p4.gear.json",
    "arms_warrior": "ui/warrior/arms/gear_sets/p4_arms_bis.gear.json",
    "fury_warrior": "ui/warrior/fury/gear_sets/p4_fury_tg.gear.json",
    "retribution_paladin": "ui/paladin/retribution/gear_sets/p4_bis.gear.json",
    "beast_mastery_hunter": "ui/hunter/beast_mastery/gear_sets/p3_bm.gear.json",
    "marksmanship_hunter": "ui/hunter/marksmanship/gear_sets/p4_mm.gear.json",
    "survival_hunter": "ui/hunter/survival/gear_sets/p4_sv.gear.json",
    "assassination_rogue": "ui/rogue/assassination/gear_sets/p4_assassination.gear.json",
    "combat_rogue": "ui/rogue/combat/gear_sets/p4_combat.gear.json",
    "subtlety_rogue": "ui/rogue/subtlety/gear_sets/p4_subtlety.gear.json",
    "frost_death_knight": "ui/death_knight/frost/gear_sets/p4.masterfrost.gear.json",
    "unholy_death_knight": "ui/death_knight/unholy/gear_sets/p4.bis.gear.json",
    "elemental_shaman": "ui/shaman/elemental/gear_sets/p4.default.gear.json",
    "enhancement_shaman": "ui/shaman/enhancement/gear_sets/p4.orc.gear.json",
    "arcane_mage": "ui/mage/arcane/gear_sets/p4.gear.json",
    "fire_mage": "ui/mage/fire/gear_sets/p4_fire.gear.json",
    "frost_mage": "ui/mage/frost/gear_sets/p3_frost_alliance.gear.json",
    "affliction_warlock": "ui/warlock/affliction/gear_sets/p4.gear.json",
    "demonology_warlock": "ui/warlock/demonology/gear_sets/p4.gear.json",
    "destruction_warlock": "ui/warlock/destruction/gear_sets/p4.gear.json",
    "shadow_priest": "ui/priest/shadow/gear_sets/p4.gear.json",
    "balance_druid": "ui/druid/balance/gear_sets/t13.gear.json",
    "feral_druid_dps": "ui/druid/feral/gear_sets/p4.gear.json",
}

APL_PATH = {
    "protection_warrior": "ui/warrior/protection/apls/default.apl.json",
    "protection_paladin": "ui/paladin/protection/apls/default.apl.json",
    "blood_death_knight": "ui/death_knight/blood/apls/defensive.apl.json",
    "feral_druid_tank": "ui/druid/guardian/apls/default.apl.json",
    "arms_warrior": "ui/warrior/arms/apls/arms.apl.json",
    "fury_warrior": "ui/warrior/fury/apls/tg.apl.json",
    "retribution_paladin": "ui/paladin/retribution/apls/default.apl.json",
    "beast_mastery_hunter": "ui/hunter/beast_mastery/apls/bm.apl.json",
    "marksmanship_hunter": "ui/hunter/marksmanship/apls/mm.apl.json",
    "survival_hunter": "ui/hunter/survival/apls/sv.apl.json",
    "assassination_rogue": "ui/rogue/assassination/apls/mutilate.apl.json",
    "combat_rogue": "ui/rogue/combat/apls/combat.apl.json",
    "subtlety_rogue": "ui/rogue/subtlety/apls/subtlety.apl.json",
    "frost_death_knight": "ui/death_knight/frost/apls/masterfrost.apl.json",
    "unholy_death_knight": "ui/death_knight/unholy/apls/default.apl.json",
    "elemental_shaman": "ui/shaman/elemental/apls/default.apl.json",
    "enhancement_shaman": "ui/shaman/enhancement/apls/default.apl.json",
    "arcane_mage": "ui/mage/arcane/apls/arcane.apl.json",
    "fire_mage": "ui/mage/fire/apls/fire.apl.json",
    "frost_mage": "ui/mage/frost/apls/frost.apl.json",
    "affliction_warlock": "ui/warlock/affliction/apls/default.apl.json",
    "demonology_warlock": "ui/warlock/demonology/apls/incinerate.apl.json",
    "destruction_warlock": "ui/warlock/destruction/apls/default.apl.json",
    "shadow_priest": "ui/priest/shadow/apls/p4.apl.json",
    "balance_druid": "ui/druid/balance/apls/t13.apl.json",
    "feral_druid_dps": "ui/druid/feral/apls/default.apl.json",
}

RESULT_META = {
    "protection_warrior": ("sim/warrior/protection/protection_test.go", "sim/warrior/protection/TestProtectionWarrior.results"),
    "protection_paladin": ("sim/paladin/protection/protection_test.go", "sim/paladin/protection/TestProtection.results"),
    "blood_death_knight": ("sim/death_knight/blood/blood_test.go", "sim/death_knight/blood/TestBlood.results"),
    "feral_druid_tank": ("sim/druid/guardian/tank_test.go", "sim/druid/guardian/TestGuardian.results"),
    "arms_warrior": ("sim/warrior/arms/arms_test.go", "sim/warrior/arms/TestArms.results"),
    "fury_warrior": ("sim/warrior/fury/fury_test.go", "sim/warrior/fury/TestFury.results"),
    "retribution_paladin": ("sim/paladin/retribution/retribution_test.go", "sim/paladin/retribution/TestRetribution.results"),
    "beast_mastery_hunter": ("sim/hunter/beast_mastery/beast_mastery_test.go", "sim/hunter/beast_mastery/TestBM.results"),
    "marksmanship_hunter": ("sim/hunter/marksmanship/marksmanship_test.go", "sim/hunter/marksmanship/TestMM.results"),
    "survival_hunter": ("sim/hunter/survival/survival_test.go", "sim/hunter/survival/TestSV.results"),
    "assassination_rogue": ("sim/rogue/assassination/assassination_test.go", "sim/rogue/assassination/TestAssassination.results"),
    "combat_rogue": ("sim/rogue/combat/combat_test.go", "sim/rogue/combat/TestCombat.results"),
    "subtlety_rogue": ("sim/rogue/subtlety/subtlety_test.go", "sim/rogue/subtlety/TestSubtlety.results"),
    "frost_death_knight": ("sim/death_knight/frost/frost_test.go", "sim/death_knight/frost/TestFrost.results"),
    "unholy_death_knight": ("sim/death_knight/unholy/unholy_test.go", "sim/death_knight/unholy/TestUnholy.results"),
    "elemental_shaman": ("sim/shaman/elemental/elemental_test.go", "sim/shaman/elemental/TestElemental.results"),
    "enhancement_shaman": ("sim/shaman/enhancement/enhancement_test.go", "sim/shaman/enhancement/TestEnhancement.results"),
    "arcane_mage": ("sim/mage/arcane/arcane_test.go", "sim/mage/arcane/TestArcane.results"),
    "fire_mage": ("sim/mage/fire/fire_test.go", "sim/mage/fire/TestFire.results"),
    "affliction_warlock": ("sim/warlock/affliction/affliction_test.go", "sim/warlock/affliction/TestAffliction.results"),
    "demonology_warlock": ("sim/warlock/demonology/demonology_test.go", "sim/warlock/demonology/TestDemonology.results"),
    "destruction_warlock": ("sim/warlock/destruction/destruction_test.go", "sim/warlock/destruction/TestDestruction.results"),
    "shadow_priest": ("sim/priest/shadow/shadow_test.go", "sim/priest/shadow/TestShadow.results"),
    "balance_druid": ("sim/druid/balance/balance_test.go", "sim/druid/balance/TestBalance.results"),
    "feral_druid_dps": ("sim/druid/feral/feral_test.go", "sim/druid/feral/TestFeral.results"),
}

# Average-Default selects the first test matrix configuration. These two
# numeric references intentionally use the exact Phase-4 gear preset instead,
# so pin the complete Settings row which names that preset. Keeping the key
# here makes a source refresh reproduce the catalog without a hand edit.
RESULT_KEY_OVERRIDE = {
    "assassination_rogue": (
        "TestAssassination-Settings-Human-p4_assassination-Assassination-"
        "mutilate-FullBuffs-0.0yards-LongSingleTarget"
    ),
    "combat_rogue": (
        "TestCombat-Settings-Human-p4_combat-Combat-combat-FullBuffs-"
        "0.0yards-LongSingleTarget"
    ),
}

ICY_BUILD = {
    "holy_paladin": ("paladin", "#tc-111222433378899abcccdeeefgghhhjGGFFFmmkkk|0i1v2r3z5k4e6E7a8u", "https://www.icy-veins.com/cataclysm-classic/holy-paladin-pve-spec-builds-talents-glyphs"),
    "discipline_priest": ("priest", "#tc-22211100566a877bbbcceefffghhjjkmmmnnnGGGo|0h1i2G3D4a5H6e7C8u", "https://www.icy-veins.com/cataclysm-classic/discipline-priest-pve-spec-builds-talents-glyphs"),
    "holy_priest": ("priest", "#tc-nnnmmmllpprrssuuxxvtzAqqoECCCDF22211GGG1D|0k1v2o3z4D5H6e7C8u", "https://www.icy-veins.com/cataclysm-classic/holy-priest-pve-spec-builds-talents-glyphs"),
    "restoration_shaman": ("shaman", "#tc-EEEDDDFFGGKJJLLLNSQTTTMMVjj000RRCC2266PPP|0E1I2a3A4f5F6q7v8u", "https://www.icy-veins.com/cataclysm-classic/restoration-shaman-pve-spec-builds-talents-glyphs"),
    "restoration_druid": ("druid", "#tc-IIJJJMMMGGPOOHHLSSTTVUUUWYYYZR-2200043l44|0m2G1k3B5P4i6p7x8r", "https://www.icy-veins.com/cataclysm-classic/restoration-druid-pve-spec-builds-talents-glyphs"),
    "frost_mage": ("mage", "#tc-HHHGGIIJJJQQQPPPORRRSTTTVWWXXMYllmmmooo22|0o1L2H3l4j5N6I7A8x", "https://www.icy-veins.com/cataclysm-classic/frost-mage-pve-spec-builds-talents-glyphs"),
}

ROLE_CAPABILITIES = {
    "tank": ["single_target_threat", "aoe_threat", "active_mitigation", "defensive_cooldown", "taunt", "interrupt", "hazard_movement"],
    "healer": ["single_target_heal", "party_heal", "emergency_heal", "dispel", "mana_management", "defensive_cooldown", "hazard_movement"],
    "dps": ["single_target_damage", "separate_aoe_damage", "offensive_cooldown", "interrupt_or_control", "target_switch", "hazard_movement"],
}

CLASS_UTILITY = {
    "warrior": ["pummel", "heroic_leap", "battle_shout"],
    "paladin": ["rebuke", "hand_utility", "divine_protection"],
    "hunter": ["counterattack_utility", "misdirection", "trap_control"],
    "rogue": ["kick", "tricks_of_the_trade", "feint"],
    "priest": ["dispel_magic", "mass_dispel", "levitate", "threat_drop"],
    "death_knight": ["mind_freeze", "death_grip", "anti_magic_shell"],
    "shaman": ["wind_shear", "totem_utility", "purge"],
    "mage": ["counterspell", "blink", "spellsteal"],
    "warlock": ["spell_lock_or_shadowfury", "healthstone", "fear_control"],
    "druid": ["skull_bash_or_solar_beam", "rebirth", "stampeding_roar"],
}

SPEC_BEHAVIOR = {
    "blood_death_knight": ["blood_presence", "death_strike_timing", "rune_and_runic_power"],
    "feral_druid_tank": ["bear_form", "savage_defense", "rage_management"],
    "feral_druid_dps": ["cat_form", "bleed_snapshot", "energy_combo_points"],
    "balance_druid": ["moonkin_form", "eclipse_cycle", "dot_refresh"],
    "restoration_druid": ["tree_of_life", "lifebloom_maintenance", "swiftmend_efflorescence"],
    "beast_mastery_hunter": ["permanent_pet", "bestial_wrath", "focus_management"],
    "marksmanship_hunter": ["permanent_pet", "steady_focus", "careful_aim_execute_inverse"],
    "survival_hunter": ["permanent_pet", "explosive_shot_lock_and_load", "focus_management"],
    "unholy_death_knight": ["unholy_presence", "permanent_ghoul", "dark_transformation"],
    "frost_death_knight": ["unholy_presence", "dual_wield_masterfrost", "runic_power"],
    "affliction_warlock": ["felhunter_pet", "dot_refresh", "drain_soul_execute"],
    "demonology_warlock": ["felguard_pet", "metamorphosis", "decimation_execute"],
    "destruction_warlock": ["imp_pet", "improved_soul_fire", "shadowburn_execute"],
    "shadow_priest": ["shadowform", "dot_refresh", "shadow_word_death_execute"],
    "arms_warrior": ["battle_stance", "rend_maintenance", "execute_phase"],
    "fury_warrior": ["berserker_stance", "titan_grip", "execute_phase"],
    "protection_warrior": ["defensive_stance", "shield_block", "rage_management"],
    "protection_paladin": ["righteous_fury", "holy_power", "shield_of_the_righteous"],
    "holy_paladin": ["beacon_of_light", "holy_power", "aura_mastery"],
    "retribution_paladin": ["seal_and_judgement", "holy_power", "hammer_of_wrath_execute"],
    "discipline_priest": ["power_word_shield", "divine_aegis", "pain_suppression"],
    "holy_priest": ["chakra_serenity_or_sanctuary", "prayer_of_mending", "guardian_spirit"],
    "restoration_shaman": ["earth_shield", "riptide", "spirit_link_totem"],
    "elemental_shaman": ["lightning_shield", "flame_shock", "lava_burst"],
    "enhancement_shaman": ["weapon_imbues", "maelstrom_weapon", "searing_totem"],
    "arcane_mage": ["arcane_charge_cycle", "mana_burn_conserve", "arcane_power"],
    "fire_mage": ["living_bomb", "hot_streak", "combustion"],
    "frost_mage": ["water_elemental", "fingers_of_frost", "deep_freeze"],
    "assassination_rogue": ["poisons", "envenom_uptime", "backstab_execute"],
    "combat_rogue": ["poisons", "bandits_guile", "killing_spree"],
    "subtlety_rogue": ["poisons", "hemorrhage_or_rupture", "shadow_dance"],
}

GUIDE_SLUG = {
    "protection_warrior": "protection-warrior",
    "protection_paladin": "protection-paladin",
    "blood_death_knight": "blood-death-knight",
    "feral_druid_tank": "feral-druid-tank",
    "holy_paladin": "holy-paladin",
    "discipline_priest": "discipline-priest",
    "holy_priest": "holy-priest",
    "restoration_shaman": "restoration-shaman",
    "restoration_druid": "restoration-druid",
    "arms_warrior": "arms-warrior",
    "fury_warrior": "fury-warrior",
    "retribution_paladin": "retribution-paladin",
    "beast_mastery_hunter": "beast-mastery-hunter",
    "marksmanship_hunter": "marksmanship-hunter",
    "survival_hunter": "survival-hunter",
    "assassination_rogue": "assassination-rogue",
    "combat_rogue": "combat-rogue",
    "subtlety_rogue": "subtlety-rogue",
    "frost_death_knight": "frost-death-knight",
    "unholy_death_knight": "unholy-death-knight",
    "elemental_shaman": "elemental-shaman",
    "enhancement_shaman": "enhancement-shaman",
    "arcane_mage": "arcane-mage",
    "fire_mage": "fire-mage",
    "frost_mage": "frost-mage",
    "affliction_warlock": "affliction-warlock",
    "demonology_warlock": "demonology-warlock",
    "destruction_warlock": "destruction-warlock",
    "shadow_priest": "shadow-priest",
    "balance_druid": "balance-druid",
    "feral_druid_dps": "feral-druid-dps",
}
GUIDE_URL = {
    target_id: f"https://www.icy-veins.com/cataclysm-classic/{GUIDE_SLUG[target_id]}-pve-guide"
    for target_id, *_rest in TARGETS
}

RUNTIME_ROTATION_SQL = "sql/custom/world/2026_07_18_00_all_spec_rotation_profile_coverage.sql"
RUNTIME_PROFILE_SPEC_TAG = {
    "protection_paladin": "protection",
    "marksmanship_hunter": "marksmanship",
    "survival_hunter": "survival",
    "enhancement_shaman": "enhancement",
    "fire_mage": "fire",
}

# Preserve the previously tuned spec-level provisioning spells while expanding
# the manifest to all 31 targets. The generated all-spec map must not erase
# runtime actions that predate the canonical catalog.
LEGACY_TUNED_ACTION_SPELL_IDS = {
    "protection_paladin": [20271, 35395, 53595, 31935, 26573, 53600, 62124, 31789, 96231, 2812, 498, 25780, 31801, 465, 20217, 54428, 31884, 85673, 86150, 1038, 1022, 84963],
    "holy_priest": [586],
    "fire_mage": [133, 1459, 2948, 2136, 2120, 2139, 30482, 44457, 92315, 82731, 45438, 55342, 11129, 11113],
    "marksmanship_hunter": [75, 1978, 3044, 56641, 2643, 53351, 77767, 883, 982, 2641, 1130, 13165, 34477, 3045],
    "survival_hunter": [75, 1978, 3044, 2643, 53351, 77767, 883, 982, 2641, 1130, 13165, 34477, 3045, 53301, 3674, 13813, 77769, 20572],
    "enhancement_shaman": [324, 403, 421, 8024, 8050, 8042, 8232, 17364, 60103, 57994, 73680, 8075, 3599, 8190, 8512, 51533],
}

# Phase 8 tuning migrations extend the original canonical profile source. Keep
# every added runtime action provisioned when pinned source catalogs refresh.
QUALIFICATION_TUNED_ACTION_SPELL_IDS = {
    "protection_warrior": [772, 845, 871, 6343],
    "arms_warrior": [845, 1719, 6343],
    "fury_warrior": [845, 1134, 1719, 18499],
    "blood_death_knight": [48721, 56815],
    "frost_death_knight": [42650, 45529, 46584, 47568, 48265, 77575],
    "unholy_death_knight": [42650, 43265, 45529, 46584, 47568, 48265, 49016, 49206, 77575],
    "feral_druid_tank": [99, 6807, 80964],
    "holy_paladin": [4987],
    "holy_priest": [34433, 64843, 64901, 88684],
    "restoration_druid": [774, 2782, 20484],
    "fire_mage": [5405, 6117, 12051],
    "marksmanship_hunter": [34490],
    "protection_paladin": [24275],
    "affliction_warlock": [603, 1120, 1454, 6353, 47897, 74434, 77799, 77801],
    "demonology_warlock": [603, 6353, 18540, 29722, 33697, 47897, 50589, 74434],
}

# BotWorldPopulationMgr's persistent setup casts these spells before choosing a
# rotation action. Missing setup spells can invalidate an otherwise complete
# profile, such as Shield Block outside Defensive Stance.
PERSISTENT_SETUP_SPELL_IDS = {
    "protection_warrior": [71],
    "arms_warrior": [2457],
    "fury_warrior": [2458],
    "protection_paladin": [25780, 31801, 465, 20217],
    "holy_paladin": [20217],
    "retribution_paladin": [20217],
    "blood_death_knight": [48263],
    "frost_death_knight": [48265],
    # Raise Dead is an ordinary learned Unholy action. Runtime requires the
    # Master of Ghouls talent aura and reconciles the resulting permanent pet;
    # provisioning only guarantees that the player knows these setup spells.
    "unholy_death_knight": [46584, 48265],
    "feral_druid_tank": [5487],
    "feral_druid_dps": [768, 20484],
    "arcane_mage": [1459, 30482],
    "fire_mage": [759, 1459, 30482],
    "frost_mage": [1459, 30482],
    "beast_mastery_hunter": [13165],
    "marksmanship_hunter": [13165],
    "survival_hunter": [13165],
    # WoWSims applies Fel Armor permanently for every Cataclysm warlock and
    # includes its spell-power bonus in the generated reference. Provision the
    # ordinary learned spell so runtime can establish the same aura with a
    # native self-cast before the scored-window reset.
    "affliction_warlock": [691, 28176],
    "demonology_warlock": [28176, 30146],
    "elemental_shaman": [324],
    "enhancement_shaman": [324],
    "restoration_shaman": [324],
}

# Explicit SQL/rule profiles remain runtime authority. These spell lists seed the
# 17 Phase 0 profile gaps and are also provisioned as known spells. Later
# calibration phases may tune priorities without changing the canonical links.
RUNTIME_ACTION_SPELL_IDS = {
    "feral_druid_tank": [99, 6795, 779, 22812, 33745, 33878, 77758, 77761, 80313],
    "restoration_shaman": [331, 1064, 8004, 51886, 61295, 77472],
    "arms_warrior": [772, 1464, 5308, 6552, 7384, 12294, 86346],
    "fury_warrior": [1464, 1680, 5308, 6552, 23881, 85288, 86346],
    "retribution_paladin": [879, 20271, 24275, 35395, 53385, 85256, 96231],
    "beast_mastery_hunter": [1978, 2643, 3044, 19577, 34026, 53351, 77767],
    "assassination_rogue": [53, 1329, 1766, 1943, 5171, 14177, 32645, 51723, 57934, 79140],
    "combat_rogue": [1752, 1766, 1943, 2098, 5171, 13750, 51690, 84617],
    "subtlety_rogue": [53, 1752, 1766, 1943, 2098, 5171, 16511, 51713, 51723],
    "frost_death_knight": [45462, 47528, 48265, 49020, 49143, 49184, 51271, 57330],
    "unholy_death_knight": [45462, 46584, 47528, 47541, 55090, 57330, 63560, 77575, 85948],
    "arcane_mage": [1449, 2139, 5143, 12042, 12051, 30451, 44425],
    "frost_mage": [10, 116, 2139, 12472, 30455, 31687, 44572, 44614],
    "demonology_warlock": [172, 348, 686, 689, 1454, 1949, 6353, 47241, 71521, 77801],
    "destruction_warlock": [348, 5740, 6353, 17877, 17962, 29722, 50796, 77801],
    "shadow_priest": [588, 589, 2944, 8092, 8122, 15407, 15473, 26297, 32379, 34433, 34914, 47585, 48045, 87151, 87153],
    "balance_druid": [5570, 8921, 16914, 2912, 5176, 33831, 48505, 50516, 78674],
    "feral_druid_dps": [1079, 1822, 5217, 5221, 22568, 33876, 50334, 52610, 62078, 80965],
}


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "trinity-cata-phase1-catalog/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def source_record(url: str, content: bytes) -> dict[str, Any]:
    return {"url": url, "sha256": hashlib.sha256(content).hexdigest(), "byte_count": len(content)}


def reconcile_rogue_poison_provisioning(targets: list[dict[str, Any]]) -> None:
    """Reconcile exact ordinary poison stacks without rebuilding references."""
    poison_ids = {int(row["item_id"]) for row in ROGUE_POISON_CONSUMABLES}
    for target in targets:
        target_id = str(target.get("spec_target_id") or "")
        bot = target.get("provisioning_bot")
        if not isinstance(bot, dict):
            raise ValueError(f"{target_id or '<unknown>'}: missing provisioning bot")

        item_ids = [
            int(item_id)
            for item_id in bot.get("consumable_item_ids", [])
            if int(item_id) not in poison_ids
        ]
        explicit = [
            dict(row)
            for row in bot.get("consumables", [])
            if int(row.get("item_id") or 0) not in poison_ids
        ]
        if target_id in ROGUE_POISON_OWNERS:
            for item_id in sorted(poison_ids, reverse=True):
                if item_id not in item_ids:
                    item_ids.append(item_id)
            if not explicit:
                explicit = [dict(row) for row in DEFAULT_PLAYER_CONSUMABLES]
            explicit.extend(dict(row) for row in ROGUE_POISON_CONSUMABLES)
        bot["consumable_item_ids"] = item_ids
        top_level_ids = [
            int(item_id)
            for item_id in target.get("consumable_item_ids", [])
            if int(item_id) not in poison_ids
        ]
        if target_id in ROGUE_POISON_OWNERS:
            top_level_ids = list(item_ids)
        if "consumable_item_ids" in target:
            target["consumable_item_ids"] = top_level_ids
        if explicit:
            bot["consumables"] = explicit
        else:
            bot.pop("consumables", None)


def reconcile_controlled_dps_consumable_provisioning(
    targets: list[dict[str, Any]],
) -> None:
    """Install exact flask, food, and two-use potion stacks for DPS refs."""
    for target in targets:
        spec = str(target.get("spec_target_id") or "")
        if spec not in CONTROLLED_DPS_SPECS:
            continue
        bot = target.get("provisioning_bot")
        if not isinstance(bot, dict):
            raise ValueError(f"{spec}: missing provisioning bot")
        profile = controlled_consumable_profile(spec)
        inventory = [dict(row) for row in profile["inventory"]]
        bot["controlled_consumable_profile"] = profile
        bot["consumables"] = inventory
        bot["consumable_item_ids"] = [
            int(row["item_id"]) for row in inventory
        ]
        target["consumable_item_ids"] = list(bot["consumable_item_ids"])


def validate_controlled_dps_consumable_provisioning(
    targets: list[dict[str, Any]],
) -> None:
    seen: set[str] = set()
    poison_ids = {int(row["item_id"]) for row in ROGUE_POISON_CONSUMABLES}
    for target in targets:
        spec = str(target.get("spec_target_id") or "")
        if spec not in CONTROLLED_DPS_SPECS:
            continue
        seen.add(spec)
        bot = target.get("provisioning_bot") or {}
        profile = bot.get("controlled_consumable_profile")
        if not isinstance(profile, dict):
            raise ValueError(f"{spec}: missing controlled consumable profile")
        validate_controlled_consumable_profile(spec, profile)
        expected_inventory = {
            (int(row["item_id"]), int(row["slot"]), int(row["count"]))
            for row in profile["inventory"]
        }
        actual_inventory = {
            (
                int(row.get("item_id") or 0),
                int(row.get("slot") or 0),
                int(row.get("count") or 0),
            )
            for row in bot.get("consumables", [])
            if int(row.get("item_id") or 0) not in poison_ids
        }
        if actual_inventory != expected_inventory:
            raise ValueError(f"{spec}: controlled consumable inventory drift")
        expected_ids = {row[0] for row in expected_inventory}
        actual_ids = {
            int(value)
            for value in bot.get("consumable_item_ids", [])
            if int(value) not in poison_ids
        }
        top_level_ids = {
            int(value)
            for value in target.get("consumable_item_ids", [])
            if int(value) not in poison_ids
        }
        if actual_ids != expected_ids or top_level_ids != expected_ids:
            raise ValueError(f"{spec}: controlled consumable item identity drift")
    if seen != set(CONTROLLED_DPS_SPECS):
        raise ValueError("controlled DPS consumable cohort is incomplete")


def validate_rogue_poison_provisioning(targets: list[dict[str, Any]]) -> None:
    poison_contract = {
        int(row["item_id"]): (int(row["slot"]), int(row["count"]))
        for row in ROGUE_POISON_CONSUMABLES
    }
    owners_by_item = {item_id: set() for item_id in poison_contract}
    targets_by_id = {str(row.get("spec_target_id") or ""): row for row in targets}
    for target_id, target in targets_by_id.items():
        bot = target.get("provisioning_bot") or {}
        top_level_ids = [int(value) for value in target.get("consumable_item_ids", [])]
        declared_ids = {int(value) for value in bot.get("consumable_item_ids", [])}
        explicit = {
            int(row.get("item_id") or 0): (
                int(row.get("slot") or 0), int(row.get("count") or 0)
            )
            for row in bot.get("consumables", [])
        }
        for item_id in poison_contract:
            if item_id in top_level_ids or item_id in declared_ids or item_id in explicit:
                owners_by_item[item_id].add(target_id)
        if target_id in ROGUE_POISON_OWNERS:
            bot_ids = [int(value) for value in bot.get("consumable_item_ids", [])]
            if (
                top_level_ids != bot_ids
                or len(top_level_ids) != len(set(top_level_ids))
            ):
                raise ValueError(
                    f"{target_id}: top-level/provisioning consumable identity drift"
                )
            for item_id, exact_row in poison_contract.items():
                if item_id not in declared_ids or explicit.get(item_id) != exact_row:
                    raise ValueError(
                        f"{target_id}: rogue poison {item_id} missing exact slot/count"
                    )

    for item_id, owners in owners_by_item.items():
        if owners != ROGUE_POISON_OWNERS:
            raise ValueError(
                f"rogue poison {item_id} owners must be exactly "
                f"{sorted(ROGUE_POISON_OWNERS)}, got {sorted(owners)}"
            )


def parse_wowsims_talents(
    target_id: str,
    class_name: str,
    spec_name: str,
    preset_text: str,
    tree_payload: list[dict[str, Any]],
    proto_text: str,
) -> tuple[dict[str, Any], list[int], str]:
    strings = re.findall(r"talentsString:\s*['\"]([^'\"]+)", preset_text)
    if not strings:
        raise ValueError(f"{target_id}: missing WoWSims talent string")
    preset_selected = strings[TALENT_VARIANT.get(target_id, 0)]
    selected = RESULT_TALENT_OVERRIDE.get(target_id, preset_selected)
    if sum(int(char) for char in selected if char.isdigit()) != 41:
        raise ValueError(f"{target_id}: WoWSims talent string is not a Cataclysm 41-point build")
    segments = selected.split("-")
    if len(segments) < len(tree_payload):
        segments.extend([""] * (len(tree_payload) - len(segments)))
    if len(segments) != len(tree_payload):
        raise ValueError(f"{target_id}: talent tree segment count mismatch")
    dbc_talents, primary_spells = talent_data()
    spell_to_talent: dict[int, tuple[int, list[Any]]] = {}
    for talent_id, row in dbc_talents.items():
        for spell_id in row[4:9]:
            if int(spell_id):
                spell_to_talent[int(spell_id)] = (talent_id, row)
    selected_rows: list[dict[str, int]] = []
    points_by_tree: Counter[int] = Counter()
    for segment, tree in zip(segments, tree_payload):
        for rank_char, talent in zip(segment, tree["talents"]):
            rank = int(rank_char)
            if rank <= 0:
                continue
            spell_id = int(talent["spellIds"][rank - 1])
            talent_id, row = spell_to_talent[spell_id]
            selected_rows.append({"talent_id": talent_id, "spell_id": spell_id})
            points_by_tree[int(row[1])] += rank
    primary_tree_id = points_by_tree.most_common(1)[0][0]
    build = {
        "primary_talent_tree_id": primary_tree_id,
        "talents": sorted(selected_rows, key=lambda row: row["talent_id"]),
        "primary_tree_spells": sorted(primary_spells[primary_tree_id]),
    }
    validate_talent_manifest({"name": target_id, **build})
    occurrence = [match.start() for match in re.finditer(re.escape(preset_selected), preset_text)][0]
    glyph_block = preset_text[occurrence : occurrence + 2400]
    glyph_names = re.findall(r"(?:prime|major|minor)\d:\s*\w+\.([A-Za-z0-9_]+)", glyph_block)
    enum_values = {name: int(value) for name, value in re.findall(r"\b([A-Za-z0-9_]+)\s*=\s*(\d+)\s*;", proto_text)}
    glyphs = [enum_values[name] for name in glyph_names if name in enum_values][:9]
    if len(glyphs) < 3:
        raise ValueError(f"{target_id}: expected at least three WoWSims glyphs, found {len(glyphs)}")
    return build, glyphs, selected


def icy_url_characters() -> list[str]:
    return [str(value) for value in range(10)] + list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-._~[]()ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝﾞﾟ")


def parse_icy_build(class_name: str, encoded: str, class_payload: dict[str, Any], glyph_payload: dict[str, Any]) -> tuple[dict[str, Any], list[int]]:
    talent_part, glyph_part = encoded.split("|", 1)
    talent_part = talent_part.removeprefix("#tc-")
    chars = icy_url_characters()
    talent_by_char: dict[str, tuple[int, dict[str, Any]]] = {}
    index = 0
    for tree_index, tree in enumerate(class_payload["talentGroups"]):
        for talent in tree["talents"]:
            if talent is None:
                continue
            talent_by_char[chars[index]] = (tree_index, talent)
            index += 1
    ranks: Counter[str] = Counter(talent_part)
    selected: list[dict[str, int]] = []
    points_by_tree: Counter[int] = Counter()
    dbc_talents, primary_spells = talent_data()
    spell_to_talent: dict[int, tuple[int, list[Any]]] = {}
    for talent_id, row in dbc_talents.items():
        for spell_id in row[4:9]:
            if int(spell_id):
                spell_to_talent[int(spell_id)] = (talent_id, row)
    for url_char, rank in ranks.items():
        tree_index, talent = talent_by_char[url_char]
        if rank > int(talent["maxRank"]):
            raise ValueError(f"{class_name}: encoded talent rank exceeds maximum")
        spell_id = int(talent["ranks"][rank - 1]["id"])
        talent_id, row = spell_to_talent[spell_id]
        selected.append({"talent_id": talent_id, "spell_id": spell_id})
        points_by_tree[int(row[1])] += rank
    if sum(ranks.values()) != 41:
        raise ValueError(f"{class_name}: Icy Veins build is not 41 points")
    primary_tree_id = points_by_tree.most_common(1)[0][0]
    build = {
        "primary_talent_tree_id": primary_tree_id,
        "talents": sorted(selected, key=lambda row: row["talent_id"]),
        "primary_tree_spells": sorted(primary_spells[primary_tree_id]),
    }
    validate_talent_manifest({"name": class_name, **build})
    class_id = CLASS_META[class_name]["class_id"]
    class_glyphs = sorted(
        (row for row in glyph_payload["glyphs"] if int(row["classId"]) == class_id),
        key=lambda row: (int(row["requiredLevel"]), str(row["name"])),
    )
    glyph_by_char = {chars[10 + index]: row for index, row in enumerate(class_glyphs)}
    glyph_chars = re.findall(r"\d(.)", glyph_part)
    glyphs = [int(glyph_by_char[char]["itemId"]) for char in glyph_chars]
    if len(glyphs) != 9:
        raise ValueError(f"{class_name}: expected nine Icy Veins glyphs, found {len(glyphs)}")
    return build, glyphs


def result_reference(
    result_text: str, *, preferred_key: str | None = None
) -> dict[str, Any] | None:
    matches = re.findall(
        r'key:\s*"([^"]+)"\s*value:\s*\{([^}]+)\}',
        result_text,
        flags=re.DOTALL,
    )
    if not matches:
        return None
    if preferred_key:
        candidates = [row for row in matches if row[0] == preferred_key]
        if len(candidates) != 1:
            raise ValueError(f"pinned simulator result row missing: {preferred_key}")
        preferred = candidates[0]
    else:
        preferred = next(
            (row for row in matches if row[0].endswith("-Average-Default")),
            matches[0],
        )
    metrics = {name: float(value) for name, value in re.findall(r"\b(dps|tps|hps):\s*([0-9.]+)", preferred[1])}
    return {"result_key": preferred[0], "metrics": metrics}


def aliases(target_id: str, class_name: str, spec_name: str, feral_variant: str | None) -> list[str]:
    values = {target_id, f"{spec_name}_{class_name}", target_id.replace("_death_knight", "_dk")}
    if feral_variant:
        values.update({f"feral_{feral_variant}", f"feral_druid_{feral_variant}"})
    if target_id == "protection_paladin":
        values.update({"protection", "prot_paladin", "prot_pally"})
    if target_id == "protection_warrior":
        values.update({"prot_warrior"})
    if target_id.endswith("_hunter"):
        values.add(spec_name.replace("beast_mastery", "bm").replace("marksmanship", "mm").replace("survival", "sv"))
    return sorted(value for value in values if value)


def pet_for(target_id: str, index: int) -> dict[str, Any] | None:
    if not target_id.endswith("_hunter"):
        return None
    return {
        "id_offset": 100 + index,
        "entry": 8959,
        "modelid": 4124,
        "created_by_spell": 0,
        "name": f"Specwolf{index:02d}",
        "level": 85,
        "slot": 0,
        "active": 1,
        # Match sim/hunter/survival/survival_test.go's numeric fixture rather
        # than the UI preset's different ferocityDefault allocation.
        "spells": [
            2649,
            17253,
            61683,
            {"id": 23145, "active": 193},
            53184,
            53186,
            61681,
            53205,
            {"id": 53401, "active": 193},
            {"id": 53434, "active": 193},
            62760,
        ],
    }


def archetype_for(class_name: str, role: str) -> str:
    if role == "tank":
        return "tank"
    if role == "healer":
        return "healer"
    return f"dps_{CLASS_META[class_name]['archetype']}"


def action_spell_ids(target_id: str, class_id: int, build: dict[str, Any]) -> list[int]:
    action_profiles = json.loads(ACTION_PROFILES_PATH.read_text(encoding="utf-8"))
    class_spells = action_profiles["action_profile_spells_by_class"].get(str(class_id), [])
    selected = [row["spell_id"] for row in build["talents"]]
    tuned_actions = LEGACY_TUNED_ACTION_SPELL_IDS.get(target_id, [])
    qualification_actions = QUALIFICATION_TUNED_ACTION_SPELL_IDS.get(target_id, [])
    runtime_actions = RUNTIME_ACTION_SPELL_IDS.get(target_id, [])
    persistent_setup = PERSISTENT_SETUP_SPELL_IDS.get(target_id, [])
    return sorted(
        {
            int(spell)
            for spell in (
                class_spells
                + build["primary_tree_spells"]
                + selected
                + tuned_actions
                + qualification_actions
                + runtime_actions
                + persistent_setup
            )
            if int(spell) > 0
        }
    )


def build_catalogs(refresh_sources: bool) -> dict[str, dict[str, Any]]:
    if not refresh_sources:
        paths = [TARGET_CATALOG_PATH, REFERENCE_CATALOG_PATH, CALIBRATION_CATALOG_PATH, PAIRWISE_CATALOG_PATH]
        if not all(path.is_file() for path in paths):
            raise FileNotFoundError("checked-in Phase 1 catalogs are missing; run with --refresh-sources")
        payloads = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in paths}
        validate_catalogs(payloads, check_linked=True)
        return payloads

    glyph_payload_bytes = fetch_bytes(f"{ICY_JSON}/glyphs.json")
    glyph_payload = json.loads(glyph_payload_bytes)
    tree_cache: dict[str, tuple[list[dict[str, Any]], bytes]] = {}
    proto_cache: dict[str, tuple[str, bytes]] = {}
    icy_cache: dict[str, tuple[dict[str, Any], bytes]] = {}
    targets: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    wowsims_gear_document = json.loads(
        WOWSIMS_GEAR_PROFILES_PATH.read_text(encoding="utf-8")
    )
    wowsims_gear_profiles = wowsims_gear_document.get("profiles", {})

    for index, (target_id, class_name, spec_name, role, bot_name, feral_variant) in enumerate(TARGETS, start=1):
        class_id = CLASS_META[class_name]["class_id"]
        preset_path = f"ui/{class_name}/{spec_name}/presets.ts"
        preset_bytes = fetch_bytes(f"{WOWSIMS_RAW}/{preset_path}")
        preset_text = preset_bytes.decode()
        if class_name not in tree_cache:
            tree_path = f"ui/core/talents/trees/{class_name}.json"
            tree_bytes = fetch_bytes(f"{WOWSIMS_RAW}/{tree_path}")
            tree_cache[class_name] = (json.loads(tree_bytes), tree_bytes)
            proto_path = f"proto/{class_name}.proto"
            proto_bytes = fetch_bytes(f"{WOWSIMS_RAW}/{proto_path}")
            proto_cache[class_name] = (proto_bytes.decode(), proto_bytes)
        tree_payload, tree_bytes = tree_cache[class_name]
        proto_text, proto_bytes = proto_cache[class_name]
        support = WOWSIMS_SUPPORT.get(target_id, "launched")
        research_pass = "unsupported_second_pass" if target_id in ICY_BUILD else "consolidated_all_target_pass"
        guide_bytes = fetch_bytes(GUIDE_URL[target_id])
        source_assets = [
            source_record(f"{WOWSIMS_RAW}/{preset_path}", preset_bytes),
            source_record(f"{WOWSIMS_RAW}/ui/core/talents/trees/{class_name}.json", tree_bytes),
            source_record(f"{WOWSIMS_RAW}/proto/{class_name}.proto", proto_bytes),
            source_record(GUIDE_URL[target_id], guide_bytes),
        ]
        if target_id in ICY_BUILD:
            icy_class, encoded, guide_url = ICY_BUILD[target_id]
            if icy_class not in icy_cache:
                icy_bytes = fetch_bytes(f"{ICY_JSON}/{icy_class}.json")
                icy_cache[icy_class] = (json.loads(icy_bytes), icy_bytes)
            icy_payload, icy_bytes = icy_cache[icy_class]
            build, glyphs = parse_icy_build(icy_class, encoded, icy_payload, glyph_payload)
            source_assets.extend(
                [
                    source_record(f"{ICY_JSON}/{icy_class}.json", icy_bytes),
                    source_record(f"{ICY_JSON}/glyphs.json", glyph_payload_bytes),
                ]
            )
            talent_source = {"provider": "Icy Veins", "url": guide_url, "encoded_build": encoded}
        else:
            build, glyphs, talent_string = parse_wowsims_talents(target_id, class_name, spec_name, preset_text, tree_payload, proto_text)
            talent_source = {"provider": "WoWSims", "path": preset_path, "talent_string": talent_string}

        gear_path = GEAR_PATH[target_id]
        gear_bytes = fetch_bytes(f"{WOWSIMS_RAW}/{gear_path}")
        source_assets.append(source_record(f"{WOWSIMS_RAW}/{gear_path}", gear_bytes))
        apl_path = APL_PATH.get(target_id)
        if apl_path:
            apl_bytes = fetch_bytes(f"{WOWSIMS_RAW}/{apl_path}")
            source_assets.append(source_record(f"{WOWSIMS_RAW}/{apl_path}", apl_bytes))
        result = None
        test_path = None
        result_path = None
        test_bytes = None
        if target_id in RESULT_META:
            test_path, result_path = RESULT_META[target_id]
            test_bytes = fetch_bytes(f"{WOWSIMS_RAW}/{test_path}")
            result_bytes = fetch_bytes(f"{WOWSIMS_RAW}/{result_path}")
            source_assets.extend(
                [source_record(f"{WOWSIMS_RAW}/{test_path}", test_bytes), source_record(f"{WOWSIMS_RAW}/{result_path}", result_bytes)]
            )
            result = result_reference(
                result_bytes.decode(),
                preferred_key=RESULT_KEY_OVERRIDE.get(target_id),
            )
            if target_id in RESULT_TALENT_OVERRIDE:
                talent_source = {
                    "provider": "WoWSims",
                    "path": test_path,
                    "talent_string": RESULT_TALENT_OVERRIDE[target_id],
                    "selection_basis": "numeric_result_fixture",
                }

        pet = pet_for(target_id, index)
        consume_profile = (
            controlled_consumable_profile(target_id)
            if target_id in CONTROLLED_DPS_SPECS
            else None
        )
        consumables = (
            [int(row["item_id"]) for row in consume_profile["inventory"]]
            if consume_profile
            else [58085, 58086, 58257]
        )
        runtime_gear_profile = canonical_gear_profile_id(target_id)
        exact_gear_profile = wowsims_gear_profiles.get(runtime_gear_profile)
        runtime_race = {
            "demonology_warlock": 2,
            "shadow_priest": 8,
            "survival_hunter": 2,
        }.get(target_id, CLASS_META[class_name]["race"])
        provisioning_bot = {
            "account": f"ASPC{index:02d}",
            "name": bot_name,
            "role": role,
            "class_spec": target_id,
            "race": runtime_race,
            "class": class_id,
            "level": 85,
            "gear_profile": runtime_gear_profile,
            "gear_profile_id": runtime_gear_profile,
            "glyphs": glyphs,
            "consumable_item_ids": consumables,
            **build,
        }
        if consume_profile:
            provisioning_bot["controlled_consumable_profile"] = consume_profile
            provisioning_bot["consumables"] = [
                dict(row) for row in consume_profile["inventory"]
            ]
        reconcile_rogue_poison_provisioning(
            [{"spec_target_id": target_id, "provisioning_bot": provisioning_bot}]
        )
        if pet:
            provisioning_bot["pet"] = pet
        spell_ids = action_spell_ids(target_id, class_id, build)
        runtime_spec_tag = RUNTIME_PROFILE_SPEC_TAG.get(target_id, target_id)
        capabilities = ROLE_CAPABILITIES[role] + CLASS_UTILITY[class_name] + SPEC_BEHAVIOR.get(target_id, [])
        targets.append(
            {
                "spec_target_id": target_id,
                "class_id": class_id,
                "class_name": class_name,
                "spec_name": spec_name,
                "role": role,
                "feral_variant": feral_variant,
                "accepted_aliases": aliases(target_id, class_name, spec_name, feral_variant),
                "runtime_join_key": target_id,
                "lease_key": f"all_spec_candidate_pool:{target_id}",
                "provisioning_bot": provisioning_bot,
                "talent_build": build,
                "glyph_item_ids": glyphs,
                "gear_profile_id": runtime_gear_profile,
                "consumable_item_ids": list(provisioning_bot["consumable_item_ids"]),
                "pet_form_stance_presence": SPEC_BEHAVIOR.get(target_id, []),
                "action_profile_identity": f"cata_434:{class_id}:{target_id}",
                "action_profile_spell_ids": spell_ids,
                "runtime_rotation_profile": {
                    "class_id": class_id,
                    "spec_tag": runtime_spec_tag,
                    "role": role,
                    "identity": f"{class_id}:{runtime_spec_tag}:{role}",
                    "authority": "world_db_bot_rotation_profile",
                    "sql_path": RUNTIME_ROTATION_SQL,
                    "action_priority_source": apl_path or GUIDE_URL[target_id],
                },
                "calibration_type": "controlled_party_damage" if role == "healer" else "single_target_300s",
                "capability_contract": sorted(set(capabilities)),
                "required_rotation_groups": [
                    "opener",
                    "single_target_priority",
                    "cooldowns",
                    "execute_or_low_health",
                    "movement",
                    "separate_aoe",
                    "interrupts_and_utility",
                    "resource_and_form_pet_state",
                ],
                "reference_id": f"cata_p4:{target_id}",
            }
        )
        expected_output: dict[str, Any]
        if role == "healer":
            expected_output = {
                "type": "deterministic_controlled_party_damage",
                "success": ["zero_preventable_deaths", "damage_events_covered", "mana_state_recorded", "dispel_and_emergency_response_recorded"],
                "external_hps_floor": None,
            }
        elif result:
            expected_output = {"type": "simulator_metrics", **result}
        else:
            expected_output = {"type": "phase4_guide_priority_reference", "numeric_floor": None}
        gear_reference = {
            "phase": "phase_4",
            "gear_profile_id": runtime_gear_profile,
            "runtime_profile_id": runtime_gear_profile,
            "runtime_builder": "tools/bot_ml/build_validation_gear_profiles.py",
            "runtime_manifest": gear_profile_runtime_manifest(target_id),
            "simulator_preset": {
                "path": gear_path,
                "phase": "phase_4" if any(token in gear_path.lower() for token in ("p4", "t13")) else "best_executable_legacy_preset",
            },
        }
        if isinstance(exact_gear_profile, dict):
            exact_source = exact_gear_profile.get("source") or {}
            gear_reference.update(
                {
                    "source_sha256": exact_source.get("sha256"),
                    "source_snapshot": exact_source.get("snapshot"),
                    "transform_schema": TRANSFORM_SCHEMA,
                    "transformed_manifest_sha256": exact_gear_profile.get(
                        "transformed_manifest_sha256"
                    ),
                    "permanent_enchant_applicability_authority": (
                        ENCHANT_APPLICABILITY_AUTHORITY
                    ),
                }
            )
            if test_path and test_bytes:
                test_snapshot = (
                    "experiments/configs/wowsims_cata_p4_gear_sources/"
                    f"{runtime_gear_profile}.test.go"
                )
                gear_reference.update(
                    {
                        "numeric_fixture_test_source_sha256": hashlib.sha256(
                            test_bytes
                        ).hexdigest(),
                        "numeric_fixture_test_snapshot": test_snapshot,
                        "numeric_fixture_gear_label": (
                            selected_numeric_fixture_gear_label(
                                {
                                    "expected_output": expected_output,
                                    "gear": gear_reference,
                                },
                                test_bytes.decode("utf-8"),
                            )
                        ),
                    }
                )
        references.append(
            {
                "reference_id": f"cata_p4:{target_id}",
                "spec_target_id": target_id,
                "research_pass": research_pass,
                "review_status": "reviewed",
                "simulator_support": support,
                "provider": "WoWSims" if support != "unsupported" else "WoWSims gear plus Icy Veins role reference",
                "provider_revision": WOWSIMS_REVISION,
                "repository": WOWSIMS_REPOSITORY,
                "guide_url": GUIDE_URL[target_id],
                "gear": gear_reference,
                "apl": {"path": apl_path, "available": bool(apl_path)},
                "talents": talent_source,
                "test": test_path,
                "results": result_path,
                "source_assets": source_assets,
                "reference_conditions": {
                    "level": 85,
                    "single_target_duration_seconds": 300,
                    "duration_variation_seconds": 5,
                    "raid_buffs": "full_simulator_reference_live_conditions_recorded_separately",
                    "consumables": "simulator_enabled_live_clone_capabilities_recorded",
                    "aoe": "separate_mode_not_mixed_with_single_target",
                },
                "rotation_research": {
                    "priority_source": apl_path or GUIDE_URL[target_id],
                    "cooldowns": "explicit_required_rotation_group",
                    "execute": "explicit_required_rotation_group_even_when_not_applicable",
                    "movement": "explicit_required_rotation_group",
                    "aoe": "separate_explicit_required_rotation_group",
                    "pet_form_behavior": SPEC_BEHAVIOR.get(target_id, []),
                    "interrupts_utility": CLASS_UTILITY[class_name],
                },
                "expected_output": expected_output,
                "known_trinitycore_deviations": [
                    "TrinityCore 4.3.4 mechanics and bot scheduling differ from the simulator engine",
                    "live clones do not assume every simulator profession, racial, prepot, or raid-buff condition",
                    "the 75 percent hard floor is applied only after Phase 2 establishes compatible live conditions",
                ]
                + (["WoWSims does not publish a numeric result for this specialization"] if support == "unsupported" else [])
                + (
                    ["the pinned executable simulator preset predates Phase 4; the canonical runtime profile is independently generated from Phase 4 item data"]
                    if not any(token in gear_path.lower() for token in ("p4", "t13"))
                    else []
                ),
            }
        )
        calibration_rows.append(
            {
                "spec_target_id": target_id,
                "primary": {
                    "scenario_id": f"calibration:{target_id}:primary",
                    "type": "controlled_party_damage" if role == "healer" else "single_target",
                    "scored_window_seconds": 300,
                    "window_tolerance_seconds": 5,
                    "hard_floor_ratio": 0.75,
                    "optimization_target_ratio": 0.80,
                    "individual_floor_enforced": True,
                },
                "aoe": {
                    "scenario_id": f"calibration:{target_id}:aoe",
                    "type": "separate_aoe_mode",
                    "mixed_with_primary": False,
                },
            }
        )

    target_catalog = {
        "schema": "all_spec_targets_cata_p4_v1",
        "target_count": 31,
        "role_counts": {"tank": 4, "healer": 5, "dps": 22},
        "runtime_join_key": "character_bot_pool.class_spec",
        "candidate_pool_scenario_id": "all_spec_candidate_pool",
        "source_revision": WOWSIMS_REVISION,
        "targets": targets,
    }
    reference_catalog = {
        "schema": "all_spec_references_cata_p4_v1",
        "research_contract": {
            "first_pass": "one consolidated pass across all ten classes and all 31 targets",
            "second_pass_scope": sorted(ICY_BUILD),
            "second_pass_reason": "WoWSims explicitly marks these healer/Frost Mage records unsupported",
            "guide_prose_is_sole_runtime_source": False,
        },
        "references": references,
    }
    calibration_catalog = {
        "schema": "all_spec_calibration_scenarios_v1",
        "acceptance_contract": {
            "single_target_scored_window_seconds": 300,
            "single_target_window_tolerance_seconds": 5,
            "hard_floor_ratio": 0.75,
            "optimization_target_ratio": 0.80,
            "aoe_is_separate": True,
            "healer_damage_model": "deterministic_controlled_party_damage",
        },
        "scenarios": calibration_rows,
    }
    tanks = [row[0] for row in TARGETS if row[3] == "tank"]
    healers = [row[0] for row in TARGETS if row[3] == "healer"]
    dps = [row[0] for row in TARGETS if row[3] == "dps"]
    parties = []
    for pair_index, (tank, healer) in enumerate((tank, healer) for tank in tanks for healer in healers):
        trio = [dps[(pair_index * 3 + offset) % len(dps)] for offset in range(3)]
        parties.append({"party_id": f"stonecore_pair_{pair_index + 1:02d}", "tank": tank, "healer": healer, "dps": trio})
    pairwise_catalog = {
        "schema": "stonecore_pairwise_constraints_v1",
        "composition": {"tank": 1, "healer": 1, "dps": 3},
        "certification": "strict_uninterrupted_current_manifest_full_clear",
        "diagnostic_segments_certify": False,
        "concurrency_before_isolation_gate": "prohibited",
        "constraints": [
            "every tank-healer pair appears exactly once",
            "all party members use unique lease keys",
            "all three DPS slots are distinct within a party",
            "only calibration-qualified targets may enter certification",
        ],
        "parties": parties,
    }
    payloads = {
        TARGET_CATALOG_PATH.name: target_catalog,
        REFERENCE_CATALOG_PATH.name: reference_catalog,
        CALIBRATION_CATALOG_PATH.name: calibration_catalog,
        PAIRWISE_CATALOG_PATH.name: pairwise_catalog,
    }
    validate_catalogs(payloads, check_linked=False)
    return payloads


def validate_catalogs(payloads: dict[str, dict[str, Any]], *, check_linked: bool) -> None:
    target_catalog = payloads[TARGET_CATALOG_PATH.name]
    reference_catalog = payloads[REFERENCE_CATALOG_PATH.name]
    calibration_catalog = payloads[CALIBRATION_CATALOG_PATH.name]
    pairwise_catalog = payloads[PAIRWISE_CATALOG_PATH.name]
    targets = target_catalog["targets"]
    ids = [row["spec_target_id"] for row in targets]
    if len(targets) != 31 or len(set(ids)) != 31:
        raise ValueError("Phase 1 requires exactly 31 unique target rows")
    validate_rogue_poison_provisioning(targets)
    validate_controlled_dps_consumable_provisioning(targets)
    roles = Counter(row["role"] for row in targets)
    if dict(roles) != {"tank": 4, "healer": 5, "dps": 22}:
        raise ValueError("Phase 1 role counts must be 4 tanks, 5 healers, and 22 DPS")
    aliases_seen: dict[str, str] = {}
    runtime_profiles_seen: set[str] = set()
    for row in targets:
        validate_talent_manifest({"name": row["spec_target_id"], **row["talent_build"]})
        if not 3 <= len(row["glyph_item_ids"]) <= 9 or not row["action_profile_spell_ids"]:
            raise ValueError(f"{row['spec_target_id']}: incomplete provisioning/profile link")
        expected_gear_profile_id = canonical_gear_profile_id(row["spec_target_id"])
        provisioning = row.get("provisioning_bot") or {}
        if (
            row.get("gear_profile_id") != expected_gear_profile_id
            or provisioning.get("gear_profile_id") != expected_gear_profile_id
            or provisioning.get("gear_profile") != expected_gear_profile_id
        ):
            raise ValueError(
                f"{row['spec_target_id']}: canonical gear profile identity mismatch"
            )
        runtime_profile = row.get("runtime_rotation_profile") or {}
        expected_runtime_identity = (
            f"{row['class_id']}:{RUNTIME_PROFILE_SPEC_TAG.get(row['spec_target_id'], row['spec_target_id'])}:{row['role']}"
        )
        if runtime_profile.get("identity") != expected_runtime_identity or runtime_profile.get("sql_path") != RUNTIME_ROTATION_SQL:
            raise ValueError(f"{row['spec_target_id']}: incomplete runtime rotation profile link")
        if expected_runtime_identity in runtime_profiles_seen:
            raise ValueError(f"duplicate runtime rotation profile identity: {expected_runtime_identity}")
        runtime_profiles_seen.add(expected_runtime_identity)
        required_action_spells = set().union(
            LEGACY_TUNED_ACTION_SPELL_IDS.get(row["spec_target_id"], []),
            QUALIFICATION_TUNED_ACTION_SPELL_IDS.get(row["spec_target_id"], []),
            RUNTIME_ACTION_SPELL_IDS.get(row["spec_target_id"], []),
            PERSISTENT_SETUP_SPELL_IDS.get(row["spec_target_id"], []),
        )
        if not required_action_spells <= set(row["action_profile_spell_ids"]):
            raise ValueError(f"{row['spec_target_id']}: runtime action/setup spells are not provisioned")
        for alias in row["accepted_aliases"]:
            previous = aliases_seen.setdefault(alias, row["spec_target_id"])
            if previous != row["spec_target_id"]:
                raise ValueError(f"alias {alias!r} conflicts between {previous} and {row['spec_target_id']}")
    references = reference_catalog["references"]
    targets_by_id = {row["spec_target_id"]: row for row in targets}
    wowsims_gear_document = json.loads(
        WOWSIMS_GEAR_PROFILES_PATH.read_text(encoding="utf-8")
    )
    wowsims_gear_profiles = wowsims_gear_document.get("profiles", {})
    wowsims_slot_map = [int(value) for value in wowsims_gear_document.get("slot_map", [])]
    selected_numeric_dps = set(
        json.loads(DPS_ACCEPTANCE_PATH.read_text(encoding="utf-8")).get(
            "dps_targets", []
        )
    )
    if {row["spec_target_id"] for row in references} != set(ids) or any(row["review_status"] != "reviewed" for row in references):
        raise ValueError("every target requires reviewed reference provenance")
    for row in references:
        source_urls = {asset.get("url") for asset in row.get("source_assets", [])}
        if row.get("guide_url") not in source_urls:
            raise ValueError(f"{row['spec_target_id']}: guide provenance is not content-addressed")
        if any(
            not asset.get("url") or not re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256") or "")) or int(asset.get("byte_count") or 0) <= 0
            for asset in row.get("source_assets", [])
        ):
            raise ValueError(f"{row['spec_target_id']}: incomplete source hash provenance")
        gear = row.get("gear") or {}
        expected_gear_profile_id = canonical_gear_profile_id(row["spec_target_id"])
        if (
            gear.get("phase") != "phase_4"
            or gear.get("gear_profile_id") != expected_gear_profile_id
            or gear.get("runtime_profile_id") != expected_gear_profile_id
            or gear.get("runtime_manifest")
            != gear_profile_runtime_manifest(row["spec_target_id"])
        ):
            raise ValueError(
                f"{row['spec_target_id']}: canonical gear profile identity mismatch"
            )
        if expected_gear_profile_id in wowsims_gear_profiles:
            profile = wowsims_gear_profiles.get(expected_gear_profile_id) or {}
            binding = validate_profile_source_binding(
                profile=profile, reference=row, slot_map=wowsims_slot_map
            )
            if not binding["passed"]:
                raise ValueError(
                    f"{row['spec_target_id']}: WoWSims gear source identity mismatch: "
                    f"{[key for key, value in binding['checks'].items() if not value]}"
                )
            if row["spec_target_id"] in selected_numeric_dps:
                legality = validate_profile_local_legality(
                    profile=profile,
                    target=targets_by_id[row["spec_target_id"]],
                    slot_map=wowsims_slot_map,
                    dbc_dir=DBC_DIR,
                )
                if not legality["passed"]:
                    raise ValueError(
                        f"{row['spec_target_id']}: numeric DPS target gear is not "
                        f"locally player-legal: {legality['failure_reasons']}"
                    )
        elif row["spec_target_id"] in selected_numeric_dps:
            raise ValueError(
                f"{row['spec_target_id']}: numeric DPS target requires exact pinned WoWSims gear"
            )
    if {row["spec_target_id"] for row in calibration_catalog["scenarios"]} != set(ids):
        raise ValueError("every target requires calibration scenarios")
    parties = pairwise_catalog["parties"]
    if len(parties) != 20 or len({(row["tank"], row["healer"]) for row in parties}) != 20:
        raise ValueError("pairwise catalog requires all 20 tank-healer pairs")
    if set(value for row in parties for value in row["dps"]) != {row["spec_target_id"] for row in targets if row["role"] == "dps"}:
        raise ValueError("pairwise catalog must cover every DPS target")
    if check_linked:
        try:
            from .build_baseline_inventory import rotation_tuples
        except ImportError:
            from build_baseline_inventory import rotation_tuples

        expected_catalog = str(TARGET_CATALOG_PATH.relative_to(REPO_ROOT))
        runtime_sql_path = REPO_ROOT / RUNTIME_ROTATION_SQL
        declared_profiles = {
            (int(row["class_id"]), str(row["spec_tag"]), str(row["role"]))
            for row in rotation_tuples([runtime_sql_path], REPO_ROOT)
        }
        expected_profiles = {
            (
                int(row["class_id"]),
                str(row["runtime_rotation_profile"]["spec_tag"]),
                str(row["role"]),
            )
            for row in targets
        }
        if declared_profiles != expected_profiles:
            raise ValueError("runtime SQL does not declare exactly 31 canonical rotation profiles")
        provisioning = json.loads(PROVISIONING_PATH.read_text(encoding="utf-8"))
        actions = json.loads(ACTION_PROFILES_PATH.read_text(encoding="utf-8"))
        combat_loot = json.loads(COMBAT_LOOT_PATH.read_text(encoding="utf-8"))
        if provisioning.get("canonical_target_catalog") != expected_catalog:
            raise ValueError("provisioning config is not linked to the canonical target catalog")
        expected_actions = {row["spec_target_id"]: row["action_profile_spell_ids"] for row in targets}
        if actions.get("canonical_target_catalog") != expected_catalog or actions.get("action_profile_spells_by_spec") != expected_actions:
            raise ValueError("action profiles are not complete for all canonical targets")
        expected_archetypes = {row["spec_target_id"]: archetype_for(row["class_name"], row["role"]) for row in targets}
        if combat_loot.get("canonical_target_catalog") != expected_catalog or combat_loot.get("class_spec_archetypes") != expected_archetypes:
            raise ValueError("gear archetypes are not complete for all canonical targets")


def update_linked_configs(target_catalog: dict[str, Any]) -> None:
    provisioning = json.loads(PROVISIONING_PATH.read_text(encoding="utf-8"))
    provisioning["canonical_target_catalog"] = str(TARGET_CATALOG_PATH.relative_to(REPO_ROOT))
    provisioning["canonical_candidate_pool_scenario_id"] = "all_spec_candidate_pool"
    PROVISIONING_PATH.write_text(json.dumps(provisioning, indent=2) + "\n", encoding="utf-8")

    actions = json.loads(ACTION_PROFILES_PATH.read_text(encoding="utf-8"))
    actions["canonical_target_catalog"] = str(TARGET_CATALOG_PATH.relative_to(REPO_ROOT))
    actions["action_profile_spells_by_spec"] = {
        row["spec_target_id"]: row["action_profile_spell_ids"] for row in target_catalog["targets"]
    }
    actions["runtime_ml_control"] = "disabled_teacher_policy_validation_only"
    ACTION_PROFILES_PATH.write_text(json.dumps(actions, indent=2) + "\n", encoding="utf-8")

    combat_loot = json.loads(COMBAT_LOOT_PATH.read_text(encoding="utf-8"))
    combat_loot["canonical_target_catalog"] = str(TARGET_CATALOG_PATH.relative_to(REPO_ROOT))
    combat_loot["class_spec_archetypes"] = {
        row["spec_target_id"]: archetype_for(row["class_name"], row["role"]) for row in target_catalog["targets"]
    }
    combat_loot["glyph_source"] = str(TARGET_CATALOG_PATH.relative_to(REPO_ROOT))
    COMBAT_LOOT_PATH.write_text(json.dumps(combat_loot, indent=2) + "\n", encoding="utf-8")


def write_configs(payloads: dict[str, dict[str, Any]]) -> None:
    path_by_name = {
        TARGET_CATALOG_PATH.name: TARGET_CATALOG_PATH,
        REFERENCE_CATALOG_PATH.name: REFERENCE_CATALOG_PATH,
        CALIBRATION_CATALOG_PATH.name: CALIBRATION_CATALOG_PATH,
        PAIRWISE_CATALOG_PATH.name: PAIRWISE_CATALOG_PATH,
    }
    for name, payload in payloads.items():
        path_by_name[name].write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    update_linked_configs(payloads[TARGET_CATALOG_PATH.name])


def reconcile_checked_in_rogue_poison_catalog() -> dict[str, dict[str, Any]]:
    paths = [
        TARGET_CATALOG_PATH,
        REFERENCE_CATALOG_PATH,
        CALIBRATION_CATALOG_PATH,
        PAIRWISE_CATALOG_PATH,
    ]
    payloads = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in paths
    }
    target_catalog = payloads[TARGET_CATALOG_PATH.name]
    reconcile_rogue_poison_provisioning(target_catalog["targets"])
    validate_catalogs(payloads, check_linked=True)
    rendered = json.dumps(target_catalog, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=TARGET_CATALOG_PATH.parent,
        prefix=f".{TARGET_CATALOG_PATH.name}.", suffix=".tmp", delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    temporary_path.replace(TARGET_CATALOG_PATH)
    return payloads


def reconcile_checked_in_controlled_consumable_catalog() -> dict[str, dict[str, Any]]:
    paths = [
        TARGET_CATALOG_PATH,
        REFERENCE_CATALOG_PATH,
        CALIBRATION_CATALOG_PATH,
        PAIRWISE_CATALOG_PATH,
    ]
    payloads = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in paths
    }
    target_catalog = payloads[TARGET_CATALOG_PATH.name]
    reconcile_controlled_dps_consumable_provisioning(target_catalog["targets"])
    reconcile_rogue_poison_provisioning(target_catalog["targets"])
    validate_controlled_dps_consumable_provisioning(target_catalog["targets"])
    validate_rogue_poison_provisioning(target_catalog["targets"])
    rendered = json.dumps(target_catalog, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=TARGET_CATALOG_PATH.parent,
        prefix=f".{TARGET_CATALOG_PATH.name}.", suffix=".tmp", delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    temporary_path.replace(TARGET_CATALOG_PATH)
    return payloads


def write_bundle(output_dir: Path, payloads: dict[str, dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("*.json"):
        stale.unlink()
    members = []
    for name, payload in sorted(payloads.items()):
        data = canonical_bytes(payload)
        output_path = output_dir / name
        output_path.write_bytes(data)
        members.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "byte_count": len(data)})
    manifest = {
        "schema": "all_spec_phase1_catalog_bundle_v1",
        "target_count": 31,
        "gate_passed": True,
        "bundle_members": members,
        "bundle_hash": canonical_hash(members),
    }
    (output_dir / "manifest.json").write_bytes(canonical_bytes(manifest))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate Phase 1 all-spec catalogs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--refresh-sources", action="store_true")
    parser.add_argument("--reconcile-rogue-poisons", action="store_true")
    parser.add_argument("--reconcile-controlled-consumables", action="store_true")
    args = parser.parse_args()
    if args.reconcile_controlled_consumables:
        if args.refresh_sources or args.reconcile_rogue_poisons:
            parser.error("controlled consumable reconciliation is exclusive")
        payloads = reconcile_checked_in_controlled_consumable_catalog()
        print(json.dumps({
            "controlled_consumable_contract_valid": True,
            "target_count": len(payloads[TARGET_CATALOG_PATH.name]["targets"]),
            "reconciled": str(TARGET_CATALOG_PATH),
        }, sort_keys=True))
        return 0
    if args.reconcile_rogue_poisons:
        if args.refresh_sources:
            parser.error("--reconcile-rogue-poisons and --refresh-sources are exclusive")
        payloads = reconcile_checked_in_rogue_poison_catalog()
        print(json.dumps({
            "gate_passed": True,
            "target_count": len(payloads[TARGET_CATALOG_PATH.name]["targets"]),
            "reconciled": str(TARGET_CATALOG_PATH),
        }, sort_keys=True))
        return 0
    payloads = build_catalogs(args.refresh_sources)
    if args.refresh_sources:
        write_configs(payloads)
        validate_catalogs(payloads, check_linked=True)
    write_bundle(args.output_dir, payloads)
    print(json.dumps({"gate_passed": True, "target_count": 31, "output_dir": str(args.output_dir)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
