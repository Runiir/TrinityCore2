import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/server/scripts/Spells/spell_item_vial_of_shadows.cpp'
FIXTURE=ROOT/'tests/fixtures/hunter_vial_of_shadows_3e_5c.json'


def body(source, signature):
    start=source.index(signature); brace=source.index('{',start); depth=0
    for end in range(brace,len(source)):
        depth += (source[end]=='{')-(source[end]=='}')
        if depth==0:
            return source[start:end+1]
    raise AssertionError(signature)


def test_actual_proc_handler_snapshots_attack_type_and_preserves_native_roll_and_provenance(tmp_path):
    contract=json.loads(FIXTURE.read_text()); source=SOURCE.read_text()
    helper=body(source,'int32 LightningStrikeBasePoints(')
    handler=body(source,'void HandleProc(')
    calc=(ROOT/'src/server/game/Spells/SpellInfo.cpp').read_text()
    roll=body(calc,'else if (DieSides)')[5:]  # Actual native random die branch, as standalone if.
    code=tmp_path/'vial.cpp'
    code.write_text('''
#include <cassert>
using int32=int; using uint32=unsigned;
enum WeaponAttackType {BASE_ATTACK,OFF_ATTACK,RANGED_ATTACK};
constexpr int SPELL_AURA_RANGED_ATTACK_POWER_ATTACKER_BONUS=1,SPELL_AURA_MELEE_ATTACK_POWER_ATTACKER_BONUS=2;
constexpr int EFFECT_0=0,TRIGGERED_FULL_MASK=255,TRIGGERED_IGNORE_POWER_COST=1,TRIGGERED_IGNORE_REAGENT_COST=2;
constexpr unsigned HeroicLightningStrike=109724;
struct AuraEffect{}; struct Spell{};
struct CastSpellExtraArgs {AuraEffect const* aura; Spell const* spell=nullptr;int flags=0,bp=0;
 CastSpellExtraArgs(AuraEffect const* a):aura(a){}
 CastSpellExtraArgs& SetTriggeringSpell(Spell const* s){spell=s;return *this;}
 CastSpellExtraArgs& SetTriggerFlags(int f){flags=f;return *this;}
 CastSpellExtraArgs& AddSpellBP0(int b){bp=b;return *this;}};
struct Unit {float melee=10000,ranged=20000;int meleeBonus=100,rangedBonus=200,calls=0;
 int usedAP=-1,usedBonus=-1,lastBP=0,lastFlags=0;unsigned lastSpell=0;
 Unit* lastTarget=nullptr;AuraEffect const* lastAura=nullptr;Spell const* lastTrigger=nullptr;
 float GetTotalAttackPowerValue(WeaponAttackType type){usedAP=type;return type==RANGED_ATTACK?ranged:melee;}
 int GetTotalAuraModifier(int type){usedBonus=type;return type==1?rangedBonus:meleeBonus;}
 void CastSpell(Unit* target,unsigned spell,CastSpellExtraArgs const& args){++calls;lastTarget=target;lastSpell=spell;lastBP=args.bp;lastFlags=args.flags;lastAura=args.aura;lastTrigger=args.spell;}
};
struct DamageInfo {WeaponAttackType attack;WeaponAttackType GetAttackType(){return attack;}};
struct ProcEventInfo {DamageInfo* damage;Unit* target;Spell* spell;
 DamageInfo* GetDamageInfo(){return damage;}Unit* GetProcTarget(){return target;}Spell* GetProcSpell(){return spell;}};
struct SpellInfo {struct Effect {int BasePoints;};Effect Effects[1];};
struct SpellMgr {SpellInfo info{{{''' + str(contract['native']['base_points']) + '''}}};
 SpellInfo const* GetSpellInfo(unsigned id){assert(id==109724);return &info;}} mgr;
SpellMgr* sSpellMgr=&mgr;
''' +helper+'''
struct Harness {Unit* caster;bool prevented=false;Unit* GetTarget(){return caster;}void PreventDefaultAction(){prevented=true;}
''' +handler+'''
};
int rolled=1;int irand(int minimum,int maximum){assert(rolled>=minimum&&rolled<=maximum);return rolled;}
int nativeRoll(int points,int DieSides){double value=points;
''' +roll+'''
return int(value);}
int main(){
 Unit caster,target;AuraEffect aura;Spell trigger;DamageInfo damage{RANGED_ATTACK};ProcEventInfo event{&damage,&target,&trigger};Harness h{&caster};
 h.HandleProc(&aura,event);
 assert(h.prevented && caster.calls==1 && caster.lastSpell==109724 && caster.lastTarget==&target);
 assert(caster.lastAura==&aura && caster.lastTrigger==&trigger);
 assert(caster.lastFlags==(TRIGGERED_FULL_MASK & ~(TRIGGERED_IGNORE_POWER_COST|TRIGGERED_IGNORE_REAGENT_COST)));
 assert(caster.usedAP==RANGED_ATTACK && target.usedBonus==SPELL_AURA_RANGED_ATTACK_POWER_ATTACKER_BONUS);
 assert(caster.lastBP==4545+int(.339f*(20000+200)));
 int rangedBP=caster.lastBP; rolled=1;assert(nativeRoll(rangedBP,2274)==4546+int(.339f*20200));
 rolled=2274;assert(nativeRoll(rangedBP,2274)==6819+int(.339f*20200));
 assert(nativeRoll(4545,2274)==6819 && rangedBP>4545); // Historical DBC-only counterexample.
 caster.ranged=30000;h.HandleProc(&aura,event);assert(caster.lastBP==4545+int(.339f*30200));
 for(auto type:{BASE_ATTACK,OFF_ATTACK}){
  damage.attack=type;h.HandleProc(&aura,event);
  assert(caster.usedAP==BASE_ATTACK && target.usedBonus==SPELL_AURA_MELEE_ATTACK_POWER_ATTACKER_BONUS);
  assert(caster.lastBP==4545+int(.339f*10100));
 }
 event.damage=nullptr;h.prevented=false;int calls=caster.calls;h.HandleProc(&aura,event);
 assert(!h.prevented && caster.calls==calls);
}
'''.replace('for(auto type:{BASE_ATTACK,OFF_ATTACK})','for(auto type : {BASE_ATTACK,OFF_ATTACK})'))
    # initializer_list supports the two native attack-type cases.
    code.write_text('#include <initializer_list>\n'+code.read_text())
    binary=tmp_path/'vial'
    subprocess.run(['c++','-std=c++17',str(code),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)


def test_heroic_only_script_binding_and_registration_are_exact():
    source=SOURCE.read_text()
    assert 'OnEffectProc.Register(&vial_AuraScript::HandleProc, EFFECT_0, SPELL_AURA_PROC_TRIGGER_SPELL)' in source
    assert 'spellInfo->Id == HeroicVialAura' in source
    assert 'TriggerSpell == HeroicLightningStrike' in source
    loader=(SOURCE.parent/'spell_script_loader.cpp').read_text()
    assert loader.count('void AddSC_item_vial_of_shadows();')==1
    assert loader.count('    AddSC_item_vial_of_shadows();')==1
    for relative in ('sql/custom/world/2026_09_09_02_vial_of_shadows_ap.sql',
                     'sql/custom/rollback/world/2026_09_09_02_vial_of_shadows_ap_rollback.sql'):
        sql=(ROOT/relative).read_text()
        assert "`spell_id` = 109725 AND `ScriptName` = 'spell_item_vial_of_shadows'" in sql
        assert '109724' not in sql and '77999' not in sql
    assert len(source.splitlines())<1000
