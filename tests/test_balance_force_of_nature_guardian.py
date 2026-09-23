"""DPS-051 exact summon semantics through resolver and executor guard consumers."""
import json
from pathlib import Path
import subprocess

from test_warlock_doomguard_guardian import function

ROOT=Path(__file__).resolve().parents[1]
BOT=ROOT/'src/server/game/Bots'


def test_native_summon_semantics_reaches_both_callers(tmp_path):
    fixture=json.loads((ROOT/'tests/fixtures/balance_force_of_nature_native.json').read_text())
    effects=sorted(fixture['native']['SpellEffect']['rows'],key=lambda r:r[25])
    assert [(r[1],r[5],r[12],r[13],r[22],r[25]) for r in effects]==[(28,3,1964,3097,8,0),(6,0,0,0,16,1)]
    assert fixture['native']['SummonProperties']['rows']==[[3097,2,0,1,0,18432]]
    assert fixture['native']['Spell']['rows'][0][0]==33831
    assert fixture['native']['SpellEffect']['sha256']=='e3d9a470bbcb5cea4e3f2947911a908b816cc60e6ffeb9f70b4cfb123bad6252'
    shared=(BOT/'BotWorldPopulationMgrSpellSemantics.cpp').read_text()
    helper=function(shared,'bool SpellHasHostileMultiTargetSemantics(')
    melee_helper=function(shared,'bool SpellHasHostileMeleeChainSemantics(')
    resolver=(BOT/'BotWorldPopulationMgrCombatResolver.cpp').read_text()
    executor=(BOT/'BotActionExecutor.cpp').read_text()
    for source in (resolver,executor):
        assert 'bool SpellHasHostileMultiTargetSemantics(' not in source
        assert 'using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;' in source
        assert '#include "Bots/BotWorldPopulationMgrSpellSemantics.h"' in source
    start=resolver.index('        if (HasNearbyProtectedEncounterTarget(bot, target, candidateSpellInfo)\n')
    gates=resolver[start:resolver.index('        if (bot->HasUnitState',start)]
    start=executor.index('    if (HasNearbyProtectedEncounterTarget(bot, target, spellInfo)\n        && SpellHasHostileMultiTargetSemantics(spellInfo))')
    spell_gate=executor[start:executor.index('    BotActionResult check =',start)]
    start=executor.index('    if ((action.SuppressAreaDamage\n')
    preview_gate=executor[start:executor.index('    if (!target',start)]
    start=executor.index('    if ((action.SuppressAreaDamage\n', start + 1)
    resolved_gate=executor[start:executor.index('    BotActionResult check =',start)]
    setup='\n'.join(f'force.Effects[{r[25]}]={{{r[1]},{r[8]},{r[21]},true,false}};' for r in effects)
    code=r'''
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"
#include "Bots/BotRaidAreaAuthority.h"
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include <cassert>
#include <map>
#include <string>
constexpr unsigned MAX_SPELL_EFFECTS=3,SPELL_EFFECT_PERSISTENT_AREA_AURA=27,SPELL_DAMAGE_CLASS_MELEE=2;
struct SpellEffectInfo {unsigned Effect=0,ChainTarget=0,TriggerSpell=0;bool area=false,areaAura=false;
 bool IsEffect()const{return Effect!=0;}bool IsEffect(unsigned id)const{return Effect==id;}
 bool IsTargetingArea()const{return area;}bool IsAreaAuraEffect()const{return areaAura;}};
struct SpellInfo {unsigned Id=0,DmgClass=0;SpellEffectInfo Effects[3];bool positive=false;
 bool IsPositiveEffect(unsigned)const{return positive;}};
struct Manager {std::map<unsigned,SpellInfo const*> spells;SpellInfo const* GetSpellInfo(unsigned id)const{auto i=spells.find(id);return i==spells.end()?nullptr:i->second;}}manager;
auto* sSpellMgr=&manager;
namespace BotWorldPopulationMgrSpellSemantics {
''' + helper + '\n' + melee_helper + r'''
}
using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMultiTargetSemantics;
using BotWorldPopulationMgrSpellSemantics::SpellHasHostileMeleeChainSemantics;
bool nearby=false;
bool HasNearbyProtectedEncounterTarget(void*,void*,SpellInfo const* =nullptr){return nearby;}
std::string Resolve(SpellInfo const* candidateSpellInfo,bool forbidArea){
 void* bot=nullptr;void* target=nullptr;struct {std::string RejectReason;}candidate;
 bool magmawMushroomAction=false,scopedAreaAction=false;
 for(int once=0;once<1;++once){
''' + gates + r'''
 }return candidate.RejectReason;
}
enum class BotActionResult {NoAction,Ok};
BotActionResult ExecuteSpell(SpellInfo const* spellInfo){void* bot=nullptr;void* target=nullptr;
''' + spell_gate + r'''
 return BotActionResult::Ok;
}
BotActionResult ExecuteHostile(SpellInfo const* before,SpellInfo const* after,bool suppressed){
 void* bot=nullptr;void* target=nullptr;struct {bool SuppressAreaDamage=false;bool AllowMagmawBalanceMushroomSplash=false;bool AllowScopedEncounterAreaDamage=false;}action{suppressed};
 struct {SpellInfo const* Effective;}preview{before},resolved{after};
''' + preview_gate + resolved_gate + r'''
 return BotActionResult::Ok;
}
int main(){
 SpellInfo force;force.Id=33831;
''' + setup + r'''
 SpellInfo starfall;starfall.Id=48505;
 SpellInfo felstorm;felstorm.Id=89751;
 SpellInfo damage;damage.Id=100;damage.Effects[0]={2,0,0,true,false};
 SpellInfo chain;chain.Id=101;chain.Effects[0]={2,2,0,false,false};
 SpellInfo persistent;persistent.Id=102;persistent.Effects[0]={27,0,0,false,false};
 SpellInfo aura;aura.Id=103;aura.Effects[0]={6,0,0,false,true};
 SpellInfo single;single.Id=104;single.Effects[0]={2,0,0,false,false};
 SpellInfo wrapper;wrapper.Id=105;wrapper.Effects[0]={3,0,33831,false,false};
 SpellInfo triggered;triggered.Id=106;triggered.Effects[0]={3,0,100,false,false};
 manager.spells={{33831,&force},{100,&damage},{105,&wrapper}};
 assert(!SpellHasHostileMultiTargetSemantics(&force));
 assert(SpellHasHostileMultiTargetSemantics(&force,1)); // another root's preexisting chain semantics unchanged
 assert(!SpellHasHostileMultiTargetSemantics(nullptr));
 for(bool near:{false,true})for(bool forbidden:{false,true}){
  nearby=near;
  assert(Resolve(&force,forbidden).empty());
  assert(ExecuteSpell(&force)==BotActionResult::Ok);
  assert(ExecuteHostile(&force,&force,forbidden)==BotActionResult::Ok);
  for(auto spell:{&starfall,&felstorm,&damage,&chain,&persistent,&aura,&wrapper,&triggered}){
   assert(SpellHasHostileMultiTargetSemantics(spell));
   assert(Resolve(spell,forbidden).empty()==!(near||forbidden));
   assert((ExecuteSpell(spell)==BotActionResult::Ok)==!near);
   assert((ExecuteHostile(&force,spell,forbidden)==BotActionResult::Ok)==!(near||forbidden));
   assert((ExecuteHostile(spell,&force,forbidden)==BotActionResult::Ok)==!(near||forbidden));
  }
  assert(Resolve(&single,forbidden).empty());
 }
 // Guardian authority and reservation are independent, unchanged constraints.
 using namespace BotRaidAreaAuthority;uint64 owner=30001;
 SetCurrentEncounterRestrictions(owner,{41806,42321},{208});
 SetProtectedEncounterEntries(owner,{999});
 assert(IsProtectedEncounterTarget(owner,41806,0,209));
 assert(!IsProtectedEncounterTarget(owner,41806,0,208));
 assert(IsProtectedEncounterTarget(owner,999,0,208));
 assert(!IsProtectedEncounterTarget(owner,41570,0,39)&&!IsProtectedEncounterTarget(owner,42347,0,76));
 Clear(owner);
 using namespace BotRaidCooldownReservation;
 CandidateContext treants{BotCombatActionCategory::OffensiveCooldown,"force_of_nature,treants"};
 RouteContext route;route.ValidationRouteEnabled=true;route.RaidInstance=true;route.RouteKind="trash";route.NodeKind="trash_cluster";
 assert(std::string(ReservationReason(route,treants))=="raid_offensive_guardian_reserved");
 route.RouteKind=route.NodeKind="boss";route.EncounterInProgress=true;route.EncounterPhase="combat";
 assert(ReservationReason(route,treants)==nullptr);
}
'''
    source=tmp_path/'force.cpp';source.write_text(code);binary=tmp_path/'force'
    result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'src/server/game'),'-I',str(ROOT/'src/common'),str(source),'-o',str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    subprocess.run([str(binary)],check=True)
