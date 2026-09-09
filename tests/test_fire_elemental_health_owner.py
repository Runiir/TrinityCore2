"""Execute native FE initialization branch and owner resolver with stub units.

The fixture does not model UpdateAllStats, native spell effects, or survival.
"""
from pathlib import Path
import subprocess
from test_shaman_fire_elemental_owner_stats import extract

ROOT = Path(__file__).resolve().parents[1]


def test_native_fire_elemental_health_owner(tmp_path):
    source = (ROOT / 'src/server/game/Entities/Pet/GuardianInitialization.cpp').read_text()
    branch = extract(source, 'case ENTRY_FIRE_ELEMENTAL:')
    resolver = extract((ROOT / 'src/server/game/Entities/Creature/TemporarySummon.cpp').read_text(),
                       'Unit* Guardian::GetStatOwner() const')
    cpp = r'''
#include <cassert>
#include <cstdint>
using uint32=uint32_t;using int32=int32_t;
constexpr int ENTRY_FIRE_ELEMENTAL=15438,SPELL_SCHOOL_MASK_FIRE=4,BASE_ATTACK=0,MINDAMAGE=0,MAXDAMAGE=1;
struct Totem;
struct Unit {
 Unit* genericOwner=nullptr;bool totem=false;uint32 maxHealth=120004;int32 spellPower=2345;
 Unit* GetOwner()const{return genericOwner;}bool IsTotem()const{return totem;}Totem* ToTotem();
 uint32 CountPctFromMaxHealth(int pct)const{return maxHealth*pct/100;}
 int32 SpellBaseDamageBonusDone(int)const{return spellPower;}
};
struct Totem:Unit {Unit* nativeOwner=nullptr;Totem(){totem=true;}Unit* GetOwner()const{return nativeOwner;}};
Totem* Unit::ToTotem(){return static_cast<Totem*>(this);}
struct Minion:Unit {Unit* m_owner=nullptr;Unit* GetOwner()const{return m_owner;}};
struct Guardian:Minion {
 uint32 createHealth=8507,mana=0;int32 bonus=0;float damage[2]={};
 Unit* GetStatOwner()const;
 void SetCreateHealth(uint32 v){createHealth=v;}void SetBonusDamage(int32 v){bonus=v;}
 void SetCreateMana(uint32 v){mana=v;}void SetBaseWeaponDamage(int,int k,float v){damage[k]=v;}
 void InitializeBranch(){int petlevel=85;switch(ENTRY_FIRE_ELEMENTAL){
''' + branch + r'''
 }}
};
''' + resolver + r'''
int main(){
 Unit player;Totem totem;totem.nativeOwner=&player;
 Guardian g;g.m_owner=&totem;assert(totem.genericOwner==nullptr);g.InitializeBranch();
 assert(g.createHealth==90003);assert(g.bonus==1172);assert(g.mana==878);
 assert(g.damage[0]==255 && g.damage[1]==425);
 totem.nativeOwner=nullptr;Guardian missing;missing.m_owner=&totem;missing.InitializeBranch();
 assert(missing.createHealth==8507 && missing.bonus==0);
 Unit ordinary;ordinary.genericOwner=&player;Guardian fallback;fallback.m_owner=&ordinary;fallback.InitializeBranch();
 assert(fallback.createHealth==90003 && fallback.bonus==1172);
 Guardian noOwner;noOwner.InitializeBranch();assert(noOwner.createHealth==8507 && noOwner.bonus==0);
 ordinary.genericOwner=nullptr;Guardian direct;direct.m_owner=&ordinary;direct.InitializeBranch();
 assert(direct.createHealth==8507 && direct.bonus==0);
}
'''
    path = tmp_path / 'health.cpp'; path.write_text(cpp)
    binary = tmp_path / 'health'
    result = subprocess.run(['c++', '-std=c++17', str(path), '-o', str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
