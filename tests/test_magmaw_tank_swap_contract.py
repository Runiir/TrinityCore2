from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
BOSS_MECHANICS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanics.cpp"


def _magmaw_contracts() -> list[dict[str, object]]:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    return [
        step["mechanic_contract"]
        for scenario in payload["scenarios"] + payload["diagnostic_scenarios"]
        for step in scenario["route"]
        if step.get("node_id") == "bwd.magmaw.encounter"
    ]


def test_both_magmaw_routes_enable_the_native_sweltering_armor_swap() -> None:
    contracts = _magmaw_contracts()
    assert len(contracts) == 2
    for contract in contracts:
        assert contract["main_tank_roster_slot"] == 2
        assert contract["off_tank_roster_slot"] == 1
        assert contract["tank_swap_trigger"] == "debuff_stacks"
        assert contract["tank_swap_aura_id"] == 78199
        assert contract["tank_swap_aura_stacks"] == 1


def _production_debuff_gate(source: str) -> str:
    start = source.index(
        '        if (raidAdapter.TankSwapTrigger == "debuff_stacks")'
    )
    end = source.index(
        '        if (raidAdapter.TankSwapTrigger == "timer")', start
    )
    return source[start:end]


def _production_edge_and_owner_gate(source: str) -> str:
    start = source.index(
        "    if (!tankSwapConditionActive && "
        'raidAdapter.TankSwapTrigger != "timer")'
    )
    end = source.index(
        '    if (tankSwapTriggered && std::string(role) == "tank"', start
    )
    return source[start:end]


def _compile_production_gate_probe(tmp_path: Path) -> Path:
    production = BOSS_MECHANICS.read_text(encoding="utf-8")
    debuff_gate = _production_debuff_gate(production)
    edge_and_owner_gate = _production_edge_and_owner_gate(production)

    source = tmp_path / "magmaw_tank_swap_contract.cpp"
    binary = tmp_path / "magmaw_tank_swap_contract"
    source.write_text(
        r'''
#include <cassert>
#include <cstdint>
#include <string>

using uint32 = std::uint32_t;

struct ObjectGuid
{
    uint32 Value = 0;
    bool IsEmpty() const { return Value == 0; }
    uint32 GetCounter() const { return Value; }
    bool operator==(ObjectGuid const& other) const { return Value == other.Value; }
    bool operator!=(ObjectGuid const& other) const { return !(*this == other); }
};

struct Aura
{
    uint32 Stacks = 0;
    uint32 GetStackAmount() const { return Stacks; }
};

struct Unit
{
    ObjectGuid Guid;
    Aura Debuff;
    bool HasDebuff = false;

    ObjectGuid GetGUID() const { return Guid; }
    Aura const* GetAura(uint32 spellId) const
    {
        return spellId == 78199 && HasDebuff ? &Debuff : nullptr;
    }
};

struct Adapter
{
    std::string TankSwapTrigger = "debuff_stacks";
    uint32 TankSwapAuraId = 78199;
    uint32 TankSwapAuraStacks = 1;
};

struct Assignment
{
    ObjectGuid MainTankGuid;
    ObjectGuid OffTankGuid;
};

struct State
{
    std::string LastRaidTankSwapTriggerKey;
};

bool ShouldSubmitSwap(Unit* currentTank, Unit* bot, char const* role,
    Adapter const& raidAdapter, Assignment const& raidAssignment,
    State& state, bool commitSuccess)
{
    bool tankSwapConditionActive = false;
    bool tankSwapTimerTrigger = false;
    std::string tankSwapTriggerKey;
''' + debuff_gate + edge_and_owner_gate + r'''
    bool const admitted = tankSwapTriggered && std::string(role) == "tank"
        && !nextTankGuid.IsEmpty() && bot->GetGUID() == nextTankGuid
        && currentTank != bot;
    if (admitted && commitSuccess)
        state.LastRaidTankSwapTriggerKey = tankSwapTriggerKey;
    return admitted;
}

int main()
{
    Adapter adapter;
    Unit paladin{{1}, {0}, false};
    Unit deathKnight{{2}, {1}, true};
    Unit foreignTank{{3}, {1}, true};
    Assignment assignment{deathKnight.Guid, paladin.Guid};
    State state;

    // First Sweltering Armor owner hands the body to the configured off tank.
    assert(ShouldSubmitSwap(&deathKnight, &paladin, "tank", adapter,
        assignment, state, true));
    assert(!ShouldSubmitSwap(&deathKnight, &paladin, "tank", adapter,
        assignment, state, false));
    assert(!ShouldSubmitSwap(&deathKnight, &deathKnight, "tank", adapter,
        assignment, state, false));

    // Paladin coverage persists while the new current victim has no debuff;
    // clearing the current-victim condition rearms a later reciprocal edge.
    deathKnight.HasDebuff = false;
    assert(!ShouldSubmitSwap(&paladin, &deathKnight, "tank", adapter,
        assignment, state, false));
    assert(state.LastRaidTankSwapTriggerKey.empty());

    paladin.HasDebuff = true;
    paladin.Debuff.Stacks = 1;
    assert(ShouldSubmitSwap(&paladin, &deathKnight, "tank", adapter,
        assignment, state, true));
    assert(!ShouldSubmitSwap(&paladin, &deathKnight, "tank", adapter,
        assignment, state, false));

    // A victim outside the configured main/off pair has no swap owner.
    state.LastRaidTankSwapTriggerKey.clear();
    assert(!ShouldSubmitSwap(&foreignTank, &paladin, "tank", adapter,
        assignment, state, false));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return binary


def test_two_tank_sweltering_handoff_uses_the_production_caller_gate(
    tmp_path: Path,
) -> None:
    production = BOSS_MECHANICS.read_text(encoding="utf-8")
    assert "memberState.LastRaidTankSwapTriggerKey = tankSwapTriggerKey;" in production
    assert "TryCastCombatSpell(bot, result.Target, candidate.SpellId)" in production
    binary = _compile_production_gate_probe(tmp_path)
    subprocess.run([str(binary)], check=True, cwd=tmp_path)
