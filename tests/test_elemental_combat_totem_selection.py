"""Execute the production selector with stubbed native cast/readiness dependencies.

No aura application, spell effect or live haste is simulated by this fixture.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/server/game/Bots/BotWorldPopulationMgrCombatExecution.cpp'


def test_actual_combat_totem_selector(tmp_path):
    source = SOURCE.read_text()
    start = source.index('bool BotWorldPopulationMgr::TryEnsureCombatTotems(')
    end = source.index('\n}', start) + 2
    function = source[start:end]
    fixture = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>
using uint8=uint8_t; using uint32=uint32_t; using uint64=uint64_t;
constexpr int CLASS_SHAMAN=7, UNIT_STATE_CASTING=1, UNIT_CREATED_BY_SPELL=0, SPELL_CAST_OK=0;
constexpr int SUMMON_SLOT_TOTEM_FIRE=0, SUMMON_SLOT_TOTEM_EARTH=1, SUMMON_SLOT_TOTEM_WATER=2, SUMMON_SLOT_TOTEM_AIR=3;
uint64 NowMs(){return 1000;}
struct Unit { bool alive=true; bool IsAlive(){return alive;} };
struct Totem:Unit {uint32 spell=0; uint32 GetUInt32Value(int){return spell;} };
struct Creature {Totem totem; Totem* ToTotem(){return &totem;} };
struct Map {std::array<Creature,4> creatures; Creature* GetCreature(uint64 id){return &creatures[id-1];}};
struct SpellInfo {};
struct SpellMgr {SpellInfo info; bool missing=false; SpellInfo const* GetSpellInfo(uint32){return missing?nullptr:&info;}} manager;
auto sSpellMgr=&manager;
struct SpellHistory {bool gcd=false,ready=true; bool HasGlobalCooldown(SpellInfo const*){return gcd;} bool IsReady(SpellInfo const*){return ready;}};
struct Player:Unit {
 int cls=7; bool combat=true,moving=false,casting=false; uint32 tree=261; uint8 active=1;
 std::set<uint32> spells{8075,3599,5394,8512,3738,8190,8143,5675}; std::vector<uint32> casts;
 std::array<uint64,4> m_SummonSlot{1,2,3,0}; Map map; SpellHistory history; int result=0;
 Player(){map.creatures[0].totem.spell=3599;map.creatures[1].totem.spell=8143;map.creatures[2].totem.spell=5675;}
 int getClass(){return cls;} bool IsInCombat(){return combat;} bool isMoving(){return moving;}
 uint8 GetActiveSpec(){return active;} uint32 GetPrimaryTalentTree(uint8 spec){assert(spec==active);return tree;}
 bool HasSpell(uint32 id){return spells.count(id);} Map* GetMap(){return &map;}
 bool HasUnitState(int){return casting;} SpellHistory* GetSpellHistory(){return &history;}
 uint64 GetGUID(){return 123;} int CastSpell(Player*,uint32 spell,bool triggered){assert(!triggered);casts.push_back(spell);return result;}
};
struct WorldBotState {std::map<std::string,uint64> ReadinessRetryUntilMs;};
struct ResolvedCombatAction {bool Valid; std::string Type,DebugName; uint32 SpellId;uint64 TargetGuid;};
enum class BotActionResult {Ok,CastFailed};
struct BotWorldPopulationMgr {
 bool TryEnsureCombatTotems(WorldBotState&,Player*,Unit*,uint32) const;
 template<class... T> void ObserveBotCandidateFailure(T&&...)const{}
 template<class... T> void RecordCombatAttempt(T&&...)const{}
 template<class... T> void TryResolveBotBlocker(T&&...)const{}
};
'''+function+r'''
int main(){
 BotWorldPopulationMgr mgr; Unit target;
 for(uint32 tree:{261u,263u,262u}){Player p;WorldBotState s;p.tree=tree;assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts==std::vector<uint32>{tree==261?3738u:8512u});}
 for(auto [slot,oldSpell,expected]:std::array<std::array<uint32,3>,2>{{{1,8075,8143},{2,5394,5675}}}){
  Player p;WorldBotState s;p.map.creatures[slot].totem.spell=oldSpell;assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts==std::vector<uint32>{expected});
 }
 for(uint32 missing:{8143u,5675u,3738u}){Player p;WorldBotState s;p.spells.erase(missing);assert(!mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts.empty());assert(s.ReadinessRetryUntilMs.count("totem_spell_missing:"+std::to_string(missing)));}
 {Player p;WorldBotState s;p.spells.erase(8075);p.spells.erase(5394);p.spells.erase(8512);assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts[0]==3738);}
 for(auto [slot,expected]:std::array<std::array<uint32,2>,2>{{{1,8075},{2,5394}}}){Player p;WorldBotState s;p.tree=263;p.m_SummonSlot[slot]=0;p.spells.erase(8143);p.spells.erase(5675);assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts[0]==expected);}
 // An existing wrong air totem must not mask Elemental's required setup.
 {Player p;WorldBotState s;p.m_SummonSlot[3]=4;p.map.creatures[3].totem.spell=8512;assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts==std::vector<uint32>{3738});}
 {Player p;WorldBotState s;p.m_SummonSlot[3]=4;p.map.creatures[3].totem.spell=3738;assert(!mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts.empty());}
 {Player p;WorldBotState s;p.tree=263;p.m_SummonSlot[3]=4;p.map.creatures[3].totem.spell=3738;assert(!mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts.empty());}
 // Elemental readiness requires Wrath of Air, not Windfury.
 {Player p;WorldBotState s;p.spells.erase(8512);assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts[0]==3738);}
 {Player p;WorldBotState s;p.spells.erase(3738);assert(!mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts.empty());assert(s.ReadinessRetryUntilMs.count("totem_spell_missing:3738"));}
 {Player p;WorldBotState s;p.tree=263;p.spells.erase(3738);assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts[0]==8512);}
 for(int gate=0;gate<8;gate++){Player p;WorldBotState s;
  if(gate==0)p.cls=1;if(gate==1)p.moving=true;if(gate==2)p.combat=false;if(gate==3)p.casting=true;
  if(gate==4)p.history.gcd=true;if(gate==5)p.history.ready=false;if(gate==6)manager.missing=true;
  if(gate==7)s.ReadinessRetryUntilMs["totem:3738"]=2000;
  assert(!mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts.empty());manager.missing=false;
 }
 {Player p;WorldBotState s;p.map.creatures[0].totem.spell=2894;assert(mgr.TryEnsureCombatTotems(s,&p,&target,3));assert(p.casts[0]==3738);}
 {Player p;WorldBotState s;assert(mgr.TryEnsureCombatTotems(s,&p,&target,3));assert(p.casts[0]==8190);}
 {Player p;WorldBotState s;p.m_SummonSlot[0]=0;assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts[0]==3599);}
 {Player p;WorldBotState s;p.m_SummonSlot[2]=0;assert(mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(p.casts[0]==5675);}
 {Player p;WorldBotState s;p.result=1;assert(!mgr.TryEnsureCombatTotems(s,&p,&target,1));assert(s.ReadinessRetryUntilMs["totem:3738"]==4000);}
}
'''
    cpp = tmp_path/'fixture.cpp'
    cpp.write_text(fixture)
    binary=tmp_path/'fixture'
    subprocess.run(['c++','-std=c++17','-O0',str(cpp),'-o',str(binary)],check=True,capture_output=True,text=True)
    subprocess.run([str(binary)],check=True,capture_output=True,text=True)
