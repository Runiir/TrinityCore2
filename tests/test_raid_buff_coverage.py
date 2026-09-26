"""Round 5 buff and debuff coverage audit of the canonical BWD 10N shards (tools/raid_program/raid_buff_coverage.py).

Two columns: provisioned (a member has the provider) and runtime (an enabled rotation row or a runtime code
contract casts it). Runtime casts come only from the checked-in export of enabled bot_rotation_action rows, the
route readiness list, the persistent self-buff contract with class owner C's canonical raid buffs, the rogue poison
setup, the runtime totems, encounter lust duties with the canonical boss lust fallback and C's major armor upkeep
rows; never from the JSON action profiles. Gated rows and cast-once readiness buffs are runtime caveats.

The scoring tests expect C's round 5 runtime (patches 01 and 02) in the tree and fail closed without it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools.bot_ml.build_validation_provisioning import bot_spell_ids
from tools.raid_program import raid_buff_coverage as coverage
from tools.raid_program.raid_shard_scenarios import build_plan

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
RUNTIME_ACTIONS = ROOT / "experiments/configs/raid_runtime_actions/blackwing_descent_10n.json"
EVIDENCE = ROOT / "artifacts/cata_raid_program/round4_batch1_20260926.tar.gz"
BOTS = ROOT / "src/server/game/Bots"
ENCOUNTERS = BOTS / "Content/Raids/BlackwingDescent/Encounters"
BALANCE_SHARDS = {"magmaw", "atramedes"}
FERAL_SHARDS = {"omnotron", "chimaeron", "maloriak", "nefarian", "full"}
ROUND5_RUNTIME = (coverage.RAID_PERSISTENT_BUFFS, coverage.RAID_BOSS_LUST, coverage.RAID_MAJOR_ARMOR)

pytestmark = pytest.mark.skipif(not (coverage.DEFAULT_DBC_DIR / "Talent.dbc").is_file()
                                or not (ROOT / "dataset/world_knowledge/trainers.jsonl").is_file(),
                                reason="client DBCs or trainers not hydrated")


@pytest.fixture(scope="module")
def report() -> dict:
    missing = [str(path.relative_to(ROOT)) for path in ROUND5_RUNTIME if not path.is_file()]
    assert not missing, f"class owner C's round 5 runtime is not integrated: {missing}"
    return coverage.composition_coverage(COMPOSITION)


def shard(report: dict, boss: str) -> dict:
    return next(row for row in report["shards"] if row["boss_key"] == boss)


def with_composition(tmp_path: Path, edit) -> Path:
    composition = json.loads(COMPOSITION.read_text())
    edit(composition)
    path = tmp_path / "composition.json"
    path.write_text(json.dumps(composition))
    return path


def with_export(tmp_path: Path, spec_tag: str, edit) -> Path:
    export = json.loads(RUNTIME_ACTIONS.read_text())
    for row in export["profiles"]:
        if row["spec_tag"] == spec_tag:
            row["actions"] = edit(row["actions"])
    path = tmp_path / "runtime_actions.json"
    path.write_text(json.dumps(export))
    return path


def test_provisioned_and_runtime_are_scored_separately_per_shard(report):
    assert len(coverage.CATEGORIES) == 23
    assert report["runtime_actions"]["path"] == str(RUNTIME_ACTIONS.relative_to(ROOT))
    assert set(report["canonical_runtime_sources"].values()) == {True}
    assert "not proof the buff is up" in report["columns"]["runtime"]
    for row in report["shards"]:
        boss = row["boss_key"]
        bleed = ["bleed_damage_taken"] if boss in BALANCE_SHARDS else []
        assert row["canonical_raid"] is True
        assert row["provisioned"]["missing"] == bleed, boss
        assert row["runtime"]["missing"] == ["damage_pct"] + bleed, boss
        assert row["provisioned_only"] == ["damage_pct"], boss  # Communion's +3%: 63531 is never applied
        assert row["runtime"]["decision_scale"] == f"{19 - len(bleed)}/20"
        runtime, declared = row["providers"]["runtime"], row["providers"]["provisioned"]
        assert all({label.split("@")[0] for label in runtime[key]} <= set(declared[key]) for key in runtime)
        assert runtime["physical_damage_taken"] == ["pet:55749@autocast"]  # the Ravager's Ravage
        assert runtime["stamina"] == ["discipline_priest:21562@self_buff"]  # recast after a wipe
        assert runtime["armor"] == ["holy_paladin:465@self_buff"]
        assert runtime["attack_power_pct"] == ["blood_death_knight:53138@passive", "holy_paladin:19740@self_buff",
                                               "retribution_paladin:19740@self_buff"]  # Might under the Mark
        assert {"holy_paladin:19740@self_buff", "retribution_paladin:19740@self_buff"} <= set(runtime["mp5"])
        assert runtime["major_armor"] == (["balance_druid:770@raid_override"] if boss in BALANCE_SHARDS
                                          else ["feral_druid_tank:16857@raid_override"])
        assert runtime["lust"] and all(label.endswith("@lust") for label in runtime["lust"])
        assert runtime["damage_pct"] == [] and "retribution_paladin:31876" in declared["damage_pct"]
        assert any(label.endswith(":3738@totem") for label in runtime["spell_haste"])
        assert "survival_hunter:53290@passive" in runtime["melee_haste"]
        caveats = {"damage_reduction", "defensive_cooldowns"} | ({"bleed_damage_taken"} if boss in FERAL_SHARDS else set())
        assert set(row["runtime_caveats"]) == caveats, boss
        assert "gated by min_enemies" in row["runtime_caveats"]["damage_reduction"]  # Scarlet Fever via Blood Boil
        assert "gated by ally_health" in row["runtime_caveats"]["defensive_cooldowns"]  # Pain Suppression
    assert shard(report, "magmaw")["lust_encounters"] == {"strategy": ["magmaw"], "fallback": []}
    assert shard(report, "atramedes")["lust_encounters"] == {"strategy": [], "fallback": ["atramedes"]}
    full = shard(report, "full")["lust_encounters"]
    assert (sorted(full["strategy"]), sorted(full["fallback"])) == (
        ["chimaeron", "maloriak"], ["atramedes", "magmaw", "nefarian", "omnotron"])


def test_a_json_profile_spell_missing_from_the_db_rows_is_only_provisioned(report):
    # Demoralizing Roar 99 is in the Feral tank's JSON action profile and the druid knows it, but no enabled
    # bot_rotation_action row, readiness row or contract row casts it.
    feral = set(bot_spell_ids({"class_spec": "feral_druid_tank"}, None))
    exported = coverage.load_runtime_actions(RUNTIME_ACTIONS)[(11, "feral_druid_tank", "tank")]
    assert 99 in feral and 99 not in exported
    for boss in FERAL_SHARDS:
        providers = shard(report, boss)["providers"]
        assert "feral_druid_tank:99" in providers["provisioned"]["damage_reduction"]
        assert not any(label.startswith("feral_druid_tank:99") for label in providers["runtime"]["damage_reduction"])


def test_the_export_is_the_runtime_source(report, tmp_path):
    path = with_export(tmp_path, "feral_druid_tank", lambda actions: actions + [{"spell": 99, "category": "debuff"}])
    patched = coverage.composition_coverage(COMPOSITION, runtime_actions=path)
    for boss in FERAL_SHARDS:
        row = shard(patched, boss)
        assert "feral_druid_tank:99@rotation" in row["providers"]["runtime"]["damage_reduction"]
        assert "damage_reduction" not in row["runtime_caveats"]  # an ungated row lifts the Blood Boil caveat
    source = Path(coverage.__file__).read_text()
    assert "WorldDatabase" not in source and "mysql" not in source.lower()  # no live-DB dependency


def test_an_active_talent_counts_at_runtime_only_when_cast(report, tmp_path):
    path = with_export(tmp_path, "discipline_priest", lambda actions: [a for a in actions if a["spell"] != 33206])
    patched = coverage.composition_coverage(COMPOSITION, runtime_actions=path)
    for row in patched["shards"]:
        assert "discipline_priest:33206" in row["providers"]["provisioned"]["defensive_cooldowns"]
        assert "defensive_cooldowns" in row["provisioned_only"]


def test_without_a_mark_druid_the_paladins_keep_kings(report, monkeypatch):
    monkeypatch.setattr(coverage, "MARK_OF_THE_WILD", 0)  # nobody knows it: GroupHasMarkOfTheWild is false
    kings = coverage.composition_coverage(COMPOSITION)
    for row in kings["shards"]:
        runtime = row["providers"]["runtime"]
        assert "retribution_paladin:20217@self_buff" in runtime["stats"]
        assert not any(":19740@" in label for label in runtime["attack_power_pct"] + runtime["mp5"])
    assert shard(kings, "chimaeron")["runtime"]["missing"] == ["damage_pct", "mp5"]  # Healing Stream, not Mana Spring


def test_the_checked_in_export_names_its_evidence_and_covers_every_canonical_profile():
    export = json.loads(RUNTIME_ACTIONS.read_text())
    assert export["schema"] == coverage.RUNTIME_ACTIONS_SCHEMA
    assert export["source"]["evidence"] == str(EVIDENCE.relative_to(ROOT))
    pointer = (EVIDENCE.parent / (EVIDENCE.name + ".dvc")).read_text()
    assert f"md5: {export['source']['evidence_md5']}" in pointer
    assert all(row["profile_source"].startswith("world_db_bot_rotation_profile_") for row in export["profiles"])
    specs = {(row["class"], coverage.runtime_spec_tag(row["class_spec"]), row["role"])
             for plan_shard in build_plan(COMPOSITION)["shards"] for row in plan_shard["bots"]}
    assert specs == set(coverage.load_runtime_actions(RUNTIME_ACTIONS))
    rows = {(row["spec_tag"], action["spell"]): action for row in export["profiles"] for action in row["actions"]}
    assert rows[("blood_death_knight", 48721)]["gates"] == ["min_enemies"]  # Blood Boil (aoe)
    assert rows[("discipline_priest", 33206)]["gates"] == ["ally_health"]  # Pain Suppression
    assert "gates" not in rows[("blood_death_knight", 45477)]  # Icy Touch


def test_gate_kinds_come_from_the_category_and_the_observed_rejections():
    assert coverage.inferred_gates("aoe", set()) == ["min_enemies"]
    assert coverage.inferred_gates("threat_build", {"enemy_count_too_high", "global_cooldown"}) == ["max_enemies"]
    assert coverage.inferred_gates("external_defensive", set()) == ["ally_health"]
    assert coverage.inferred_gates("heal_fast", {"target_health_gate"}) == ["ally_health", "target_health"]
    assert coverage.inferred_gates("buff", {"maintain_aura_active"}) == []
    # The mask's reject reasons: BuildCandidates and the resolver admission that rewrites them.
    reasons = "".join((BOTS / name).read_text() for name in (
        "BotClassSpecActionProfileCandidates.cpp", "BotWorldPopulationMgrCombatResolverAdmission.cpp"))
    assert all(f'"{reason}"' in reasons for reason in coverage.GATE_REJECTS)


@pytest.mark.skipif(not EVIDENCE.is_file(), reason="round 4 evidence tarball not hydrated (dvc pull)")
def test_the_export_is_reproducible_from_the_dvc_evidence():
    export = coverage.export_runtime_actions(EVIDENCE, json.loads(RUNTIME_ACTIONS.read_text())["source"]["run"])
    assert coverage.render_runtime_actions(export) == RUNTIME_ACTIONS.read_text()


def test_the_canonical_scope_is_the_runtime_scope():
    scope = (BOTS / "BotCanonicalRaidScope.h").read_text()
    assert 'DiagnosticSuffix = "_diagnostic"' in scope and "IsCopyToken(scenarioId.substr(cut + 1))" in scope
    for scenario_id, canonical in (("blackwing_descent_10n_magmaw_c0_diagnostic", True),
                                   ("blackwing_descent_10n_full_c0", True), ("blackwing_descent_10n_full_c12", True),
                                   ("blackwing_descent_10n_magmaw_diagnostic", False), ("blackwing_descent_10n", False),
                                   ("stonecore_5h", False), ("blackwing_descent_10n_magmaw_cx_diagnostic", False)):
        assert coverage.is_canonical_scenario(scenario_id) is canonical, scenario_id


def test_the_canonical_raid_buffs_are_the_runtime_contract():
    source = coverage.RAID_PERSISTENT_BUFFS.read_text()
    body = source[source.index("CanonicalRows[] ="):]
    body = body[:body.index("};")]
    names = {"PowerWordFortitude": coverage.POWER_WORD_FORTITUDE}
    classes = {"PALADIN": 2, "PRIEST": 5}
    rows = tuple((classes[name], None if role == "nullptr" else role.strip('"'), None if spec == "nullptr" else spec.strip('"'),
                  int(names.get(spell, spell) if not spell.isdigit() else spell))
                 for name, role, spec, spell in re.findall(
                     r'\{ CLASS_([A-Z_]+), (nullptr|"[a-z]+"), (nullptr|"[a-z_]+"), (\w+),', body))
    assert rows == coverage.CANONICAL_BUFF_ROWS
    assert "BlessingOfMight =\n    { CLASS_PALADIN, nullptr, nullptr, 19740," in source
    assert f"MarkOfTheWild = {coverage.MARK_OF_THE_WILD};" in source
    assert f"BlessingOfKings = {coverage.BLESSING_OF_KINGS};" in source
    assert "if (spellId == PowerWordFortitude)\n        return true;" in source  # readiness Fortitude dropped
    assert "return spellId == BlessingOfKings && markOfTheWildInGroup();" in source  # readiness Kings under Might
    assert "Retribution Aura Overflow 63531" in source  # Communion's +3% is not credited


def test_the_boss_lust_fallback_scope_is_the_runtime_scope():
    source = coverage.RAID_BOSS_LUST.read_text()
    owns = source[source.index("inline bool StrategyOwnsLust"):]
    owns = owns[:owns.index("\n}\n")]
    assert "nodeId == BotEncounter::Chimaeron::EncounterNode || nodeId == MaloriakEncounterNode" in owns
    assert "BotEncounter::MagmawBloodlust::IsMagmawBloodlustScenario(scenarioId)" in owns
    assert set(coverage.LUST_DUTY_ENCOUNTERS["blackwing_descent"]) == {"magmaw", "maloriak", "chimaeron"}
    assert coverage.LUST_OWN_SHARD_ONLY["blackwing_descent"] == ("magmaw",)
    runtime = (BOTS / "BotWorldPopulationMgrRaidBossLust.cpp").read_text()
    assert "BotCanonicalRaidScope::IsCanonicalRaid(" in runtime and 'ValidationRouteKind != "boss"' in runtime


def test_the_major_armor_rows_are_the_runtime_upkeep_rows():
    source = coverage.RAID_MAJOR_ARMOR.read_text()
    assert "FaerieFireSpellId = 770;" in source and "FaerieFireFeralSpellId = 16857;" in source
    upkeep = re.sub(r"\s+", " ", source[source.index("inline BotActionProfileSpell UpkeepRow"):])
    assert 'profile.SpecTag == "balance_druid") { spell.SpellId = FaerieFireSpellId;' in upkeep
    assert 'profile.SpecTag == "feral_druid_tank") { spell.SpellId = FaerieFireFeralSpellId;' in upkeep
    assert coverage.MAJOR_ARMOR_ROWS == ((11, "dps", "balance_druid", 770), (11, "tank", "feral_druid_tank", 16857))


def test_the_spec_tag_aliases_are_the_runtime_aliases():
    header = (BOTS / "BotClassSpecActionProfileInternal.h").read_text()
    body = header[header.index("CanonicalSpecTag"):]
    aliases = dict(re.findall(r'\{ "([a-z_]+)", "([a-z_]+)" \}', body[:body.index("};")]))
    assert aliases == coverage.RUNTIME_SPEC_TAG


def test_the_readiness_buff_table_is_the_runtime_list():
    source = (BOTS / "BotWorldPopulationMgrDungeonRoute.cpp").read_text()
    body = source[source.index("static ActiveBuffRequirement const requirements[]"):]
    body = body[:body.index("};")]
    classes = {"WARRIOR": 1, "PALADIN": 2, "HUNTER": 3, "PRIEST": 5, "DEATH_KNIGHT": 6, "MAGE": 8, "DRUID": 11}
    rows = tuple((classes[name], None if role == "nullptr" else role.strip('"'), int(spell), party == "true")
                 for name, role, spell, party in re.findall(
                     r'\{ CLASS_([A-Z_]+), (nullptr|"[a-z]+"), (\d+), \{[^}]*\}, "[a-z_]+", (true|false) \}', body))
    assert rows == coverage.READINESS_BUFFS
    assert '{ CLASS_PRIEST, nullptr, 21562, { 21562 }' in body  # the dummy never matches 79104/79105
    assert 'ReadinessPartyCoverageSignature[attemptKey] == "cast_once"' in source
    assert "BotRaidPersistentBuffs::ReadinessOwnedByContract(canonicalRaid, requirement.SpellId," in source


def test_the_self_buff_contract_and_poison_setup_are_parsed_from_the_runtime():
    contract = (BOTS / "BotPersistentSelfBuffContract.h").read_text()
    assert len(coverage.self_buff_contract()) == contract.count("{ CLASS_")
    assert (2, None, None, 20217) in coverage.self_buff_contract()
    setup = (BOTS / "BotWorldPopulationMgrPersistentSetup.cpp").read_text()
    for item, spell_id in coverage.ROGUE_POISONS:
        assert re.search(rf"EQUIPMENT_SLOT_(MAIN|OFF)HAND, {item}, {spell_id},", setup)
    assert "BotRaidPersistentBuffs::Contract(BotPersistentSelfBuffContract::Buffs," in setup


def test_the_totem_rule_is_the_runtime_rule():
    providers = re.search(r"OtherMeleeHasteProviders\[\] = \{ ([^}]*) \}", (BOTS / "BotRaidShamanTotems.h").read_text())
    assert tuple(int(value) for value in providers.group(1).split(",")) == coverage.OTHER_MELEE_HASTE
    execution = (BOTS / "BotWorldPopulationMgrCombatExecution.cpp").read_text()
    for fragment in ("desiredEarthTotemSpell = isElemental ? 0 : 8075",
                     "desiredWaterTotemSpell = isElemental ? 5675 : 5394",
                     "desiredAirTotemSpell = isElemental || raidWrathOfAir ? 3738 : 8512"):
        assert fragment in execution
    resto = {"class_spec": "restoration_shaman"}
    assert coverage.runtime_totems(resto, {3738}, {53290}) == {8075, 5394, 3599, 3738}
    assert coverage.runtime_totems(resto, {3738}, set()) == {8075, 5394, 3599, 8512}
    assert coverage.runtime_totems({"class_spec": "elemental_shaman"}, set(), set()) == {5675, 3599, 3738}


def test_the_lust_duties_are_the_encounters_with_raid_haste_code():
    with_lust = {folder.name.lower() for folder in ENCOUNTERS.iterdir() if folder.is_dir() and any(
        re.search(r"\b80353\b|BotMagmawBloodlust\.h|TimeWarpSpell", path.read_text())
        for path in folder.iterdir() if path.suffix in (".h", ".cpp"))}
    assert with_lust == set(coverage.LUST_DUTY_ENCOUNTERS["blackwing_descent"])
    magmaw = (ENCOUNTERS / "Magmaw/BotMagmawBloodlust.h").read_text()
    assert 'CohortScenarioPrefix = "blackwing_descent_10n_magmaw_c"' in magmaw


def test_the_catalog_wolf_leaves_physical_damage_taken_open(report, tmp_path):
    def drop_pet(composition):
        for row in composition["characters"]:
            if row["character_key"] == "hunter":
                del row["pet"]
    wolf = coverage.composition_coverage(with_composition(tmp_path, drop_pet))
    for row in wolf["shards"]:
        assert "physical_damage_taken" in row["provisioned"]["missing"]
        assert "physical_damage_taken" in row["runtime"]["missing"]
        assert row["providers"]["runtime"]["crit"]  # Furious Howl is redundant


def test_a_pet_spell_counts_at_runtime_only_when_autocast(report, tmp_path):
    def disable_ravage(composition):
        for row in composition["characters"]:
            if row["character_key"] == "hunter":
                row["pet"]["spells"] = [dict(value, active=0x81) if isinstance(value, dict) and value["id"] == 50518
                                        else value for value in row["pet"]["spells"]]
    manual = coverage.composition_coverage(with_composition(tmp_path, disable_ravage))
    for row in manual["shards"]:
        assert row["providers"]["provisioned"]["physical_damage_taken"] == ["pet:55749"]
        assert "physical_damage_taken" in row["provisioned_only"]


def test_the_composition_audit_matches_the_tool(report):
    audit = json.loads(COMPOSITION.read_text())["buff_coverage_declared"]["survival_recheck"]["round5_audit"]
    assert str(RUNTIME_ACTIONS.relative_to(ROOT)) in audit["tool"]
    for row in report["shards"]:
        declared = audit["after"][row["boss_key"]]
        assert declared["provisioned"].split(" ")[0] == row["provisioned"]["decision_scale"], row["boss_key"]
        assert declared["runtime"].split(" ")[0] == row["runtime"]["decision_scale"], row["boss_key"]
        assert sorted(declared["runtime_caveats"]) == sorted(row["runtime_caveats"]), row["boss_key"]
    only = {category for row in report["shards"] for category in row["provisioned_only"]}
    assert only == {"damage_pct"} and set(audit["provisioned_only"]) == {"damage_pct_3"}
