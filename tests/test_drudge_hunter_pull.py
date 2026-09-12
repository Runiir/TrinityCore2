"""Exercise production pull assignment and native Misdirection admission."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeEntrancePull.cpp'


def test_native_drudge_hunter_assignment_and_misdirection(tmp_path):
    source = SOURCE.read_text()
    functions = source[source.index('uint32 DrudgeLaneContext::EntrancePullOwnerSlot()'):source.index('DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunEntrancePullActions()')]
    cpp = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
#include <vector>
using uint32 = std::uint32_t;
constexpr int CLASS_HUNTER = 3;
struct Guid { uint32 n; uint32 GetCounter() const { return n; } };
struct ThreatManager {
    uint32 redirectTarget=0;
    uint32 GetRegisteredRedirectThreatPercent(uint32 id,uint32 target) const {
        assert(id==34477); return target==redirectTarget ? 100 : 0;
    }
};
struct Player {
    bool world=true, alive=true, spell=true, aura=false;
    int cls=9, map=669, group=1; uint32 guid=0; ThreatManager threat;
    uint32 GetGUID() const { return guid; }
    ThreatManager& GetThreatManager() { return threat; }
    bool IsInWorld() const { return world; }
    bool IsAlive() const { return alive; }
    int GetMap() const { return map; }
    int GetGroup() const { return group; }
    int getClass() const { return cls; }
    bool HasSpell(uint32 id) const { assert(id==34477); return spell; }
    bool HasAura(uint32 id) const { assert(id==34477); return aura; }
};
struct WorldBotState { struct Guid Guid; Player* player; };
struct Roster { bool Active=true, LeaseOwned=true; uint32 SlotIndex; std::string Role="dps"; int ClassId=9; };
struct Raid { bool RosterComplete=true; std::map<uint32,Roster> RosterByGuid; };
struct Config { uint32 TargetPopulation=4; std::vector<uint32> ValidationRouteSplitSeedRosterSlots{8,6}; std::vector<uint32> ValidationRouteSplitLaneTankSlots{1,2}; };
struct Cohort { struct Raid Raid; struct Config Config; };
struct Party { std::vector<WorldBotState> Bots; };
struct Manager {
    struct Cohort cohort; struct Party party;
    int requests=0; bool castSuccess=true; Player* submittedTarget=nullptr;
    struct Cohort& Cohort() { return cohort; }
    struct Party& Party() { return party; }
    Player* GetLoadedBot(WorldBotState const& s) { return s.player; }
    bool TryCastFriendlySpell(Player*,Player* target,uint32 id,std::string*) {
        assert(id==34477); ++requests; submittedTarget=target; return castSuccess;
    }
};
struct DrudgeLaneContext {
    struct Manager& Manager; Player* Bot; std::vector<int> Sources{1,2};
    bool held=false; std::string reason;
    uint32 EntrancePullOwnerSlot() const;
    bool PrepareEntranceMisdirection();
    void HoldOffense() { held=true; }
    void Record(int,char const* r,float=0,uint32=0) { reason=r; }
};
'''+functions+r'''
int main() {
    Manager m; Player warlock,hunter,tank,otherTank; hunter.cls=CLASS_HUNTER; tank.guid=1; otherTank.guid=2;
    m.party.Bots={{{8},&warlock},{{9},&hunter},{{1},&tank},{{2},&otherTank}};
    m.cohort.Raid.RosterByGuid={{8,{true,true,7,"dps"}},{9,{true,true,8,"dps",CLASS_HUNTER}},
        {1,{true,true,0,"tank"}},{2,{true,true,1,"tank"}}};
    DrudgeLaneContext c{m,&warlock};
    assert(c.EntrancePullOwnerSlot()==9); // Real canary: Warlock seed is not opener.
    hunter.alive=false; assert(c.EntrancePullOwnerSlot()==9); hunter.alive=true;
    hunter.map=0; assert(c.EntrancePullOwnerSlot()==9); hunter.map=669;
    m.cohort.Raid.RosterByGuid[9].LeaseOwned=false;
    assert(c.EntrancePullOwnerSlot()==9); m.cohort.Raid.RosterByGuid[9].LeaseOwned=true;
    m.cohort.Raid.RosterComplete=false; assert(c.EntrancePullOwnerSlot()==0);
    m.cohort.Raid.RosterComplete=true;
    Player secondHunter=hunter;
    m.party.Bots.push_back({{6},&secondHunter});
    m.cohort.Raid.RosterByGuid[6]={true,true,5,"dps",CLASS_HUNTER};
    m.cohort.Config.TargetPopulation=5;
    assert(c.EntrancePullOwnerSlot()==6); // Stable roster order, not iteration order.
    c.Bot=&hunter;
    assert(!c.PrepareEntranceMisdirection());
    assert(m.requests==1 && m.submittedTarget==&tank);
    assert(c.reason=="drudge_entrance_misdirection_submitted");
    // Submission alone must not open offense. Wait for the native aura.
    m.castSuccess=false;
    assert(!c.PrepareEntranceMisdirection());
    assert(c.reason=="drudge_entrance_misdirection_wait");
    hunter.aura=true; hunter.threat.redirectTarget=2;
    assert(!c.PrepareEntranceMisdirection());
    assert(c.reason=="drudge_entrance_misdirection_wrong_tank");
    hunter.threat.redirectTarget=1;
    assert(c.PrepareEntranceMisdirection()); assert(m.requests==2);
    tank.alive=false; assert(!c.PrepareEntranceMisdirection()); assert(c.held);
    tank.alive=true; tank.group=2; assert(!c.PrepareEntranceMisdirection());
    tank.group=1; hunter.spell=false; assert(!c.PrepareEntranceMisdirection());
    c.Bot=&warlock; assert(c.PrepareEntranceMisdirection()); // No-hunter roster fallback.
}
'''
    path=tmp_path/'pull.cpp';path.write_text(cpp)
    binary=tmp_path/'pull'
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra',str(path),'-o',str(binary)],check=True,capture_output=True,text=True)
    subprocess.run([str(binary)],check=True)


def test_pull_caller_waits_before_resolving_hostile_action():
    source=SOURCE.read_text()
    caller=source[source.index('DrudgeLaneContext::PhaseResult DrudgeLaneContext::RunEntrancePullActions()'):]
    assert caller.index('if (pullStarted)') < caller.index('EntrancePullOwnerSlot()')
    assert caller.index('if (OneBasedSlot != pullOwnerSlot)') < caller.index('PrepareEntranceMisdirection()')
    assert caller.index('PrepareEntranceMisdirection()') < caller.index('ResolveProfileCombatAction(')
    assert 'if (!PrepareEntranceMisdirection())\n        return PhaseResult::Handled;' in caller
    assert 'DeclaredAnchorFor(\n        config.ValidationRouteSplitSeedRosterSlots.front())' in caller


def test_native_redirect_reader_keeps_spell_and_target_identity(tmp_path):
    source=(ROOT/'src/server/game/Combat/ThreatManager.cpp').read_text()
    body=source[source.index('uint32 ThreatManager::GetRegisteredRedirectThreatPercent('):source.index('void ThreatManager::UnregisterRedirectThreat(uint32 spellId)')]
    cpp=r'''
#include <cassert>
#include <cstdint>
#include <unordered_map>
using uint32=std::uint32_t;
using ObjectGuid=std::uint64_t;
struct ThreatManager {
 std::unordered_map<uint32,std::unordered_map<ObjectGuid,uint32>> _redirectRegistry;
 uint32 GetRegisteredRedirectThreatPercent(uint32,ObjectGuid const&) const;
};
'''+body+r'''
int main() {
 ThreatManager t;
 assert(t.GetRegisteredRedirectThreatPercent(34477,1)==0);
 assert(t._redirectRegistry.empty());
 t._redirectRegistry[34477][2]=100;
 assert(t.GetRegisteredRedirectThreatPercent(34477,1)==0);
 assert(t.GetRegisteredRedirectThreatPercent(34477,2)==100);
 assert(t.GetRegisteredRedirectThreatPercent(57934,2)==0);
 t._redirectRegistry[34477][1]=50;
 assert(t.GetRegisteredRedirectThreatPercent(34477,1)==50);
 auto const before=t._redirectRegistry;
 assert(t.GetRegisteredRedirectThreatPercent(34477,99)==0);
 assert(t._redirectRegistry==before);
}
'''
    path=tmp_path/'redirect.cpp';path.write_text(cpp)
    binary=tmp_path/'redirect'
    subprocess.run(['g++','-std=c++17',str(path),'-o',str(binary)],check=True,capture_output=True,text=True)
    subprocess.run([str(binary)],check=True)


def test_patrol_also_checks_native_redirect_target_before_hostile_pull():
    source=(ROOT/'src/server/game/Bots/BotWorldPopulationMgrValidationPatrolPull.cpp').read_text()
    gate=source.index('GetRegisteredRedirectThreatPercent(')
    assert 'HUNTER_MISDIRECTION_SPELL_ID, tank->GetGUID()) != 100' in source[gate:gate+200]
    assert gate < source.index('ResolveProfileCombatAction(',gate)
    assert 'validation_route_patrol_misdirection_wrong_tank' in source[gate:gate+300]


def test_patrol_primes_friendly_redirect_before_narrow_hostile_window():
    source=(ROOT/'src/server/game/Bots/BotWorldPopulationMgrValidationPatrolPull.cpp').read_text()
    staged=source.index('if (!rosterStaged)')
    owner=source.index('if (!pullOwner)',staged)
    preparation=source.index('if (hunterPullOwner\n                && !bot->HasAura',owner)
    window=source.index('if (!atWait)',preparation)
    chase=source.index('if (!sourcePathKeepsFutureEncountersSafe())',window)
    hostile=source.index('ResolveProfileCombatAction(',chase)
    assert staged < owner < preparation < window < chase < hostile
