from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrEncounterJson.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BuildDungeonTrashPackJson",
    "BuildBossMechanicsJson",
    "BuildRaidRoleAssignmentJson",
    "BuildRaidPositioningAnchorsJson",
    "BuildRaidMechanicAdapterJson",
    "BuildRaidGearTargetPlanJson",
    "BuildHeroicRaidProgressionJson",
)


def test_encounter_json_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrEncounterJson.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_encounter_json_preserves_dungeon_and_boss_mechanic_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "mechanic_families",
        "interrupt_priority",
        "party_average_hp_pct",
        "mechanic_embedding",
        "requires_interrupt",
        "tank_spike",
        "adds_active",
        "spell_tags",
    ):
        assert marker in module


def test_encounter_json_preserves_raid_assignment_and_progression_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "roster_slot_id",
        "lease_role_slot",
        "formation_family",
        "contract_resolved",
        "ready_for_heroic_raid",
        "heroic_raid_boss_kills",
        "BuildSpellTagJson",
    ):
        assert marker in module
