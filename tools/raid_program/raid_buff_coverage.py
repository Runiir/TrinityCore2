"""Raid buff and debuff coverage of every shard of a raid composition.

Scores each shard's roster against the 23 categories of WoWSims ui/core/components/inputs/buffs_debuffs.ts
at the pinned provider revision (RAID_BUFFS_CONFIG and DEBUFFS_CONFIG). The decision document scored 20 of
them; every category this roster can miss is in both lists, so its N/20 is 20 minus the missing ones.

Two columns per shard:
- provisioned: some member has the provider. A class spell counts when the member knows it in the shard's
  active spec (raid_loadout_spells.loadout_known_spells: the active spec's talents and tree spells, every
  talent group's profile and group-level spells, minus the inactive spec's own); `specs` narrows form-bound
  spells. Talents of the active spec, the pet's spells, totems and raid haste count when known.
- runtime: an enabled rotation row or a runtime code contract casts it. This is not proof that the buff is
  up: a gated row (enemy count, ally, target or self health) casts only when its gate opens, and a category
  whose every runtime provider is gated or cast once is reported as a caveat. A spell counts only when the
  member knows it and it is
  * an enabled bot_rotation_action row of the member's profile. This tool never reads the world DB: the rows
    come from a checked-in export (RUNTIME_ACTIONS_DIR/<raid>_<mode>.json) of the live evidence's
    valid_action_mask_json, which holds one candidate per row of the profile the raid resolver evaluated
    (LoadDbSnapshot selects `p.enabled = 1 AND a.enabled = 1`, the raid-scope BotRaidRotationOverrides edit
    rows, BuildCandidates iterates every profile spell). --export-runtime-actions writes it from a DVC-tracked
    evidence tarball. The mask publishes no numeric gates, so the export infers each row's gate kinds from
    its category and the gate rejections observed in the evidence (inferred_gates);
  * a route readiness requirement row (TryValidationRouteReadiness). Party-wide rows are cast once
    (castParty `cast_once`) and never recast after a death;
  * a BotPersistentSelfBuffContract row or the raid rogue poison setup (both restored before each pull);
  * in a canonical-composition raid (BotCanonicalRaidScope), the round 5 runtime of class owner C, credited
    while its source is present: the persistent raid buffs (BotRaidPersistentBuffs.h: Fortitude, Might in
    place of Kings under a Mark of the Wild druid, Retribution Aura, Devotion Aura; they replace the
    Fortitude and Kings readiness rows), the boss lust fallback (BotRaidBossLust.h) and the major armor
    upkeep rows (BotRaidMajorArmor.h: Faerie Fire on bosses);
  * a runtime totem (TryEnsureCombatTotems: Elemental places Wrath of Air and Mana Spring and no earth totem;
    any other tree Strength of Earth, Healing Stream and, in a raid, Wrath of Air when another member has
    Hunting Party 53290 or Improved Icy Talons 55610 (BotRaidShamanTotems.h), otherwise Windfury); or
  * raid haste on an encounter whose bot code casts it (LUST_DUTY_ENCOUNTERS, or the canonical fallback).
  A talent counts when it is passive or one of its triggers is a runtime cast (or a passive talent); a pet
  spell when the pet autocasts it (active 0xC1), matched by aura signature (Ravage 50518 applies Acid Spit
  55749's aura 87, physical, +4). The JSON action profiles (experiments/configs/cata_434_action_profiles.json)
  only provision spells; they never count as runtime.

    pixi run python -m tools.raid_program.raid_buff_coverage [--full]
    pixi run python -m tools.raid_program.raid_buff_coverage --export-runtime-actions EVIDENCE.tar.gz --run RUN
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tarfile
from pathlib import Path
from typing import Any, Iterator, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
BOTS = REPO_ROOT / "src/server/game/Bots"
DEFAULT_COMPOSITION = REPO_ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
DEFAULT_DBC_DIR = REPO_ROOT / "data/dbc/enUS"
# Not under raid_compositions: that directory is read as compositions and is a raid_shard_provisioning dep.
RUNTIME_ACTIONS_DIR = REPO_ROOT / "experiments/configs/raid_runtime_actions"
RUNTIME_ACTIONS_SCHEMA = "raid_runtime_rotation_actions_v2"
PROVIDER_REVISION = "70d87383a9b92f30fb9e370c4676d3ce33b6e6b6"
DECISION_SCALE = 20
FERAL = ("feral_druid_tank", "feral_druid_dps")
OTHER_MELEE_HASTE = (53290, 55610)  # BotRaidShamanTotems::OtherMeleeHasteProviders
# BotClassSpecActionProfileDetail::CanonicalSpecTag aliases: class_spec -> bot_rotation_profile.spec_tag.
RUNTIME_SPEC_TAG = {"protection_paladin": "protection", "marksmanship_hunter": "marksmanship",
                    "survival_hunter": "survival", "enhancement_shaman": "enhancement", "fire_mage": "fire"}
# (class, role or None, spell, party-wide): TryValidationRouteReadiness ActiveBuffRequirement rows.
READINESS_BUFFS = (
    (1, None, 6673, True), (1, None, 469, True), (2, "tank", 25780, False), (2, "tank", 31801, False),
    (2, "tank", 465, False), (2, None, 20217, True), (3, None, 13165, False), (5, None, 21562, True),
    (5, None, 27683, True), (6, None, 57330, True), (8, None, 1459, True), (11, None, 1126, True))
READINESS_ONCE = "cast once at route readiness, not recast after a death"
READINESS_NOTES = {21562: "its readiness aura check names 21562, a dummy that applies 79104/79105, so it never "
                          "matches; cast_once then suppresses every recast"}
# Raid rogue poison setup (BotWorldPopulationMgrPersistentSetup.cpp): (bag item, poison spell) per hand.
ROGUE_POISONS = ((43233, 2823), (43231, 8679))
ROGUE_POISON_SPECS = ("assassination_rogue", "combat_rogue")
LUST_SPELLS = (2825, 32182, 80353)
# Encounters whose strategy times raid haste: Magmaw BotMagmawBloodlust.h, Maloriak BotMaloriakDuties.h (phase
# two), Chimaeron BotChimaeronDutyPlan.h. Magmaw's is admitted only on its own shard (IsMagmawBloodlustScenario:
# blackwing_descent_10n_magmaw_c<copy>_diagnostic). BotRaidBossLust::StrategyOwnsLust keeps exactly these.
LUST_DUTY_ENCOUNTERS = {"blackwing_descent": ("magmaw", "maloriak", "chimaeron")}
LUST_OWN_SHARD_ONLY = {"blackwing_descent": ("magmaw",)}
AUTOCAST = 0xC1
PALADIN_AURAS = (465, 7294, 19746, 19891, 32223)
ROGUE_POISON_SPELLS = (2823, 8679, 3408, 5761, 13219)
# Round 5 canonical-raid runtime of class owner C, credited while its source is present.
RAID_PERSISTENT_BUFFS = BOTS / "BotRaidPersistentBuffs.h"
RAID_BOSS_LUST = BOTS / "BotRaidBossLust.h"
RAID_MAJOR_ARMOR = BOTS / "BotRaidMajorArmor.h"
POWER_WORD_FORTITUDE, BLESSING_OF_KINGS, BLESSING_OF_MIGHT, MARK_OF_THE_WILD = 21562, 20217, 19740, 1126
# BotRaidPersistentBuffs::CanonicalRows: (class, role, spec, spell); a row needs a known spell.
CANONICAL_BUFF_ROWS = ((5, None, None, 21562), (2, "dps", "retribution_paladin", 7294),
                       (2, "healer", "holy_paladin", 465))
# BotRaidMajorArmor::UpkeepRow, appended by BotRaidRotationOverrides::ApplyCanonical; admitted on bosses only.
MAJOR_ARMOR_ROWS = ((11, "dps", "balance_druid", 770), (11, "tank", "feral_druid_tank", 16857))
# Communion's +3% party damage modifies Retribution Aura Overflow 63531, which nothing in this core applies.
RETRIBUTION_AURA_OVERFLOW = 63531
# Gate kinds of a rotation row. The mask names the rejection, not the threshold (BuildCandidates reasons).
GATE_REJECTS = {"enemy_count_too_low": "min_enemies", "enemy_count_too_high": "max_enemies",
                "injured_player_count_too_low": "ally_health", "injured_player_count_too_high": "ally_health",
                "target_health_gate": "target_health", "hostile_target_health_gate": "target_health",
                "self_health_gate": "self_health"}
# Raid primary-stat auras the scoring-start modifier ledger can show (SpellEffect aura 29 or 137).
OBSERVED_STAT_AURAS = {6673: "Battle Shout", 8076: "Strength of Earth", 57330: "Horn of Winter",
                       79060: "Mark of the Wild", 79061: "Mark of the Wild (raid)", 79062: "Blessing of Kings",
                       79063: "Blessing of Kings (raid)", 79104: "Power Word: Fortitude",
                       79105: "Power Word: Fortitude (raid)", 469: "Commanding Shout"}
EXPORT_NOTE = ("Enabled bot_rotation_action rows each canonical profile ran with in this run: valid_action_mask_json "
               "lists one candidate per profile spell (BotClassSpecActionProfileStore::BuildCandidates) of the "
               "profile ResolveProfileCombatAction evaluated, which LoadDbSnapshot loads with p.enabled = 1 AND "
               "a.enabled = 1 and the raid-scope BotRaidRotationOverrides then edit (in this run they only edit "
               "rows). A snapshot, not the live DB: re-export from the next live evidence after a rotation "
               "migration or a raid override that adds rows. The mask publishes no numeric gates (min_enemies, "
               "health or injured-player thresholds): each action's `gates` are inferred from its category (aoe "
               "and cleave: min_enemies; external_defensive and heal_*: ally health; execute: target health; "
               "defensive: self health) and from the gate rejections observed in the run's final and latest "
               "masks (`observed_rejects`). observed_stat_auras_at_scoring_start counts members per primary-stat "
               "aura in the scoring-start modifier ledger, for the raid stat auras of observed_stat_auras_legend.")


def spell(spell_id: int, *specs: str) -> dict[str, Any]:
    return {"kind": "spell", "spell": spell_id, "specs": list(specs)}


def talent(spell_id: int, *requires: int) -> dict[str, Any]:
    """A talent; `requires` lists the casts (or passive talents) that trigger it, empty when passive."""
    return {"kind": "talent", "spell": spell_id, "requires": list(requires)}


def lust(spell_id: int) -> dict[str, Any]:
    return {"kind": "lust", "spell": spell_id}


def pet(spell_id: int) -> dict[str, Any]:
    return {"kind": "pet", "spell": spell_id}


def totem(spell_id: int) -> dict[str, Any]:
    return {"kind": "totem", "spell": spell_id}


# (category, WoWSims config, providers). Spell IDs are the WoWSims provider IDs, or the talent rank the
# canonical builds carry where WoWSims names another rank or the aura (Abomination's Might 53138, Elemental
# Oath 51470, Scarlet Fever 81132, Earth and Moon 48506, Critical Mass 12873). Pet providers match by aura.
# Passive raid auras (Abomination's Might, Unleashed Rage, Trueshot Aura, Hunting Party, Improved Icy Talons,
# Elemental Oath, Arcane Tactics) are SpellEffect 65 area auras of the talent itself.
CATEGORIES: list[tuple[str, str, list[dict[str, Any]]]] = [
    ("stats", "AllStatsBuff", [spell(20217), spell(1126)]),
    ("armor", "ArmorBuff", [spell(465), totem(8071)]),
    ("stamina", "StaminaBuff", [spell(21562), spell(469)]),
    ("strength_agility", "StrengthAndAgilityBuff", [spell(57330), spell(6673), totem(8075)]),
    ("mana", "ManaBuff", [spell(1459)]),
    ("attack_power_pct", "AttackPowerPercentBuff", [spell(19740), talent(53138), talent(30808), talent(19506)]),
    ("lust", "Bloodlust", [lust(2825), lust(32182), lust(80353)]),
    ("damage_pct", "DamagePercentBuff", [talent(31876, RETRIBUTION_AURA_OVERFLOW), talent(82930), talent(34460)]),
    ("defensive_cooldowns", "DefensiveCooldownBuff", [spell(6940), talent(33206, 33206), spell(97462)]),
    ("spell_haste", "SpellHasteBuff", [talent(15473, 15473), spell(24858, "balance_druid"), totem(3738)]),
    ("crit", "CritBuff", [talent(17007, 768, 5487), talent(51470), talent(51701), talent(29801), pet(24604)]),
    ("melee_haste", "MeleeHasteBuff", [talent(55610), talent(53290), totem(8512)]),
    ("mp5", "MP5Buff", [spell(19740), totem(5675)]),
    ("replenishment", "ReplenishmentBuff", [talent(34914, 34914), talent(31876, 20271), talent(48544, 774, 48438),
                                            talent(30295, 6353, 17877, 50796), talent(86508, 116)]),
    ("resistance", "ResistanceBuff", [spell(19891), spell(20043), spell(27683), spell(20217), spell(1126), totem(8184)]),
    ("spell_power", "SpellPowerBuff", [talent(47236, 30146, 691, 688, 697, 712), talent(77746, 3599, 8190, 2894),
                                       spell(1459), totem(8227)]),
    ("major_armor", "MajorArmorDebuff", [spell(7386), spell(8647), spell(770), spell(16857), pet(35387)]),
    ("physical_damage_taken", "PhysicalDamageDebuff", [talent(29859, 772, 12834, 12849, 12867),
                                                       talent(58413, *ROGUE_POISON_SPELLS), talent(81328, 45477, 49184),
                                                       pet(55749)]),
    ("bleed_damage_taken", "BleedDebuff", [talent(29859, 772, 12834, 12849, 12867), spell(33878, *FERAL),
                                           spell(33876, *FERAL), spell(16511), pet(57386)]),
    ("spell_damage_taken", "SpellDamageDebuff", [talent(51160, 45477, 45462, 77575, 49184), talent(48506, 5176, 2912, 78674),
                                                 spell(1490), talent(58410, *ROGUE_POISON_SPELLS), pet(34889)]),
    ("spell_crit_taken", "SpellCritDebuff", [talent(12873, 2948, 44457, 82731), talent(17801, 686, 29722)]),
    ("damage_reduction", "DamageReduction", [talent(26016, 35395, 53595), spell(702), talent(81132, 48721), spell(1160),
                                             spell(99, *FERAL)]),
    ("attack_speed", "MeleeAttackSpeedDebuff", [spell(6343), spell(45477), talent(53696, 20271),
                                                talent(48484, 5221, 6807, 6785, 33878, 33876), spell(8042)]),
]


def runtime_totems(shaman: Mapping[str, Any], known_spells: set[int], others_known: set[int]) -> set[int]:
    elemental = shaman["class_spec"] == "elemental_shaman"
    wrath_of_air = elemental or (3738 in known_spells and bool(others_known & set(OTHER_MELEE_HASTE)))
    earth, water = (set(), {5675}) if elemental else ({8075}, {5394})
    return earth | water | {3599, 3738 if wrath_of_air else 8512}


def self_buff_contract() -> list[tuple[int, str | None, str | None, int]]:
    """(class, role, spec, spell) rows of BotPersistentSelfBuffContract::Buffs."""
    classes = {"WARRIOR": 1, "PALADIN": 2, "HUNTER": 3, "ROGUE": 4, "PRIEST": 5, "DEATH_KNIGHT": 6, "SHAMAN": 7,
               "MAGE": 8, "WARLOCK": 9, "DRUID": 11}
    source = (BOTS / "BotPersistentSelfBuffContract.h").read_text()
    return [(classes[name], None if role == "nullptr" else role.strip('"'), None if spec == "nullptr" else spec.strip('"'),
             int(spell_id)) for name, role, spec, spell_id in re.findall(
                 r'\{ CLASS_([A-Z_]+), (nullptr|"[a-z]+"), (nullptr|"[a-z_]+"), (\d+),', source)]


def is_canonical_scenario(scenario_id: str) -> bool:
    """BotCanonicalRaidScope::IsCanonicalCompositionScenario: a `_c<copy>` token, before any `_diagnostic`."""
    scenario_id = scenario_id.removesuffix("_diagnostic") if len(scenario_id) > len("_diagnostic") else scenario_id
    token = scenario_id.rpartition("_")[2] if "_" in scenario_id else ""
    return len(token) >= 2 and token[0] == "c" and token[1:].isdigit()


def inferred_gates(category: str, rejects: set[str]) -> list[str]:
    gates = {GATE_REJECTS[reason] for reason in rejects if reason in GATE_REJECTS}
    if category in ("aoe", "cleave"):
        gates.add("min_enemies")
    if category == "external_defensive" or category.startswith("heal_"):
        gates.add("ally_health")
    if category == "execute":
        gates.add("target_health")
    if category == "defensive":
        gates.add("self_health")
    return sorted(gates)


def runtime_spec_tag(class_spec: str) -> str:
    return RUNTIME_SPEC_TAG.get(class_spec, class_spec)


def runtime_actions_path(raid: str, mode: str) -> Path:
    return RUNTIME_ACTIONS_DIR / f"{raid}_{mode.lower()}.json"


def load_runtime_actions(path: Path) -> dict[tuple[int, str, str], dict[int, tuple[str, ...]]]:
    """(class, spec_tag, role) -> {spell: gate kinds} of the profile's enabled rows (a spell's least-gated row)."""
    export = json.loads(path.read_text())
    if export.get("schema") != RUNTIME_ACTIONS_SCHEMA:
        raise ValueError(f"runtime_actions_schema:{path}")
    profiles: dict[tuple[int, str, str], dict[int, tuple[str, ...]]] = {}
    for row in export["profiles"]:
        spells = profiles.setdefault((int(row["class_id"]), row["spec_tag"], row["role"]), {})
        for action in row["actions"]:
            gates = tuple(action.get("gates") or ())
            spell_id = int(action["spell"])
            if spell_id not in spells or len(gates) < len(spells[spell_id]):
                spells[spell_id] = gates
    return profiles


def _evidence_files(source: Path, run: str | None) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """(cohort, report.json or latest.json, payload) of a run directory or evidence tarball."""
    pattern = re.compile(rf"^{re.escape(run) if run else '[^/]+'}/shards/([^/]+)/(report|latest)\.json$")
    if source.is_dir():
        for path in sorted(source.glob("shards/*/*.json")):
            if path.name in ("report.json", "latest.json"):
                yield path.parent.name, path.name, json.loads(path.read_text())
        return
    with tarfile.open(source) as archive:
        for member in archive:
            match = pattern.match(member.name)
            if match and member.isfile():
                yield match.group(1), match.group(2) + ".json", json.load(archive.extractfile(member))


def _stat_auras(snapshot: Mapping[str, Any]) -> set[int]:
    ledger = ((snapshot.get("effective_stats") or {}).get("owner") or {}).get("modifier_ledger") or {}
    return {int(effect["spell_id"]) for stat in ledger.get("primary_stats") or [] for effect in stat["aura_effects"]}


def export_runtime_actions(source: Path, run: str | None = None) -> dict[str, Any]:
    """The enabled rotation rows each profile ran with, from a live run's shard reports."""
    profiles: dict[tuple[int, str, str], dict[str, Any]] = {}
    rejects: dict[tuple[tuple[int, str, str], int], set[str]] = {}  # (profile, row index) -> reasons
    observed: dict[str, dict[str, int]] = {}
    hashes: set[str] = set()
    for cohort, name, payload in _evidence_files(source, run):
        counts: dict[str, int] = {}
        for bot in payload["diagnosis"]["bots"]:
            snapshot = bot["snapshot"]
            for spell_id in _stat_auras(snapshot) & set(OBSERVED_STAT_AURAS):
                counts[str(spell_id)] = counts.get(str(spell_id), 0) + 1
            mask = snapshot["policy"].get("valid_action_mask_json") or {}
            if "profile" not in mask:
                continue
            profile = mask["profile"]
            key = (int(profile["class_id"]), profile["spec_tag"], profile["role"])
            for index, action in enumerate(mask["actions"]):
                rejects.setdefault((key, index), set()).add(action["reject_reason"])
            row = {"class_id": key[0], "spec_tag": key[1], "role": key[2], "profile_source": mask["profile_source"],
                   "actions": [{"spell": int(action["spell_id"]), "category": action["action_category"],
                                "target": action["target_selector"]} for action in mask["actions"]]}
            if any(int(action["resolved_spell_id"]) != int(action["spell_id"]) for action in mask["actions"]):
                row["resolved_spell_ids"] = [int(action["resolved_spell_id"]) for action in mask["actions"]]
            hashes.add(profile["snapshot_content_hash"])
            known = profiles.setdefault(key, {**row, "cohorts": []})
            if {k: v for k, v in known.items() if k != "cohorts"} != row:
                raise ValueError(f"runtime_profile_differs:{key}:{cohort}:{name}")
            if cohort not in known["cohorts"]:
                known["cohorts"].append(cohort)
        if name == "report.json":
            observed[cohort] = dict(sorted(counts.items(), key=lambda item: int(item[0])))
    if len(hashes) != 1:
        raise ValueError(f"runtime_snapshot_hashes:{sorted(hashes)}")
    for key, row in profiles.items():
        for index, action in enumerate(row["actions"]):
            seen = sorted(reason for reason in rejects[(key, index)] if reason in GATE_REJECTS)
            gates = inferred_gates(action["category"], set(seen))
            action.update({"gates": gates} if gates else {})
            action.update({"observed_rejects": seen} if seen else {})
    source_block: dict[str, Any] = {"run": run or source.name, "reports": "shards/<cohort>/{report,latest}.json",
                                    "field": "diagnosis.bots[].snapshot.policy.valid_action_mask_json",
                                    "snapshot_content_hash": hashes.pop()}
    if source.is_file():
        # Lexical, not resolved: a symlinked checkout or artifact keeps the repository path.
        source_block["evidence"] = os.path.relpath(source.absolute(), REPO_ROOT)
        source_block["evidence_md5"] = hashlib.md5(source.read_bytes()).hexdigest()
    return {"schema": RUNTIME_ACTIONS_SCHEMA, "note": EXPORT_NOTE, "source": source_block,
            "profiles": [dict(profiles[key], cohorts=sorted(profiles[key]["cohorts"])) for key in sorted(profiles)],
            "observed_stat_auras_legend": {str(key): name for key, name in sorted(OBSERVED_STAT_AURAS.items())},
            "observed_stat_auras_at_scoring_start": dict(sorted(observed.items()))}


def render_runtime_actions(export: Mapping[str, Any]) -> str:
    """Pretty JSON with one line per profile."""
    head = json.dumps({key: value for key, value in export.items() if key != "profiles"}, indent=2)
    profiles = ",\n".join("    " + json.dumps(row) for row in export["profiles"])
    return head[:-2] + ',\n  "profiles": [\n' + profiles + "\n  ]\n}\n"


def shard_coverage(shard: Mapping[str, Any], runtime_actions: Mapping[tuple[int, str, str], Mapping[int, tuple]],
                   raid_bosses: list[str], dbc_dir: Path = DEFAULT_DBC_DIR) -> dict[str, Any]:
    from tools.raid_program.raid_loadout_pet import pet_spell_rows, spell_auras
    from tools.raid_program.raid_loadout_spells import loadout_known_spells

    bots = shard["bots"]
    known = {bot["character_guid"]: set(loadout_known_spells(bot, dbc_dir)["known_spell_ids"]) for bot in bots}
    talented = {bot["character_guid"]: {int(row["spell_id"]) for row in bot.get("talents") or []}
                | {int(value) for value in bot.get("primary_tree_spells") or []} for bot in bots}
    contract = self_buff_contract()
    canonical = is_canonical_scenario(shard["scenario_id"])
    persistent_buffs = canonical and RAID_PERSISTENT_BUFFS.is_file()
    lust_fallback = canonical and RAID_BOSS_LUST.is_file()
    major_armor = canonical and RAID_MAJOR_ARMOR.is_file()
    bosses = raid_bosses if shard["boss_key"] == "full" else [shard["boss_key"]]
    strategy_lust = [boss for boss in bosses if boss in LUST_DUTY_ENCOUNTERS.get(shard["raid"], ())
                     and (shard["boss_key"] == boss or boss not in LUST_OWN_SHARD_ONLY.get(shard["raid"], ()))]
    fallback_lust = [boss for boss in bosses if lust_fallback and boss not in strategy_lust]
    pet_rows = [(spell_id, active) for bot in bots for spell_id, active in pet_spell_rows(bot.get("pet") or {})]
    pet_auras = {"provisioned": set().union(set(), *(spell_auras(spell_id, dbc_dir) for spell_id, _ in pet_rows)),
                 "runtime": set().union(set(), *(spell_auras(spell_id, dbc_dir) for spell_id, active in pet_rows
                                                 if active == AUTOCAST))}

    def mark_in_group(bot: Mapping[str, Any]) -> bool:
        """BotRaidPersistentBuffs::GroupHasMarkOfTheWild: another member is a druid that knows the Mark."""
        return any(int(other["class"]) == 11 and MARK_OF_THE_WILD in known[other["character_guid"]]
                   for other in bots if other["character_guid"] != bot["character_guid"])

    def sources(bot: Mapping[str, Any]) -> dict[int, tuple[str, str | None]]:
        """spell -> (runtime source, caveat) of a member's casts; the strongest source wins."""
        cls, role, spec, guid = int(bot["class"]), bot["role"], bot["class_spec"], bot["character_guid"]
        key = (cls, runtime_spec_tag(spec), role)
        if key not in runtime_actions:
            raise ValueError(f"runtime_profile_missing:{key}")
        might = persistent_buffs and cls == 2 and BLESSING_OF_MIGHT in known[guid] and mark_in_group(bot)
        cast: dict[int, tuple[str, str | None]] = {}

        def offer(spell_id: int, source: str, caveat: str | None = None) -> None:
            """An uncaveated source beats a caveated one; otherwise the first source stays."""
            if spell_id not in cast or (cast[spell_id][1] is not None and caveat is None):
                cast[spell_id] = (source, caveat)

        for _cls, _role, spell_id, party in READINESS_BUFFS:
            if _cls != cls or _role not in (None, role):
                continue
            if persistent_buffs and (spell_id == POWER_WORD_FORTITUDE or (spell_id == BLESSING_OF_KINGS and might)):
                continue  # BotRaidPersistentBuffs::ReadinessOwnedByContract
            once = "; ".join([READINESS_ONCE] + ([READINESS_NOTES[spell_id]] if spell_id in READINESS_NOTES else []))
            offer(spell_id, "readiness_once" if party else "readiness", once if party else None)
        if cls == 7:
            others = set().union(set(), *(spells for other, spells in known.items() if other != guid))
            for spell_id in runtime_totems(bot, known[guid], others):
                offer(spell_id, "totem")
        if len(strategy_lust) + len(fallback_lust) == len(bosses):
            for spell_id in LUST_SPELLS:
                offer(spell_id, "lust")
        rows = [(c, r, s, BLESSING_OF_MIGHT if might and spell_id == BLESSING_OF_KINGS else spell_id)
                for c, r, s, spell_id in contract]
        rows += list(CANONICAL_BUFF_ROWS) if persistent_buffs else []
        for c, r, s, spell_id in rows:
            if c == cls and r in (None, role) and s in (None, spec):
                offer(spell_id, "self_buff")
        for spell_id, gates in runtime_actions[key].items():
            offer(spell_id, "rotation", f"a rotation row gated by {', '.join(gates)}" if gates else None)
        for c, r, s, spell_id in MAJOR_ARMOR_ROWS if major_armor else ():
            if c == cls and r == role and s == spec:
                offer(spell_id, "raid_override")
        cast = {spell_id: value for spell_id, value in cast.items() if spell_id in known[guid]}
        if cls == 4 and role == "dps" and spec in ROGUE_POISON_SPECS:
            # Item uses, not spellbook spells: the setup needs the bag stacks only.
            items = {int(row["item_id"]) for row in bot.get("consumables") or []}
            cast.update({spell_id: ("poison_setup", None) for item, spell_id in ROGUE_POISONS if item in items})
        return cast

    runtime_casts = {bot["character_guid"]: sources(bot) for bot in bots}
    provisioned: dict[str, list[str]] = {}
    runtime: dict[str, list[str]] = {}
    caveats: dict[str, str] = {}
    for category, _config, providers in CATEGORIES:
        have, cast, notes = set(), set(), {}
        for provider in providers:
            spell_id, kind = provider["spell"], provider["kind"]
            if kind == "pet":
                if spell_auras(spell_id, dbc_dir) & pet_auras["provisioned"]:
                    have.add(f"pet:{spell_id}")
                if spell_auras(spell_id, dbc_dir) & pet_auras["runtime"]:
                    cast.add(f"pet:{spell_id}@autocast")
                continue
            for bot in bots:
                guid, spec = bot["character_guid"], bot["class_spec"]
                if provider.get("specs") and spec not in provider["specs"]:
                    continue
                label, casts = f"{spec}:{spell_id}", runtime_casts[guid]
                if kind == "talent":
                    if spell_id not in talented[guid]:
                        continue
                    have.add(label)
                    # An active talent (Pain Suppression, Shadowform) needs its own runtime cast; a passive
                    # trigger talent (Deep Wounds) counts by being talented. An ungated trigger wins.
                    triggers = sorted((casts[value][1] is not None if value in casts else False, value)
                                      for value in provider["requires"] if value in casts
                                      or (value != spell_id and value in talented[guid]))
                    if not provider["requires"]:
                        cast.add(f"{label}@passive")
                    elif triggers:
                        gated, trigger = triggers[0]
                        cast.add(f"{label}@{trigger}")
                        if gated:
                            notes[f"{label}@{trigger}"] = f"{label} only through {trigger}, {casts[trigger][1]}"
                elif spell_id in known[guid]:
                    have.add(label)
                    if spell_id in casts:
                        source, note = casts[spell_id]
                        cast.add(f"{label}@{source}")
                        if note:
                            notes[f"{label}@{source}"] = f"{label}: {note}"
        provisioned[category], runtime[category] = sorted(have), sorted(cast)
        if cast and all(label in notes for label in cast):
            caveats[category] = "; ".join(notes[label] for label in sorted(cast))

    def score(found_by: Mapping[str, list[str]]) -> dict[str, Any]:
        missing = [category for category, found in found_by.items() if not found]
        return {"covered": len(CATEGORIES) - len(missing), "categories": len(CATEGORIES),
                "decision_scale": f"{DECISION_SCALE - len(missing)}/{DECISION_SCALE}", "missing": missing}

    provisioned_score, runtime_score = score(provisioned), score(runtime)
    return {"cohort_id": shard["cohort_id"], "boss_key": shard["boss_key"], "canonical_raid": canonical,
            "specs": sorted(bot["class_spec"] for bot in bots),
            "provisioned": provisioned_score, "runtime": runtime_score,
            "provisioned_only": [category for category in runtime_score["missing"]
                                 if category not in provisioned_score["missing"]],
            "runtime_caveats": caveats, "lust_encounters": {"strategy": strategy_lust, "fallback": fallback_lust},
            "providers": {"provisioned": provisioned, "runtime": runtime}}


def composition_coverage(composition: Path = DEFAULT_COMPOSITION, dbc_dir: Path = DEFAULT_DBC_DIR,
                         runtime_actions: Path | None = None) -> dict[str, Any]:
    from tools.raid_program.raid_shard_scenarios import build_plan

    plan = build_plan(composition)
    path = runtime_actions or runtime_actions_path(plan["raid"], plan["mode"])
    actions = load_runtime_actions(path)
    bosses = [shard["boss_key"] for shard in plan["shards"] if shard["boss_key"] != "full"]
    return {"schema": "raid_buff_coverage_v3", "provider_revision": PROVIDER_REVISION,
            "composition_id": plan["composition_id"],
            "columns": {"provisioned": "a member has the provider",
                        "runtime": "an enabled rotation row or a runtime code contract casts it; not proof the "
                                   "buff is up (gated or cast-once providers are runtime_caveats)"},
            "runtime_actions": {"path": os.path.relpath(path.absolute(), REPO_ROOT),
                                "source": json.loads(path.read_text())["source"]},
            "canonical_runtime_sources": {name: path.is_file() for name, path in (
                ("persistent_raid_buffs", RAID_PERSISTENT_BUFFS), ("boss_lust_fallback", RAID_BOSS_LUST),
                ("major_armor_upkeep", RAID_MAJOR_ARMOR))},
            "shards": [shard_coverage(shard, actions, bosses, dbc_dir) for shard in plan["shards"]]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--composition", type=Path, default=DEFAULT_COMPOSITION)
    parser.add_argument("--dbc-dir", type=Path, default=DEFAULT_DBC_DIR)
    parser.add_argument("--runtime-actions", type=Path, help="export to score against (default: the raid's)")
    parser.add_argument("--full", action="store_true", help="include every category's providers")
    parser.add_argument("--export-runtime-actions", type=Path, metavar="EVIDENCE",
                        help="print the runtime action export of a live run's tarball or run directory")
    parser.add_argument("--run", help="run directory inside the tarball")
    args = parser.parse_args(argv)
    if args.export_runtime_actions:
        print(render_runtime_actions(export_runtime_actions(args.export_runtime_actions, args.run)), end="")
        return 0
    report = composition_coverage(args.composition, args.dbc_dir, args.runtime_actions)
    if not args.full:
        for shard in report["shards"]:
            shard.pop("providers")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
