"""Compile the production validated-target/independent ranged-uptime slice."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / 'src/server/game/Bots'


def test_hunter_autorepeat_rebinds_only_valid_changed_target(tmp_path):
    source = (BOTS / 'BotActionExecutor.cpp').read_text()
    start = source.index('    if (!target || !target->IsAlive()', source.index('BotActionResult BotActionExecutor::ExecuteCombat'))
    end = source.index('        // Command the player', start)
    production = source[start:end] + '\n    }\n    return BotActionResult::Ok;\n'
    fixture = r'''
#include <cassert>
#include <string>
constexpr int CURRENT_AUTOREPEAT_SPELL=2, CLASS_HUNTER=3;
enum class BotActionResult {Ok,InvalidTarget};
struct Unit {bool alive=true,valid=true; bool IsAlive(){return alive;}};
struct Targets {Unit* target=nullptr; Unit* GetUnitTarget(){return target;}};
struct Spell {Targets m_targets;};
struct Player:Unit {
 Spell storage; Spell* repeat=nullptr; int starts=0,interrupts=0,faces=0;
 int klass=CLASS_HUNTER;
 bool IsValidAttackTarget(Unit* target){return target && target->valid;}
 int getClass(){return klass;}
 Spell* GetCurrentSpell(int slot){assert(slot==CURRENT_AUTOREPEAT_SPELL);return repeat;}
 void InterruptSpell(int slot,bool delayed){assert(slot==CURRENT_AUTOREPEAT_SPELL && !delayed);++interrupts;repeat=nullptr;}
 void CastSpell(Unit* target,int id,bool triggered){assert(id==75 && !triggered);++starts;storage.m_targets.target=target;repeat=&storage;}
};
struct Action {std::string AutoAttackMode="ranged";bool MeleeAutoAttackExternallyReconciled=false;};
void Face(Player* bot,Unit*){++bot->faces;}
void SubmitMeleeAutoAttack(Player*,Unit*){}
BotActionResult ExecuteUptime(Player* bot,Unit* target,Action const& action) {
''' + production + r'''
}
int main() {
 Unit body,head; Action action; Player hunter;
 assert(ExecuteUptime(&hunter,&body,action)==BotActionResult::Ok);
 assert(hunter.starts==1 && hunter.interrupts==0);
 for(int i=0;i<3;++i) ExecuteUptime(&hunter,&body,action);
 assert(hunter.starts==1 && hunter.interrupts==0);
 ExecuteUptime(&hunter,&head,action);
 assert(hunter.starts==2 && hunter.interrupts==1 && hunter.repeat->m_targets.target==&head);
 for(int i=0;i<3;++i) ExecuteUptime(&hunter,&head,action);
 assert(hunter.starts==2 && hunter.interrupts==1);
 for(int invalid=0;invalid<3;++invalid) {
  Unit bad; bad.alive=invalid!=1;bad.valid=invalid!=2;
  assert(ExecuteUptime(&hunter,invalid==0?nullptr:&bad,action)==BotActionResult::InvalidTarget);
  assert(hunter.starts==2 && hunter.interrupts==1 && hunter.repeat->m_targets.target==&head);
 }
 Player other;other.klass=8; ExecuteUptime(&other,&head,action);
 assert(other.starts==0 && other.interrupts==0);
 Action melee;melee.AutoAttackMode="melee";ExecuteUptime(&hunter,&body,melee);
 assert(hunter.starts==2 && hunter.interrupts==1);
}
'''
    path = tmp_path / 'repeat.cpp'
    path.write_text(fixture)
    binary = tmp_path / 'repeat'
    subprocess.run(['g++', '-std=c++17', str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def test_hunter_autorepeat_native_diagnostic_identity(tmp_path):
    source = (BOTS / 'BotWorldPopulationMgrCombatDiagnostics.cpp').read_text()
    start = source.index('    if (Spell* repeat = bot ?')
    end = source.index('    if (bot)\n', start)
    observation = source[start:end]
    fixture = r'''
#include <cassert>
constexpr int CURRENT_AUTOREPEAT_SPELL=2;
struct Guid {int value=0;};
struct Creature;
struct Unit {Guid guid; Creature* creature=nullptr; Guid GetGUID(){return guid;} Creature* ToCreature(){return creature;}};
struct Creature:Unit {int entry=42347; int GetEntry()const{return entry;}};
struct SpellInfo {int Id=75;};
struct Targets {Unit* target=nullptr; Unit* GetUnitTarget(){return target;}};
struct Spell {SpellInfo info;Targets m_targets;SpellInfo const* GetSpellInfo(){return &info;}};
struct Player {Spell* repeat=nullptr;Spell* GetCurrentSpell(int slot){assert(slot==CURRENT_AUTOREPEAT_SPELL);return repeat;}};
struct Diagnostic {bool RangedAutoActive=false;int RangedAutoSpellId=0;Guid RangedAutoTargetGuid;int RangedAutoTargetEntry=0;};
Diagnostic Observe(Player* bot) {Diagnostic diagnostic;
''' + observation + r'''
return diagnostic;}
int main(){
 Player player;assert(!Observe(nullptr).RangedAutoActive);assert(!Observe(&player).RangedAutoActive);
 Spell spell;player.repeat=&spell;
 auto empty=Observe(&player);assert(empty.RangedAutoActive && empty.RangedAutoSpellId==75 && empty.RangedAutoTargetGuid.value==0);
 Creature head;head.guid.value=76;head.creature=&head;spell.m_targets.target=&head;
 auto active=Observe(&player);assert(active.RangedAutoActive && active.RangedAutoSpellId==75);
 assert(active.RangedAutoTargetGuid.value==76 && active.RangedAutoTargetEntry==42347);
 player.repeat=nullptr;auto cleared=Observe(&player);
 assert(!cleared.RangedAutoActive && cleared.RangedAutoSpellId==0 && cleared.RangedAutoTargetGuid.value==0 && cleared.RangedAutoTargetEntry==0);
}
'''
    path = tmp_path / 'observation.cpp'
    path.write_text(fixture)
    binary = tmp_path / 'observation'
    subprocess.run(['g++', '-std=c++17', str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
