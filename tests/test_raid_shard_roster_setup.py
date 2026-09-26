"""Round 3 package M: every canonical raid-shard bot carries its prepull consumables and native raid haste.

Evidence (round-2 batch, 2026-09-25): the prepull candidate failed closed for the whole raid on
`raid_prepull_unknown_spec_contract_beast_mastery_hunter`, and the Magmaw Bloodlust owner reported
`blocked_spell_not_in_shaman_spellbook` because the Draenei shaman was provisioned without Heroism.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools.raid_program import raid_shard_plan as rsp

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
CONTRACTS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidConsumableContracts.cpp"
GENERATED = ROOT / "src/server/game/Bots/BotCalibrationFixtureContractGenerated.h"
DBC = ROOT / "data/dbc/enUS"
HEROISM, BLOODLUST, WATER_SHIELD = 32182, 2825, 52127
SELF_BUFFS = ROOT / "src/server/game/Bots/BotPersistentSelfBuffContract.h"
CLASS_IDS = {"WARRIOR": 1, "PALADIN": 2, "HUNTER": 3, "ROGUE": 4, "PRIEST": 5, "DEATH_KNIGHT": 6, "SHAMAN": 7,
             "MAGE": 8, "WARLOCK": 9, "DRUID": 11}
# Specs whose native contract row is still a pending shared patch
# (.git/round3_patches/maloriak/01_prepull_bm_hunter_contract.patch). Self-expiring: once the C++
# contract table names the spec, the whitelist is empty and every roster spec must have its row.
CONTRACT_PATCH_SPECS = {"beast_mastery_hunter"}
CONTRACT_PATCH_PENDING = {spec for spec in CONTRACT_PATCH_SPECS if f'"{spec}"' not in CONTRACTS.read_text()}


@pytest.fixture(scope="module")
def plan() -> dict:
    from tools.raid_program.raid_shard_scenarios import build_plan
    return build_plan(COMPOSITION)


def runtime_contracts() -> dict[str, tuple[int, int, int]]:
    """spec -> (flask, food, prepot) item IDs of the C++ prepull contract."""
    source = CONTRACTS.read_text()
    archetypes = {}
    for name in ("Intellect", "Agility", "Strength"):
        body = re.search(rf"Contract {name}Contract\(char const\* classSpec\)\s*\{{\s*return \{{ classSpec, ([^}}]*)\}};",
                         source).group(1)
        values = [int(value) for value in body.replace("\n", " ").split(",") if value.strip()]
        archetypes[name] = (values[0], values[3], values[6])
    contracts = {spec: archetypes[name]
                 for name, spec in re.findall(r'(Intellect|Agility|Strength)Contract\("([a-z_]+)"\)', source)}
    for row in re.findall(r'\{ "([a-z_]+)", "[a-z_]+", "[0-9a-f]{64}", ([^}]*)\}', GENERATED.read_text()):
        spec, values = row[0], [value.strip() for value in row[1].split(",")]
        items = [int(value) for value in values if value.isdigit()]
        # ... PetPolicy, 58086 flask, 79470, 79470, 62671 food, 87587, 87547, 58091 prepot, ...
        flask_index = next(index for index, value in enumerate(items) if value in (58086, 58087, 58088))
        contracts[spec] = (items[flask_index], items[flask_index + 3], items[flask_index + 6])
    return contracts


def test_every_canonical_bot_carries_its_runtime_contract_consumables(plan):
    contracts = runtime_contracts()
    missing_contract = set()
    for shard in plan["shards"]:
        for bot in shard["bots"]:
            rows = {int(row["slot"]): row for row in bot.get("consumables") or []}
            assert {26, 27, 28} <= set(rows), (shard["cohort_id"], bot["class_spec"])
            assert rows[26]["uses"] == ["flask_before_scoring"] and rows[27]["uses"] == ["food_before_scoring"]
            assert "prepot_before_combat" in rows[28]["uses"]
            items = (rows[26]["item_id"], rows[27]["item_id"], rows[28]["item_id"])
            if bot["class_spec"] in contracts:
                assert items == contracts[bot["class_spec"]], bot["class_spec"]
            else:
                missing_contract.add(bot["class_spec"])
    assert missing_contract <= CONTRACT_PATCH_PENDING


def test_the_pending_contract_whitelist_expires_with_the_native_row():
    source = CONTRACTS.read_text()
    for spec in CONTRACT_PATCH_SPECS:
        assert (spec in CONTRACT_PATCH_PENDING) is (f'"{spec}"' not in source)
    if not CONTRACT_PATCH_PENDING:
        assert set(rsp.CONTRACT_CONSUMABLE_ARCHETYPES) <= set(runtime_contracts())


def test_the_fallback_table_mirrors_the_runtime_contract_archetypes():
    contracts = runtime_contracts()
    for spec, archetype in rsp.CONTRACT_CONSUMABLE_ARCHETYPES.items():
        expected = rsp.CONTRACT_CONSUMABLE_ITEMS[archetype]
        if spec in contracts:
            assert contracts[spec] == expected, spec
        else:
            assert spec in CONTRACT_PATCH_PENDING, spec
    # Calibrated DPS specs keep their catalog consumables (poison stacks included).
    assert rsp.contract_consumables("assassination_rogue") is None
    assert [row["item_id"] for row in rsp.contract_consumables("blood_death_knight")] == [58088, 62670, 58146]


def test_the_shaman_carries_native_heroism_in_every_shard(plan):
    shamans = [bot for shard in plan["shards"] for bot in shard["bots"] if bot["character_key"] == "shaman"]
    assert len(shamans) == len(plan["shards"])
    assert all({HEROISM, WATER_SHIELD} <= set(bot["spells"]) and bot["race"] == 11 for bot in shamans)
    declared = {row["character_key"]: sorted(row.get("spells") or []) for row in json.loads(COMPOSITION.read_text())["characters"]}
    for shard in plan["shards"]:
        for bot in shard["bots"]:
            assert sorted(bot.get("spells") or []) == declared[bot["character_key"]], bot["name"]


def test_declared_spells_must_be_native_to_the_race_and_class(plan):
    if not (DBC / "SkillLineAbility.dbc").is_file() or not (ROOT / "dataset/world_knowledge/trainers.jsonl").is_file():
        pytest.skip("client DBCs or trainers not hydrated")
    from tools.raid_program.raid_loadout_spells import LoadoutSpellError, loadout_known_spells

    shaman = next(bot for bot in plan["shards"][0]["bots"] if bot["character_key"] == "shaman")
    assert HEROISM in loadout_known_spells(shaman, DBC)["known_spell_ids"]
    for foreign in ([BLOODLUST], [1329]):  # Horde-only raid haste; a rogue spell
        with pytest.raises(LoadoutSpellError, match="declared_spell_not_native"):
            loadout_known_spells({**shaman, "spells": foreign}, DBC)


@pytest.mark.parametrize("spells", ["32182", [32182, 32182], [0], [True], [32182.0]])
def test_malformed_character_spells_are_refused(spells):
    with pytest.raises(rsp.ShardPlanError, match="character_spells_invalid"):
        rsp.character_spells({"character_key": "shaman", "spells": spells})
    assert rsp.character_spells({"character_key": "shaman"}) == []


def test_the_plan_refuses_a_roster_member_without_its_contract_set(plan):
    import copy
    import json

    assert rsp.validate_shard_plan(plan)["all_passed"]
    for mutate, reason in (
            (lambda bot: bot.pop("consumables"), "prepull_contract_flask_before_scoring_row"),
            (lambda bot: bot["consumables"].pop(), "prepull_contract_prepot_before_combat_row"),
            (lambda bot: bot["consumables"][0].update(item_id=58087), "prepull_contract_archetype_items")):
        broken = copy.deepcopy(plan)
        dk = next(bot for bot in broken["shards"][0]["bots"] if bot["class_spec"] == "blood_death_knight")
        mutate(dk)
        with pytest.raises(rsp.ShardPlanError) as refused:
            rsp.validate_shard_plan(broken)
        failures = json.loads(str(refused.value))["failures"]
        assert {"check": "prepull_consumable_contract", "name": dk["name"], "class_spec": "blood_death_knight",
                "reason": reason} in failures


def persistent_self_buffs() -> list[tuple[int, str | None, str | None, int]]:
    """(class id, role, spec tag, spell id) rows of BotPersistentSelfBuffContract::Buffs."""
    rows = re.findall(r'\{ CLASS_([A-Z_]+), (nullptr|"[a-z]+"), (nullptr|"[a-z_]+"), (\d+),', SELF_BUFFS.read_text())
    return [(CLASS_IDS[name], None if role == "nullptr" else role.strip('"'),
             None if spec == "nullptr" else spec.strip('"'), int(spell)) for name, role, spec, spell in rows]


def test_every_canonical_spec_knows_its_persistent_self_buff(plan):
    """Round 3 Nefarian c0: the Restoration shaman logged persistent_setup_spell_missing:52127 all run."""
    if not (DBC / "SkillLineAbility.dbc").is_file() or not (ROOT / "dataset/world_knowledge/trainers.jsonl").is_file():
        pytest.skip("client DBCs or trainers not hydrated")
    from tools.raid_program.raid_loadout_spells import loadout_known_spells

    buffs = persistent_self_buffs()
    assert (7, "healer", None, WATER_SHIELD) in buffs and len(buffs) >= 20
    checked = set()
    for shard in plan["shards"]:
        for bot in shard["bots"]:
            known = set(loadout_known_spells(bot, DBC)["known_spell_ids"])
            required = {spell for class_id, role, spec, spell in buffs if class_id == int(bot["class"])
                        and role in (None, bot["role"]) and spec in (None, bot["class_spec"])}
            assert required <= known, (shard["cohort_id"], bot["class_spec"], sorted(required - known))
            checked.add(bot["class_spec"])
    assert {"restoration_shaman", "elemental_shaman", "fire_mage", "demonology_warlock"} <= checked


ENCOUNTERS = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters"
NEFARIAN_CAPABILITIES = ENCOUNTERS / "Nefarian/BotNefarianCapabilities.h"
MALORIAK_CANDIDATES = ENCOUNTERS / "Maloriak/BotWorldPopulationMgrMaloriakCandidates.cpp"
MALORIAK_DUTIES = ENCOUNTERS / "Maloriak/BotMaloriakDuties.h"
OMNOTRON_CAPABILITIES = ENCOUNTERS / "Omnotron/BotOmnotronCapabilities.h"
OMNOTRON_CANDIDATES = ENCOUNTERS / "Omnotron/BotWorldPopulationMgrOmnotronCandidates.cpp"
CHIMAERON_DUTIES = ENCOUNTERS / "Chimaeron/BotChimaeronDutyPlan.h"
CHIMAERON_CANDIDATES = ENCOUNTERS / "Chimaeron/BotWorldPopulationMgrChimaeronCandidates.cpp"
ATRAMEDES_MOBILITY = ENCOUNTERS / "Atramedes/BotAtramedesMobility.h"
ATRAMEDES_ICE_BLOCK = ENCOUNTERS / "Atramedes/BotAtramedesIceBlock.h"
ATRAMEDES_FACTS = ENCOUNTERS / "Atramedes/BotAtramedesFacts.h"
COMBAT_RES = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatRes.cpp"
GROUP_RECOVERY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteGroupRecovery.cpp"
COMBAT_RES_ELIGIBILITY = ROOT / "src/server/game/Bots/BotCombatResEligibility.h"
RESURRECT_EFFECTS = (18, 113, 172)  # SPELL_EFFECT_RESURRECT, _NEW, _WITH_AURA
SPELL_ATTR8_ENFORCE_IN_COMBAT_RESSURECTION_LIMIT = 0x00800000
# Round 5: the druid tanks here, and a canonical raid never makes a tank the combat-res owner.
SHARDS_WITHOUT_COMBAT_RES = {"omnotron", "chimaeron", "maloriak", "nefarian", "full"}
# MaloriakRemedyDispelSpells in class order: Spellsteal, Purge, Tranquilizing Shot, Dispel Magic.
REMEDY_DISPEL_BY_CLASS = {8: 30449, 7: 370, 3: 19801, 5: 527}
# Omnotron's Soaked In Poison dispel (CanCleansePoison): Cleanse for a paladin, Remove Corruption for a
# druid that is neither a tank nor Feral.
POISON_CLEANSE_BY_CLASS = {2: 4987, 11: 2782}
# Reviewed gaps: none since b90e95330a names Curse of Exhaustion (an Affliction talent) for Affliction only.
UNLEARNABLE_DUTY_SPELLS: set[tuple[str, int]] = set()


def function_body(path: Path, signature: str) -> str:
    source = path.read_text()
    body = source[source.index(signature):]
    return body[:body.index("\n}\n")]


def constants(*paths: Path) -> dict[str, int]:
    return {name: int(value) for path in paths
            for name, value in re.findall(r"constexpr uint32 (\w+) = (\d+);", path.read_text())}


def capability_table(function: str) -> list[tuple[str, str, int]]:
    """(match kind, spec or suffix, spell) rows of a Nefarian capability function, in if-chain order."""
    body = function_body(NEFARIAN_CAPABILITIES, f"inline {function}")
    return [("suffix", suffix, int(spell)) if suffix else ("exact", exact, int(spell))
            for suffix, exact, spell in re.findall(
                r'if \((?:SpecEndsWith\(spec, "(\w+)"\)|spec == "(\w+)")\)\s*return \{ (\d+),', body)]


def omnotron_interrupts() -> list[tuple[str, str, int]]:
    """Omnotron InterruptFor rows: SpecIs matches a suffix, SpecStarts a prefix."""
    body = function_body(OMNOTRON_CAPABILITIES, "inline std::optional<InterruptCapability> InterruptFor")
    return [("suffix" if kind == "SpecIs" else "prefix", value, int(spell)) for kind, value, spell in re.findall(
        r'if \((SpecIs|SpecStarts)\(classSpec, "(\w+)"\)\)\s*return InterruptCapability\{ (\d+),', body)]


def capability_spell(table: list[tuple[str, str, int]], spec: str) -> int | None:
    for kind, value, spell in table:
        if ((kind == "suffix" and spec.endswith(value)) or (kind == "exact" and spec == value)
                or (kind == "prefix" and spec.startswith(value))):
            return spell
    return None


def spec_list(path: Path, signature: str) -> set[str]:
    return set(re.findall(r'spec == "(\w+)"', function_body(path, signature)))


def lust_owner(bots: list[dict], rank) -> dict | None:
    ranked = [(rank(bot["class_spec"]), bot["character_guid"], bot) for bot in bots if rank(bot["class_spec"]) is not None]
    return min(ranked, key=lambda row: row[:2])[2] if ranked else None


def encounter_duty_rules() -> dict[str, list]:
    """Per boss: rules (bot, shard bots) -> requirements, each a set of spells of which one must be known."""
    nefarian_controls = capability_table("ControlCapability ControlFor")
    nefarian_interrupts = capability_table("InterruptCapability InterruptFor")
    assert ("suffix", "hunter", 5116) in nefarian_controls and ("suffix", "priest", 9484) in nefarian_controls
    dispels = re.search(r"MaloriakRemedyDispelSpells = \{([^}]*)\}", MALORIAK_CANDIDATES.read_text()).group(1)
    assert [int(value) for value in re.findall(r"(\d+)u", dispels)] == list(REMEDY_DISPEL_BY_CLASS.values())
    interrupts = omnotron_interrupts()
    assert ("suffix", "paladin", 96231) in interrupts and ("prefix", "feral_druid", 80965) in interrupts
    cleanse = function_body(OMNOTRON_CAPABILITIES, "inline bool CanCleansePoison")
    assert 'SpecIs(classSpec, "paladin")' in cleanse and '!SpecStarts(classSpec, "feral_druid")' in cleanse
    assert "{ 4987u, 2782u }" in OMNOTRON_CANDIDATES.read_text()

    chimaeron = constants(CHIMAERON_DUTIES)
    maloriak = constants(MALORIAK_DUTIES)
    nefarian_constants = constants(NEFARIAN_CAPABILITIES)
    assert "SpellNaturesGrasp : 0" in function_body(NEFARIAN_CAPABILITIES, "inline uint32 WarriorRootFor")
    assert "return { SpellEnrage, SpellFrenziedRegeneration, SpellSurvivalInstincts };" in function_body(
        NEFARIAN_CAPABILITIES, "inline std::array<uint32, 3> TankSelfCareSpellsFor")
    rank_body = function_body(CHIMAERON_DUTIES, "inline int LustRank")
    mage_rank = int(re.search(r"IsMageSpec\(spec\)\)\s*return (\d+);", rank_body).group(1))
    shaman_rank = int(re.search(r"IsShamanSpec\(spec\)\)\s*return (\d+);", rank_body).group(1))
    mages = spec_list(CHIMAERON_DUTIES, "inline bool IsMageSpec")
    shamans = spec_list(CHIMAERON_DUTIES, "inline bool IsShamanSpec")
    assert "IsMageSpec(lust->ClassSpec) ? TimeWarpSpell : BloodlustSpell" in CHIMAERON_DUTIES.read_text()
    assert "HeroismSpell" in CHIMAERON_CANDIDATES.read_text()  # a shaman owner casts Heroism when it lacks Bloodlust
    shaman_lust = {chimaeron["BloodlustSpell"], chimaeron["HeroismSpell"]}
    chimaeron_rank = lambda spec: mage_rank if spec in mages else shaman_rank if spec in shamans else None
    maloriak_body = function_body(MALORIAK_DUTIES, "inline uint8 LustRankFor")
    maloriak_ranks = {suffix: int(rank) for suffix, rank in
                      re.findall(r'EndsWith\(classSpec, "(\w+)"\)\)\s*return (\d+);', maloriak_body)}
    maloriak_rank = lambda spec: next((rank for suffix, rank in maloriak_ranks.items() if spec.endswith(suffix)), None)

    mobility = constants(ATRAMEDES_MOBILITY, ATRAMEDES_FACTS)
    forms = {name: form for name, form in re.findall(
        r"\{ (\w+Spell), Kind::\w+, [^,]+, [^,]+, \d+, \d+, (\w+),", ATRAMEDES_MOBILITY.read_text())}
    static = function_body(ATRAMEDES_MOBILITY, "inline float StaticCapabilityYards")
    kite = {word: re.findall(r"yards\((\w+)\)", expression)
            for word, expression in re.findall(r'if \(has\("(\w+)"\)\)\s*return ([^;]+);', static)}
    assert kite["rogue"] == ["SprintSpell"] and kite["druid"] == ["DashSpell", "StampedingRoarSpell"]
    ice_mages = spec_list(ATRAMEDES_ICE_BLOCK, "inline bool IsMageSpec")

    def kite_spells(bot, _bots):
        if bot["role"] == "tank":
            return []
        names = next((names for word, names in kite.items() if word in bot["class_spec"]), [])
        required = [{mobility[name]} for name in names]
        required += [{mobility[forms[name]]} for name in names if forms.get(name, "0") != "0"]
        if bot["class_spec"] in ice_mages:
            required.append({mobility["IceBlockAura"]})
        return required

    def lust(rank, spells_for):
        def rule(bot, bots):
            owner = lust_owner(bots, rank)
            return [spells_for(bot["class_spec"])] if owner is bot else []
        return rule

    def combat_res(bot, _bots):
        # Rebirth is the reconciler's named combat res; only a non-tank may own it in a canonical raid.
        return [{combat_res_spells()[0]}] if int(bot["class"]) == 11 and bot["role"] != "tank" else []

    return {
        "all": [combat_res],
        "nefarian": [
            lambda bot, _bots: [{capability_spell(nefarian_interrupts, bot["class_spec"])}],
            # Round 6, the user's tactic: the druid roots bone warriors with Nature's Grasp (WarriorRootFor).
            lambda bot, _bots: [{nefarian_constants["SpellNaturesGrasp"]}] if bot["class_spec"].endswith(
                ("druid", "druid_tank")) else [],
            # Round 8: the Feral tank's pillar self-care and the paladins' magma-crossing Divine Shield.
            lambda bot, _bots: [{nefarian_constants["SpellEnrage"]}, {nefarian_constants["SpellFrenziedRegeneration"]}]
            if bot["class_spec"] == "feral_druid_tank" else [],
            lambda bot, _bots: [{nefarian_constants["SpellDivineShield"]}] if bot["class_spec"].endswith("paladin") else [],
            lambda bot, _bots: [] if bot["role"] == "tank" else [{capability_spell(nefarian_controls, bot["class_spec"])}]],
        "maloriak": [
            lambda bot, _bots: [{REMEDY_DISPEL_BY_CLASS.get(int(bot["class"]))}],
            # Round 6, the user's Maloriak tactic: the rogue's Tricks and the hunter's traps (BotMaloriakDuties.h).
            lambda bot, _bots: [{maloriak["TricksOfTheTradeSpell"]}] if int(bot["class"]) == 4 else
                               [{maloriak["FreezeTrapSpell"]}, {maloriak["IceTrapSpell"]}] if int(bot["class"]) == 3 else [],
            lust(maloriak_rank, lambda spec: shaman_lust if spec.endswith("_shaman") else {chimaeron["TimeWarpSpell"]})],
        "omnotron": [
            lambda bot, _bots: [{capability_spell(interrupts, bot["class_spec"])}],
            lambda bot, _bots: [{POISON_CLEANSE_BY_CLASS.get(int(bot["class"]))}]
            if int(bot["class"]) == 2 or (int(bot["class"]) == 11 and bot["role"] != "tank"
                                          and not bot["class_spec"].startswith("feral_druid")) else []],
        "chimaeron": [lust(chimaeron_rank, lambda spec: {chimaeron["TimeWarpSpell"]} if spec in mages else shaman_lust)],
        "atramedes": [kite_spells],
    }


def test_every_canonical_bot_knows_the_duty_spells_its_encounters_name(plan):
    """Round 4: encounter duties named spells no canonical bot knew (Nefarian controls, Maloriak Remedy
    dispels, the Ret's Omnotron Cleanse; review: Chimaeron's Time Warp owner and Atramedes air mobility).

    Each boss shard answers to its boss's duty tables, read from the C++ sources; the full raid to all.
    """
    if not (DBC / "SkillLineAbility.dbc").is_file() or not (ROOT / "dataset/world_knowledge/trainers.jsonl").is_file():
        pytest.skip("client DBCs or trainers not hydrated")
    from tools.raid_program.raid_loadout_spells import loadout_known_spells, native_baseline, spell_learn_map

    rules = encounter_duty_rules()
    learn_map, gaps, required_seen = spell_learn_map(DBC), set(), set()
    for shard in plan["shards"]:
        boss_rules = [rule for boss, boss_rules in rules.items() for rule in boss_rules
                      if boss == "all" or shard["boss_key"] in (boss, "full")]
        assert len(boss_rules) > 1 or shard["boss_key"] == "magmaw", shard["cohort_id"]
        for bot in shard["bots"]:
            spec, known = bot["class_spec"], set(loadout_known_spells(bot, DBC)["known_spell_ids"])
            baseline = native_baseline(int(bot["class"]), int(bot["race"]), DBC, learn_map)
            for rule in boss_rules:
                for alternatives in rule(bot, shard["bots"]):
                    alternatives = {spell for spell in alternatives if spell}
                    required_seen |= alternatives
                    if alternatives and not alternatives & known:
                        # learnable but not provisioned fails; a spell the class cannot learn is a reviewed gap
                        assert not alternatives & baseline, (shard["cohort_id"], spec, sorted(alternatives))
                        gaps.add((spec, min(alternatives)))
    assert gaps == UNLEARNABLE_DUTY_SPELLS
    # The review's spells are among the checked ones: Time Warp, Sprint, Dash, Stampeding Roar, Cat Form.
    assert {80353, 2983, 1850, 77764, 768, 4987, 5116, 19801, 30449, 370, 9484, 853, 20484,
            57934, 1499, 13809, 16689, 5229, 22842, 642} <= required_seen


def combat_res_spells() -> list[int]:
    """The spells BotWorldPopulationMgrCombatRes.cpp IsNativeCombatResSpell names by id (Rebirth)."""
    body = function_body(COMBAT_RES, "bool IsNativeCombatResSpell")
    return [int(value) for value in re.findall(r"spellInfo->Id == (\d+)", body)]


def resurrect_spells_with_limit() -> set[int]:
    """Spells the reconciler also accepts: a resurrect effect and the in-combat resurrection limit."""
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    attributes = {int(row[0]): int(row[9]) for row in load_wdbc_values(
        DBC / "Spell.dbc", "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii")}
    effects = {int(row[24]) for row in load_wdbc_values(DBC / "SpellEffect.dbc", "nifiiiffiiiiiifiifiiiiiiiix")
               if int(row[1]) in RESURRECT_EFFECTS}
    return {spell for spell in effects if attributes.get(spell, 0) & SPELL_ATTR8_ENFORCE_IN_COMBAT_RESSURECTION_LIMIT}


def test_combat_res_owners_are_the_non_tank_members_that_know_one(plan):
    """Round 5: the druid knows Rebirth everywhere, but owns it only where it is Balance (not the tank)."""
    if not (DBC / "SkillLineAbility.dbc").is_file() or not (ROOT / "dataset/world_knowledge/trainers.jsonl").is_file():
        pytest.skip("client DBCs or trainers not hydrated")
    from tools.raid_program.raid_loadout_spells import loadout_known_spells

    assert combat_res_spells() == [20484]
    # One rule (BotCombatResEligibility.h) for the reconciler's owner loop and the group recovery's living caster.
    reconciler = re.sub(r"\s+", " ", COMBAT_RES.read_text())
    assert ("if (canonicalRaid && !BotCombatResEligibility::RoleMayCast(canonicalRaid, "
            "GetDungeonRole(member.Bot))) continue;") in reconciler
    assert "BotCombatResEligibility::CountsAsLivingCaster(canonicalRaid," in GROUP_RECOVERY.read_text()
    assert 'return !canonicalRaid || role != "tank";' in COMBAT_RES_ELIGIBILITY.read_text()
    res_spells = set(combat_res_spells()) | resurrect_spells_with_limit()
    owners = {}
    for shard in plan["shards"]:
        owners[shard["boss_key"]] = sorted(
            bot["class_spec"] for bot in shard["bots"] if bot["role"] != "tank"
            and res_spells & set(loadout_known_spells(bot, DBC)["known_spell_ids"]))
        druid = next(bot for bot in shard["bots"] if bot["character_key"] == "druid")
        assert 20484 in loadout_known_spells(druid, DBC)["known_spell_ids"], shard["cohort_id"]
    assert owners["magmaw"] == owners["atramedes"] == ["balance_druid"]
    assert {boss for boss, found in owners.items() if not found} == SHARDS_WITHOUT_COMBAT_RES


def test_canonical_only_declarations_stay_out_of_the_legacy_rosters():
    """Rebirth, Power Word: Fortitude, the Maloriak Tricks and traps, Nature's Grasp and the Ravager are canonical-roster provisioning;
    the legacy rosters keep theirs."""
    for path in (ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json",
                 ROOT / "experiments/configs/validation_provisioning_cata_001.json"):
        legacy = json.loads(path.read_text())
        bots = []

        def walk(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "bots" and isinstance(child, list):  # provisioned rows, not roster summaries
                        bots.extend(row for row in child if isinstance(row, dict) and "class_spec" in row)
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(legacy)
        assert bots, path
        assert not any({20484, 21562, 57934, 1499, 13809, 16689, 5229, 22842, 642} & set(bot.get("spells") or []) for bot in bots), path
        hunters = [bot for bot in bots if str(bot["class_spec"]).endswith("_hunter")]
        assert hunters and all(isinstance(bot.get("pet"), dict) and bot["pet"]["entry"] == 8959 for bot in hunters), path
