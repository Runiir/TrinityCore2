from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
BOSS_MECHANICS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrTankSwap.cpp"


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
    assert "TryCastCombatSpell(bot, result.Target, candidate.SpellId, forceFacing)" in production
    binary = _compile_production_gate_probe(tmp_path)
    subprocess.run([str(binary)], check=True, cwd=tmp_path)


def _method(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(signature)


def test_adaptive_swap_crosses_submission_kernel_native_cast_and_movement(tmp_path: Path) -> None:
    bots = ROOT / "src/server/game/Bots"
    production = BOSS_MECHANICS.read_text()
    # This is the missing production caller, not a synthetic ShouldSubmitSwap.
    assert "SubmitAdaptiveTankSwapCandidate(context);" in (
        bots / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
    ).read_text()
    submit = _method(production, "void BotWorldPopulationMgr::SubmitAdaptiveTankSwapCandidate(")
    swap = _method(production, "bool BotWorldPopulationMgr::TryBossTankSwap(")
    cast = _method((bots / "BotWorldPopulationMgrCombatSpell.cpp").read_text(),
                   "bool BotWorldPopulationMgr::TryCastCombatSpell(")
    facing = _method((ROOT / "src/server/game/Entities/Unit/Unit.cpp").read_text(),
                     "void Unit::SetFacingToObject(")
    source = tmp_path / "adaptive_swap.cpp"
    binary = tmp_path / "adaptive_swap"
    source.write_text(r'''
#include "Bots/BotActionArbiter.h"
#include <cassert>
#include <memory>
#include <algorithm>
#include <string>
#include <vector>
using namespace BotActionArbitration;
uint64 NowMs() { return 100; }
ObjectGuid guid(uint32 value) { return ObjectGuid(HighGuid::Player, value); }
struct Aura { uint32 GetStackAmount() const { return 1; } };
struct SpellInfo { int PreventionType=0; float GetMaxRange(bool) const { return 30; } };
struct History { bool HasGlobalCooldown(SpellInfo const*) const { return false; }
 bool IsReady(SpellInfo const*) const { return true; } };
struct SpellMgr { SpellInfo Info; SpellInfo const* GetSpellInfo(uint32) { return &Info; } } mgr;
auto* sSpellMgr=&mgr;
constexpr int UNIT_STATE_CONTROLLED=1, UNIT_STATE_CASTING=2, SPELL_PREVENTION_TYPE_SILENCE=1,
 SPELL_PREVENTION_TYPE_PACIFY=2, UNIT_FIELD_FLAGS=0, UNIT_FLAG_SILENCED=1, UNIT_FLAG_PACIFIED=2,
 SPELL_CAST_OK=0;
struct WorldObject {};
struct Spline { bool Final=false; uint32 Id=7; bool Finalized() const { return Final; } };
struct Creature;
struct Unit : WorldObject {
 ObjectGuid Id; Unit* Victim=nullptr; bool Debuffed=false, Alive=true, InCombat=true;
 bool Moving=true, NativeOk=true; int Casts=0; uint32 Entry=0; Spline Path;
 Spline* movespline=&Path; Aura Debuff; History Hist;
 explicit Unit(uint32 id=0):Id(guid(id)){}
 ObjectGuid GetGUID() const { return Id; } Unit* GetVictim() const { return Victim; }
 Aura const* GetAura(uint32 id) const { return id==78199 && Debuffed ? &Debuff:nullptr; }
 bool IsAlive() const { return Alive; } bool IsInCombat() const { return InCombat; }
 bool IsInWorld() const { return true; } int GetMap() const { return 1; }
 uint32 GetEntry() const { return Entry; } uint32 GetSpawnId() const { return 1; }
 bool IsValidAttackTarget(Unit const* p) const { return p && p!=this; }
 bool IsWithinLOSInMap(Unit const*) const { return true; }
 bool IsWithinDistInMap(Unit const*,float) const { return true; }
 bool HasUnitState(int) const { return false; } bool HasFlag(int,int) const { return false; }
 History* GetSpellHistory() { return &Hist; }
 Creature const* ToCreature() const { return nullptr; }
 int CastSpell(Unit*,uint32,bool) { ++Casts; return NativeOk?SPELL_CAST_OK:1; }
 bool IsStopped() const { return !Moving; }
 float GetPositionX() const { return 0; } float GetPositionY() const { return 0; }
 float GetPositionZ() const { return 0; } float GetAngle(WorldObject const*) const { return 0; }
 void UpdateSplineMovement(int) {}
 void SetFacingToObject(WorldObject const*,bool force=true);
};
struct Creature : Unit {};
using Player=Unit;
namespace Movement {
struct MoveSplineInit { Unit* U; explicit MoveSplineInit(Unit* u):U(u){}
 void MoveTo(float,float,float,bool){} void SetFacing(float){}
 void Launch(){++U->Path.Id; U->Path.Final=true; U->Moving=false;}
}; }
namespace BotRaidAreaAuthority {
bool IsAllOffenseSuppressed(uint64){return false;}
bool IsProtectedEncounterTarget(uint64,uint32,uint32,uint64){return false;}
}
bool HasNearbyProtectedEncounterTarget(Player*,Unit*){return false;}
bool SpellHasHostileMultiTargetSemantics(SpellInfo const*){return false;}
bool HasPowerForSpell(Player*,SpellInfo const*){return true;}
Unit* NativeBoss=nullptr;
namespace ObjectAccessor { Unit* GetUnit(Player&,ObjectGuid id) {return NativeBoss && NativeBoss->GetGUID()==id?NativeBoss:nullptr;} }
struct Actor {ObjectGuid Guid;};
struct Board {std::string NativeBossState="in_progress"; Actor Boss{guid(39)};};
namespace BotEncounter::MagmawBloodlust {
constexpr uint32 BossEntry=41570;
Actor const* FindBoss(Board const& b){return &b.Boss;}
}
struct Contract {
 bool MechanicContractResolved=true; std::string NodeId="bwd.magmaw.encounter",MechanicContractId="magmaw";
 std::string TankSwapTrigger="debuff_stacks",TankSwapPhase;
 uint32 TankSwapAuraId=78199,TankSwapAuraStacks=1,TankSwapIntervalMs=0,
 TankSwapTriggerSpellId=0,TankSwapAddEntry=0,MainTankRosterSlot=2,OffTankRosterSlot=1;
 std::vector<uint32> TargetEntries{41570};
};
struct Features {bool RaidEncounter=true;uint32 CastSpellId=0;ObjectGuid PriorityAddGuid;float DangerScore=0;};
struct Assignment {ObjectGuid MainTankGuid=guid(30002),OffTankGuid=guid(30001);};
struct Adapter : Contract {bool ContractResolved=true;};
struct State {ObjectGuid Guid=guid(30001); Kernel DecisionKernel;
 uint64 LastRaidTankSwapMs=0,LastRaidTankSwapWipeGeneration=0;
 uint32 LastRaidTankSwapTriggerSpellId=0,RaidAttempts=0;
 std::string LastRaidTankSwapTriggerKey,LastDecisionHandler; bool WasInCombat=true;
};
struct PartyState {uint32 ValidationRouteManifestIndex=0; uint64 ValidationRouteGeneration=4;
 std::vector<Contract> ValidationRouteManifest{Contract{}}; std::vector<State> Bots=std::vector<State>(2);};
struct CohortState {std::shared_ptr<Board> EncounterSnapshot=std::make_shared<Board>();
 uint64 EncounterSnapshotRevision=1,AttemptId=1;
 struct {std::string ValidationRouteNodeId="bwd.magmaw.encounter",ValidationRouteKind="boss";} Config;
 struct {uint64 WipeGeneration=0;std::string EncounterPhase;} Raid; PartyState Party;
};
enum class BotCombatActionCategory {Taunt};
struct BotActionCandidate {BotCombatActionCategory Category=BotCombatActionCategory::Taunt;std::string RejectReason;uint32 SpellId=62124;};
struct BotClassSpecActionProfile {};
struct BotClassSpecActionProfileStore {
 static BotClassSpecActionProfile Build(Player*,char const*){return {};}
 static std::vector<BotActionCandidate> BuildCandidates(Player*,Unit*,BotClassSpecActionProfile const&){return {{}};}
};
struct BotWorldPopulationMgr {
 using WorldBotState=State; using RaidRoleAssignment=Assignment; using RaidPositioningAnchors=int;
 using RaidMechanicAdapter=Adapter;using RaidGearTargetPlan=int;using HeroicRaidProgression=int;
 struct BossMechanicActionResult {Unit* Target=nullptr; ::Features Features; std::string Action;
 uint32 SpellId=0;bool Failure=false,Rare=false;};
 struct BotUpdateContext {Player* Bot;::State& State;bool AdaptiveMagmawOwnsNode=true;
 uint64 DecisionNowMs=100;int Power=0,Stage=0;struct{int Activity=0;}ChosenActivity;
 std::string Action,Situation;};
 CohortState C; Assignment Assigned; const char* Role="tank";
 auto& Cohort(){return C;} auto& Party(){return C.Party;}
 char const* GetDungeonRole(Player*){return Role;}
 Assignment BuildRaidRoleAssignment(Player*){return Assigned;}
 Features BuildBossMechanicFeatures(Player*,Unit*){return {};}
 Adapter BuildRaidMechanicAdapter(Player*,Unit*,Assignment const&,Features const&){return {};}
 int BuildRaidPositioningAnchors(Player*,Unit*,Assignment const&,Features const&){return 0;}
 int BuildRaidGearTargetPlan(Player*,int,int){return 0;}
 int BuildHeroicRaidProgression(State&,Player*,int,int){return 0;}
 std::string BuildRawJson(Player*,Unit*){return "";}
 std::string BuildSemanticJson(Player*,Unit*,char const*,int*,int,int){return "";}
 template<class... T> void RecordRaidTelemetry(T&&...){}
 bool TryCastCombatSpell(Player*,Unit*,uint32,bool=true) const;
 bool TryBossTankSwap(State&,Player*,char const*,BossMechanicActionResult&,Assignment const&,
 Adapter const&,std::function<void(uint32)> const&,bool=true);
 void SubmitAdaptiveTankSwapCandidate(BotUpdateContext&);
};
''' + facing + '\n' + cast + '\n' + swap + '\n' + submit + r'''
int main(){
 BotWorldPopulationMgr m; Player pal(30001),dk(30002);Unit boss(39);boss.Entry=41570;
 boss.Victim=&dk;dk.Debuffed=true;NativeBoss=&boss;
 auto& state=m.C.Party.Bots[0];m.C.Party.Bots[1].Guid=dk.GetGUID();
 BotWorldPopulationMgr::BotUpdateContext context{&pal,state};
 auto tick=[&](bool movement=true){
  state.DecisionKernel.Begin(100);m.SubmitAdaptiveTankSwapCandidate(context);
  if(movement){Candidate c;c.Key="mangle_midpoint_stage";c.ActionPriority=Priority::Survival;
   c.RequiredResources=Uses(Resource::Movement);c.Attempt=[&](){pal.Moving=true;pal.Path.Final=false;
    return Outcome::Submitted("native_move_submitted");};state.DecisionKernel.Submit(std::move(c));}
 };
 tick();state.DecisionKernel.Resolve();assert(pal.Casts==1);assert(pal.Path.Id==7 && pal.Moving);
 assert(state.LastRaidTankSwapTriggerKey=="debuff:78199:30002");
 tick();state.DecisionKernel.Resolve();assert(pal.Casts==1); // duplicate success
 state.LastRaidTankSwapTriggerKey.clear();dk.Debuffed=false;
 tick();state.DecisionKernel.Resolve();assert(pal.Casts==1); // absent trigger
 dk.Debuffed=true;m.Assigned.OffTankGuid=guid(30003);
 tick();state.DecisionKernel.Resolve();assert(pal.Casts==1); // wrong assigned owner
 m.Assigned.OffTankGuid=pal.GetGUID();boss.Victim=&pal;pal.Debuffed=true;
 tick();state.DecisionKernel.Resolve();assert(pal.Casts==1); // current victim cannot taunt itself
 boss.Victim=&dk;pal.NativeOk=false;
 tick();state.DecisionKernel.Resolve();assert(pal.Casts==2);assert(state.LastRaidTankSwapTriggerKey.empty());
 assert(pal.Path.Id==7 && pal.Moving);pal.NativeOk=true;
 tick();++m.C.AttemptId;state.DecisionKernel.Resolve();assert(pal.Casts==2);
 tick();++m.C.Raid.WipeGeneration;state.DecisionKernel.Resolve();assert(pal.Casts==2);
 tick();++m.C.Party.ValidationRouteGeneration;state.DecisionKernel.Resolve();assert(pal.Casts==2);
 tick();++m.C.EncounterSnapshotRevision;state.DecisionKernel.Resolve();assert(pal.Casts==2);
 tick();++m.C.Party.ValidationRouteManifest[0].TankSwapAuraStacks;
 state.DecisionKernel.Resolve();assert(pal.Casts==2);
 --m.C.Party.ValidationRouteManifest[0].TankSwapAuraStacks;
 tick();state.DecisionKernel.Resolve();assert(pal.Casts==3);assert(pal.Path.Id==7);
 // Default legacy call preserves its old forced-facing behavior; the exact
 // native SetFacingToObject body above is executed, not a preservation stub.
 m.TryCastCombatSpell(&pal,&boss,62124);assert(pal.Path.Id==8 && !pal.Moving);
}
''')
    subprocess.run([
        "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
        "-Wno-missing-field-initializers",
        "-I", str(ROOT / "src/server/game"),
        "-I", str(ROOT / "src/server/game/Entities/Object"),
        "-I", str(ROOT / "src/server/shared"), "-I", str(ROOT / "src/common"),
        str(source), "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True)
