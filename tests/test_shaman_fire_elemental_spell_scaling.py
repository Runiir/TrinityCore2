"""Actual registered damage callback; native coefficient and owner interfaces."""
import re
import sqlite3
import subprocess

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/server/scripts/Pet/pet_shaman.cpp'
SCRIPT = 'spell_sha_fire_elemental_spell_scaling'
FORWARD = ROOT / 'sql/custom/world/2026_09_09_00_shaman_fire_elemental_scaling.sql'
ROLLBACK = ROOT / 'sql/custom/rollback/world/2026_09_09_00_shaman_fire_elemental_scaling_rollback.sql'


@pytest.mark.parametrize("already_applied", [(), (57984,), (12470, 13376), (57984, 12470, 13376)])
def test_bindings_add_only_three_direct_damage_scripts_and_rollback_exactly(already_applied):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE spell_script_names(spell_id INTEGER, ScriptName TEXT, PRIMARY KEY(spell_id,ScriptName))')
    prior = [(57984, 'preexisting_script'), (12470, 'another_script'), (99, SCRIPT)]
    db.executemany('INSERT INTO spell_script_names VALUES(?,?)', prior)
    before = set(db.execute('SELECT * FROM spell_script_names'))
    # Deployment prestate has none of our exact bindings. Partial rows model
    # an interrupted/manual apply owned by this same deployment, not unrelated
    # pre-existing rows that rollback would have authority to remove.
    db.executemany('INSERT INTO spell_script_names VALUES(?,?)',
                   [(spell_id, SCRIPT) for spell_id in already_applied])
    db.executescript(FORWARD.read_text())
    after = set(db.execute('SELECT * FROM spell_script_names'))
    assert after - before == {
        (57984, SCRIPT), (12470, SCRIPT), (13376, SCRIPT)}
    # Ordinary worldserver updater replays the file after a manual apply.
    db.executescript(FORWARD.read_text())
    assert set(db.execute('SELECT * FROM spell_script_names')) == after
    db.executescript(ROLLBACK.read_text())
    assert set(db.execute('SELECT * FROM spell_script_names')) == before
    assert f'RegisterSpellScript({SCRIPT});' in SOURCE.read_text()
    assert len(SOURCE.read_text().splitlines()) < 1000


def test_registered_native_damage_callback_preserves_flat_and_coefficient_spellmods(tmp_path):
    source = SOURCE.read_text()
    start = source.index('class ' + SCRIPT + ' : public SpellScript')
    end = source.index('\nclass npc_pet_shaman_earth_elemental', start)
    script = source[start:end]
    native = (ROOT / 'src/server/game/Entities/Unit/Unit.cpp').read_text()
    core_start = native.index('    // Default calculation', native.index('int32 Unit::SpellDamageBonusDone('))
    core_end = native.index('\n}\n', core_start)
    core = native[core_start:core_end]
    cpp = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <functional>
using int32=int32_t;using uint32=uint32_t;
constexpr int EFFECT_0=0,SPELL_EFFECT_SCHOOL_DAMAGE=2,TYPEID_PLAYER=4;
constexpr uint32 SPELL_SHAMAN_FIREBLAST=57984,SPELL_SHAMAN_FIRENOVA=12470,SPELL_SHAMAN_FIRESHIELD=13376;
enum class SpellModOp {BonusCoefficient,PeriodicHealingAndDamage,HealingAndDamage};
struct SpellInfo {
 uint32 Id=57984; struct EffectInfo {uint32 Effect=2;float BonusMultiplier=.429f;} Effects[1];
 uint32 GetSchoolMask()const{return 4;}float scaling=1;mutable uint32 observedLevel=0;mutable bool observedScaling=true;
 float GetSpellScalingMultiplier(uint32 level,bool flag)const{observedLevel=level;observedScaling=flag;return scaling;}
};
struct Player;
struct Unit {
 int32 localPower=0;uint32 localSchool=4;int32 GetTotalAuraModifierByMiscMask(int,uint32 school)const{return localSchool&school?localPower:0;}
 bool guardian=false,alive=true;uint32 entry=15438,type=3,level=85;Player* modOwner=nullptr;
 bool IsGuardian()const{return guardian;}uint32 GetEntry()const{return entry;}uint32 GetTypeId()const{return type;}
 uint32 getLevel()const{return level;}Player* GetSpellModOwner()const{return modOwner;}
};
struct Player:Unit {
 int calls=0;float addPercentUnits=0,lastInput=0,finalMultiplier=1;Player(){type=TYPEID_PLAYER;}
 void ApplySpellMod(SpellInfo const*,SpellModOp op,float& value){if(op==SpellModOp::BonusCoefficient){++calls;lastInput=value;value+=addPercentUnits;}else value*=finalMultiplier;}
};
struct Guardian:Unit {
 Unit* statOwner=nullptr;int32 bonus=0;Guardian(){guardian=true;}
 Unit* GetStatOwner()const{return statOwner;}int32 GetOwnerSpellDamageBonus()const{return bonus;}int32 GetBonusDamage()const{return localPower;}
};
struct SpellScript {
 struct Hook {SpellScript* self;std::function<void(Unit*,int32&,int32&,float&)> callback;
  template<class T> void Register(void(T::*method)(Unit*,int32&,int32&,float&)){
   callback=[this,method](Unit* victim,int32& damage,int32& flat,float& pct){(static_cast<T*>(self)->*method)(victim,damage,flat,pct);};
  }
 } CalcDamage{this, {}};
 Unit* caster=nullptr;SpellInfo const* info=nullptr;virtual void Register()=0;
 Unit* GetCaster(){return caster;}SpellInfo const* GetSpellInfo(){return info;}
};
SCRIPT
// Execute the actual core coefficient -> script -> final-modifier tail with
// native advertised local spell power as its input, never a final-hit patch.
struct NativeCalculation {
 Guardian* caster;SpellScript* script;
 Player* GetSpellModOwner(){return caster->GetSpellModOwner();}
 uint32 getLevel(){return caster->getLevel();}
 int32 GetTotalAuraModifierByMiscMask(int aura,uint32 school){return caster->GetTotalAuraModifierByMiscMask(aura,school);}
 int32 Calculate(SpellInfo const* spellProto,int32 initialFlat,float pct){
  int effIndex=0,stack=1,damagetype=0;constexpr int DOT=1;
  int32 pdamage=100,DoneTotal=initialFlat;constexpr int SPELL_AURA_MOD_DAMAGE_DONE=13;
LOCAL_BENEFIT
  float DoneTotalMod=pct;
  auto callDamageScript=[&](int32& damage,int32& flat,float& multiplier){script->CalcDamage.callback(nullptr,damage,flat,multiplier);};
CORE
 }
};
int main(){
 spell_sha_fire_elemental_spell_scaling script;
 static_cast<SpellScript&>(script).Register();assert(bool(script.CalcDamage.callback));
 Player owner,modOwner;Guardian guardian;guardian.statOwner=&owner;guardian.bonus=6000;
 SpellInfo info;script.caster=&guardian;script.info=&info;
 auto run=[&](int32 expected){int32 damage=100,flat=37;float pct=1.25f;
  script.CalcDamage.callback(nullptr,damage,flat,pct);
  assert(damage==100 && pct==1.25f && flat==37+expected);
  // The callback leaves final native additive/percentage calculation intact.
  assert(int32(float(damage+flat)*pct)==int32(float(137+expected)*1.25f));
 };
 // Frozen SpellEffect.dbc e3d9a470...: each configured effect0 is SCHOOL_DAMAGE
 // (2), Aura=0, including13376. Vary coefficients to detect hidden constants.
 for(uint32 id:{57984u,12470u,13376u})for(float coefficient:{.429f,1.0f,.032f,.25f,0.0f})for(float scaling:{.5f,1.0f,1.7f}){
  info.Id=id;info.Effects[0].BonusMultiplier=coefficient;info.scaling=scaling;guardian.level=80;
  run(int32(guardian.bonus*coefficient*scaling));assert(info.observedLevel==80 && !info.observedScaling);
 }
 info.Id=57984;info.Effects[0].BonusMultiplier=.25f;info.scaling=.5f;
 // Native caster spellmod owner differs from stat owner; only caster mod-owner
 // receives percent-unit BonusCoefficient adjustment, exactly once.
 guardian.modOwner=&modOwner;modOwner.addPercentUnits=5;owner.addPercentUnits=99;
 run(1050);assert(modOwner.calls==1 && modOwner.lastInput==12.5f && owner.calls==0);
 guardian.modOwner=nullptr;owner.alive=false;run(750);owner.alive=true;
 guardian.bonus=1234;run(int32(1234*.125f));guardian.bonus=6000;
 guardian.statOwner=nullptr;run(0);Unit nonplayer;guardian.statOwner=&nonplayer;run(0);guardian.statOwner=&owner;
 guardian.entry=15439;run(0);guardian.entry=15438;guardian.guardian=false;run(0);guardian.guardian=true;
 Unit nonguardian;script.caster=&nonguardian;run(0);script.caster=nullptr;run(0);script.caster=&guardian;
 info.Id=403;run(0);info.Id=57984;info.Effects[0].Effect=6;run(0);info.Effects[0].Effect=2;
 script.info=nullptr;run(0);script.info=&info;
 // Nonzero guardian-local school power flows through native calculation once.
 // A different-school aura contributes no local fire power; inherited snapshot
 // remains independent. Percentage done/final spellmods stay native.
 NativeCalculation calculation{&guardian,&script};
 info.Effects[0].BonusMultiplier=.25f;info.scaling=1;guardian.bonus=6000;
 guardian.localPower=400;
 for(uint32 schoolMask:{16u,4u}){
  guardian.localSchool=schoolMask;int32 localFirePower=schoolMask==4?400:0;
  int32 expected=int32(float(100+37+int32(localFirePower*.25f)+1500)*1.5f);
  assert(calculation.Calculate(&info,37,1.5f)==expected);
 }
 guardian.modOwner=&modOwner;modOwner.addPercentUnits=5;modOwner.finalMultiplier=1.2f;
 int32 expected=int32(float(100+37+int32(400*.30f)+int32(6000*.30f))*1.5f*1.2f);
 assert(calculation.Calculate(&info,37,1.5f)==expected);
}
'''.replace('SCRIPT', script).replace('CORE', core).replace('LOCAL_BENEFIT', re.search(r'    int32 DoneAdvertisedBenefit = GetTotalAuraModifierByMiscMask\(SPELL_AURA_MOD_DAMAGE_DONE, schoolMask\);', native)[0].replace('schoolMask', 'spellProto->GetSchoolMask()'))
    path = tmp_path / 'callback.cpp'
    path.write_text(cpp)
    binary = tmp_path / 'callback'
    result = subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True)
