"""Round 3 package M: every canonical raid-shard bot carries its prepull consumables and native raid haste.

Evidence (round-2 batch, 2026-09-25): the prepull candidate failed closed for the whole raid on
`raid_prepull_unknown_spec_contract_beast_mastery_hunter`, and the Magmaw Bloodlust owner reported
`blocked_spell_not_in_shaman_spellbook` because the Draenei shaman was provisioned without Heroism.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.raid_program import raid_shard_plan as rsp

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
CONTRACTS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidConsumableContracts.cpp"
GENERATED = ROOT / "src/server/game/Bots/BotCalibrationFixtureContractGenerated.h"
DBC = ROOT / "data/dbc/enUS"
HEROISM, BLOODLUST = 32182, 2825
# Specs whose runtime contract is still a pending shared patch (.git/round3_patches/m/R3M1_*).
CONTRACT_PATCH_PENDING = {"beast_mastery_hunter"}


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
    assert all(bot["spells"] == [HEROISM] and bot["race"] == 11 for bot in shamans)
    assert all("spells" not in bot for shard in plan["shards"] for bot in shard["bots"]
               if bot["character_key"] != "shaman")


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
