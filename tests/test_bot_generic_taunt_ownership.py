from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSupport.cpp"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
SPELL = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSpell.cpp"
BOSS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanics.cpp"


def _extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def _extract_gate(source: str, end_marker: str) -> str:
    start_marker = (
        "        if (candidate.Category == BotCombatActionCategory::Taunt\n"
        "            && (!target->GetVictim() || target->GetVictim() == bot))"
    )
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end].replace("continue;", "return true;")


def _compile_production_probe(tmp_path: Path) -> Path:
    helper = _extract_function(
        SUPPORT.read_text(encoding="utf-8"),
        "bool BotWorldPopulationMgr::HasOtherLiveCohortTankVictim(",
    )
    resolver_gate = _extract_gate(
        RESOLVER.read_text(encoding="utf-8"),
        "        if (candidate.Profile.RequiresTargetNotVictim",
    )
    spell_gate = _extract_gate(
        SPELL.read_text(encoding="utf-8"),
        "        bool selfTarget = candidate.Profile.TargetSelector == \"self\";",
    )

    source = tmp_path / "bot_generic_taunt_ownership.cpp"
    binary = tmp_path / "bot_generic_taunt_ownership"
    source.write_text(
        r'''
#include <cassert>
#include <string>
#include <vector>

struct Map
{
    int Id = 0;
};

struct Player;

struct Unit
{
    Unit const* Victim = nullptr;
    Player const* PlayerView = nullptr;
    Map const* MapView = nullptr;
    bool Alive = true;

    Unit const* GetVictim() const { return Victim; }
    Player const* ToPlayer() const { return PlayerView; }
    bool IsAlive() const { return Alive; }
    Map const* GetMap() const { return MapView; }
};

struct Player : Unit
{
    std::string Role = "dps";

    Player(Map const* map, char const* role, bool alive = true)
    {
        PlayerView = this;
        MapView = map;
        Role = role;
        Alive = alive;
    }
};

struct WorldBotState
{
    Player* Bot = nullptr;
};

struct PartyRuntime
{
    std::vector<WorldBotState> Bots;
};

struct CohortConfig
{
    bool ValidationRouteEnable = false;
    std::string ValidationRouteKind = "boss";
};

struct CohortRuntime
{
    CohortConfig Config;
};

namespace BotCombatActionCategory
{
enum Value
{
    Damage = 0,
    Taunt = 1,
};
}

struct Candidate
{
    BotCombatActionCategory::Value Category = BotCombatActionCategory::Damage;
    std::string RejectReason;
};

class BotWorldPopulationMgr
{
public:
    bool HasOtherLiveCohortTankVictim(Player const* bot,
        Unit const* target) const;
    bool ResolverGate(Player const* bot, Unit const* target,
        BotCombatActionCategory::Value category) const;
    bool SpellGate(Player const* bot, Unit const* target,
        BotCombatActionCategory::Value category) const;

private:
    PartyRuntime _party;
    CohortRuntime _cohort;

    PartyRuntime const& Party() const { return _party; }
    Player* GetBot(WorldBotState const& state) const { return state.Bot; }
    char const* GetDungeonRole(Player* bot) const
    {
        return bot ? bot->Role.c_str() : "dps";
    }
    CohortRuntime const& Cohort() const { return _cohort; }

public:
    void AddPartyMember(Player* member) { _party.Bots.push_back({member}); }
};

''' + helper + r'''

bool BotWorldPopulationMgr::ResolverGate(Player const* bot,
    Unit const* target, BotCombatActionCategory::Value category) const
{
    Candidate candidate;
    candidate.Category = category;
''' + resolver_gate + r'''
    return false;
}

bool BotWorldPopulationMgr::SpellGate(Player const* bot,
    Unit const* target, BotCombatActionCategory::Value category) const
{
    Candidate candidate;
    candidate.Category = category;
''' + spell_gate + r'''
    return false;
}

int main()
{
    Map mapOne{669};
    Map mapTwo{670};
    Player bot(&mapOne, "tank");
    Player otherTank(&mapOne, "tank");
    Player nonTank(&mapOne, "dps");
    Player outsideTank(&mapOne, "tank");
    Player deadTank(&mapOne, "tank", false);
    Player wrongMapTank(&mapTwo, "tank");
    Unit target;
    BotWorldPopulationMgr manager;
    manager.AddPartyMember(&bot);
    manager.AddPartyMember(&otherTank);
    manager.AddPartyMember(&nonTank);
    manager.AddPartyMember(&deadTank);
    manager.AddPartyMember(&wrongMapTank);

    // The actual production helper is the value-level ownership proof. It
    // rejects missing/self victims and every tank that is not a live,
    // same-map, exact Party().Bots member.
    assert(!manager.HasOtherLiveCohortTankVictim(&bot, &target));
    target.Victim = &bot;
    assert(!manager.HasOtherLiveCohortTankVictim(&bot, &target));
    target.Victim = &otherTank;
    assert(manager.HasOtherLiveCohortTankVictim(&bot, &target));
    target.Victim = &nonTank;
    assert(!manager.HasOtherLiveCohortTankVictim(&bot, &target));
    target.Victim = &outsideTank;
    assert(!manager.HasOtherLiveCohortTankVictim(&bot, &target));
    target.Victim = &deadTank;
    assert(!manager.HasOtherLiveCohortTankVictim(&bot, &target));
    target.Victim = &wrongMapTank;
    assert(!manager.HasOtherLiveCohortTankVictim(&bot, &target));

    // Both production candidate gates retain no-victim/self rejection, share
    // the ownership predicate, and keep non-tank pickup eligible.
    target.Victim = nullptr;
    assert(manager.ResolverGate(&bot, &target,
        BotCombatActionCategory::Taunt));
    assert(manager.SpellGate(&bot, &target,
        BotCombatActionCategory::Taunt));
    target.Victim = &bot;
    assert(manager.ResolverGate(&bot, &target,
        BotCombatActionCategory::Taunt));
    assert(manager.SpellGate(&bot, &target,
        BotCombatActionCategory::Taunt));
    target.Victim = &otherTank;
    assert(manager.ResolverGate(&bot, &target,
        BotCombatActionCategory::Taunt));
    assert(manager.SpellGate(&bot, &target,
        BotCombatActionCategory::Taunt));
    for (Player* victim : { &nonTank, &outsideTank, &deadTank, &wrongMapTank })
    {
        target.Victim = victim;
        assert(!manager.ResolverGate(&bot, &target,
            BotCombatActionCategory::Taunt));
        assert(!manager.SpellGate(&bot, &target,
            BotCombatActionCategory::Taunt));
    }

    // The generic filter is category-scoped; an encounter-owned action keeps
    // its direct native executor available even while a tank owns the target.
    target.Victim = &otherTank;
    assert(!manager.ResolverGate(&bot, &target,
        BotCombatActionCategory::Damage));
    assert(!manager.SpellGate(&bot, &target,
        BotCombatActionCategory::Damage));
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return binary


def test_production_taunt_helper_and_both_gates_compile_and_replay(tmp_path: Path) -> None:
    binary = _compile_production_probe(tmp_path)
    subprocess.run([str(binary)], check=True, cwd=tmp_path)


def test_encounter_swap_executor_remains_outside_generic_taunt_filter() -> None:
    resolver = RESOLVER.read_text(encoding="utf-8")
    spell = SPELL.read_text(encoding="utf-8")
    boss = BOSS.read_text(encoding="utf-8")
    assert "HasOtherLiveCohortTankVictim(bot, target)" in resolver
    assert "HasOtherLiveCohortTankVictim(bot, target)" in spell
    swap_start = boss.index("    if (tankSwapTriggered && std::string(role) == \"tank\"")
    swap_end = boss.index("    if (result.Features.MoveOut", swap_start)
    swap = boss[swap_start:swap_end]
    assert "TryCastCombatSpell(bot, result.Target, candidate.SpellId)" in swap
    assert "ResolveProfileCombatAction(" not in swap
    assert "HasOtherLiveCohortTankVictim" not in swap
