from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / 'src/server/game/Bots'


def test_patrol_production_caller_retains_shared_handoff(tmp_path):
    text = (BOTS / 'BotWorldPopulationMgrValidationPatrolPull.cpp').read_text()
    start = text.index('        if (Cohort().Config.ValidationRoutePatrolPullPolicy.empty())')
    prefix = text[start:text.index('        auto exactRosterAtAnchor', start)]
    global_start = text.index('        for (WorldBotState const& cohortState : Party().Bots)\n            if (Player* member')
    suppression = text[global_start:text.index('        auto const roster', global_start)]
    tail = text[text.index('        enrollValidationRoutePackMember(source, true);'):]
    # Execute actual lookup/invalidation/early-handoff, global suppression and
    # engaged completion blocks. Initial unengaged pull machinery is stubbed;
    # existing module/geometry tests separately retain its native contracts.
    header = BOTS / 'BotValidationPatrolPullState.h'
    state_include = '#include "Bots/BotValidationPatrolPullState.h"' if header.exists() else ''
    state_field = 'BotValidationPatrolPull::State ValidationRoutePatrolPull;' if header.exists() else ''
    source = tmp_path / 'patrol.cpp'
    source.write_text(r'''
#include <cassert>
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
''' + state_include + r'''
struct ObjectGuid {
    using LowType = uint64;
    uint64 Value = 0;
    uint64 GetRawValue() const { return Value; }
    uint64 GetCounter() const { return Value; }
    void Clear() { Value = 0; }
};
struct Player;
struct Unit {
    ObjectGuid Guid;
    virtual Player* ToPlayer() { return nullptr; }
    ObjectGuid GetGUID() const { return Guid; }
};
struct Map;
struct Player : Unit {
    Map* World = nullptr;
    uint32 MapId = 669, InstanceId = 2;
    Player* ToPlayer() override { return this; }
    Map* GetMap() { return World; }
    uint32 GetMapId() { return MapId; }
    uint32 GetInstanceId() { return InstanceId; }
};
struct Creature : Unit {
    Map* World = nullptr;
    Unit* Victim = nullptr;
    bool Alive = true, InWorld = true, Engaged = false, Evading = false;
    float Distance = 4;
    Map* GetMap() { return World; }
    bool IsAlive() { return Alive; }
    bool IsInWorld() { return InWorld; }
    unsigned GetHealth() { return Alive ? 100 : 0; }
    bool IsInEvadeMode() { return Evading; }
    Unit* GetVictim() { return Victim; }
    float GetExactDist(float, float, float) { return Distance; }
};
struct Map { Creature* Source = nullptr; Creature* GetCreatureBySpawnId(uint64) { return Source; } };
struct WorldBotState { Player* Actor; ObjectGuid TargetGuid; std::string LastNoProgressReason; };
struct Roster { std::string Role; bool Active = true, LeaseOwned = true; };
struct Configuration {
    std::string ValidationRoutePatrolPullPolicy = "ranged_patrol_to_anchor";
    unsigned ValidationRoutePatrolPullOwnerRosterSlot = 9;
    float ValidationRoutePatrolWaitToleranceYards = 5;
    float ValidationRoutePatrolAnchorToleranceYards = 5;
    float ValidationRoutePatrolEngageRadiusYards = 20;
    float ValidationRoutePatrolFutureGuardMarginYards = 5;
    float ValidationRouteClusterRadiusYards = 5;
    float ValidationRouteX = -333, ValidationRouteY = -99, ValidationRouteZ = 214;
};
struct CohortData {
    Configuration Config;
    uint64 AttemptId = 1;
    struct { uint64 WipeGeneration = 0; std::map<uint64, Roster> RosterByGuid; } Raid;
};
struct PartyData {
    std::vector<WorldBotState> Bots;
    uint64 ValidationRouteGeneration = 2;
''' + state_field + r'''
};
namespace BotRaidAreaAuthority {
std::map<uint64, bool> Suppressed;
unsigned SuppressionWrites = 0;
void SetAllOffenseSuppressed(uint64 guid, bool value) {
    Suppressed[guid] = value;
    if (value) ++SuppressionWrites;
}
}
struct Manager {
    CohortData C; PartyData P;
    uint64 SourceSpawnId = 1234;
    CohortData& Cohort() { return C; }
    PartyData& Party() { return P; }
    Player* GetLoadedBot(WorldBotState const& state) { return state.Actor; }
    bool Evaluate(WorldBotState& state, Player* bot) {
        Unit* target = nullptr;
        std::string situation, action;
        auto currentValidationRouteTargetSpawnId = [this] { return SourceSpawnId; };
        auto isValidationCohortCombatLinked = [](Creature const* source) { return source->Engaged; };
        auto enrollValidationRoutePackMember = [](Creature*, bool) {};
''' + prefix + suppression + r'''
        bool const sourceEngaged = isValidationCohortCombatLinked(source);
        if (!sourceEngaged) return hold("initial_pull_wait", source);
''' + tail + r'''
};
int main() {
    Map world;
    Player tank, dps;
    tank.Guid.Value = 30002; dps.Guid.Value = 30008;
    tank.World = dps.World = &world;
    Creature source; source.Guid.Value = 27; source.World = &world;
    world.Source = &source;
    Manager manager;
    manager.C.Raid.RosterByGuid[30002].Role = "tank";
    manager.C.Raid.RosterByGuid[30008].Role = "dps";
    manager.P.Bots = {{&tank, {}, {}}, {&dps, {}, {}}};
    auto tick = [&](unsigned index) { return manager.Evaluate(manager.P.Bots[index], manager.P.Bots[index].Actor); };
    assert(tick(1)); // Unengaged initial staging remains closed.
    assert(BotRaidAreaAuthority::Suppressed[30008]);
    source.Engaged = true; source.Victim = &dps;
    assert(!tick(0)); // Tank exemption alone does not complete shared handoff.
    source.Distance = 45;
    assert(tick(1));
    source.Distance = 4; source.Victim = &tank;
    manager.C.Raid.RosterByGuid[30002].Active = false;
    assert(!tick(0)); // Original per-actor release is preserved.
    source.Distance = 45;
    assert(tick(1)); // An inactive tank cannot complete shared handoff.
    manager.C.Raid.RosterByGuid[30002].Active = true;
    manager.C.Raid.RosterByGuid[30002].LeaseOwned = false;
    source.Distance = 4;
    assert(!tick(0));
    source.Distance = 45;
    assert(tick(1)); // Nor can a tank without its roster lease.
    manager.C.Raid.RosterByGuid[30002].LeaseOwned = true;
    source.Distance = 4; source.Victim = &tank;
    assert(!tick(0)); // First actual engaged, in-radius tank handoff.
    assert(!BotRaidAreaAuthority::Suppressed[30002]);
    auto writes = BotRaidAreaAuthority::SuppressionWrites;
    source.Distance = 45; // Later hazard geometry, not a new pull.
    assert(!tick(1));
    assert(BotRaidAreaAuthority::SuppressionWrites == writes);
    assert(!BotRaidAreaAuthority::Suppressed[30002]);
    assert(!BotRaidAreaAuthority::Suppressed[30008]);
    source.Victim = &dps; // Existing tank/taunt policy owns threat recovery.
    assert(!tick(0));
    assert(!tick(1));
    assert(BotRaidAreaAuthority::SuppressionWrites == writes);

    // Production Party() returns Cohort().Party: another cohort has fresh
    // shared state even if every numeric episode identity happens to match.
    Manager otherCohort;
    otherCohort.C = manager.C;
    otherCohort.P.Bots = manager.P.Bots;
    assert(otherCohort.Evaluate(otherCohort.P.Bots[1], &dps));
    assert(!tick(1));

    auto complete = [&] {
        source.Alive = source.InWorld = source.Engaged = true;
        source.Evading = false; source.Distance = 4; source.Victim = &tank;
        world.Source = &source;
        assert(!tick(0));
        source.Distance = 45;
        assert(!tick(1));
    };
    auto mustRestage = [&] { assert(tick(1)); assert(BotRaidAreaAuthority::Suppressed[30008]); complete(); };
    ++manager.C.AttemptId; mustRestage();
    ++manager.C.Raid.WipeGeneration; mustRestage();
    manager.C.Raid.WipeGeneration += (uint64(1) << 32); mustRestage();
    ++manager.P.ValidationRouteGeneration; mustRestage();
    ++manager.SourceSpawnId; mustRestage();
    ++source.Guid.Value; mustRestage();
    ++tank.MapId; ++dps.MapId; mustRestage();
    ++tank.InstanceId; ++dps.InstanceId; mustRestage();
    source.Engaged = false; assert(tick(1)); complete();
    source.Evading = true; assert(tick(1)); complete();
    source.Alive = false; assert(!tick(1)); source.Alive = true; mustRestage();
    source.InWorld = false; assert(!tick(1)); source.InWorld = true; mustRestage();
    world.Source = nullptr; assert(!tick(1)); world.Source = &source; mustRestage();
}
''')
    binary = tmp_path / 'patrol'
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-but-set-variable', '-I', str(ROOT / 'src/server/game'),
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
