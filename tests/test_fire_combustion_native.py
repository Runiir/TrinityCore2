"""Pinned base-period contract through native mask/script and observation consumer."""
import json
import hashlib
from pathlib import Path
import re
import subprocess

from test_fire_combustion_candidate_observation import STUB
from test_warlock_doomguard_guardian import function

ROOT = Path(__file__).resolve().parents[1]
SPELLS = ROOT / 'src/server/scripts/Spells'


def test_native_mask_consumer_base_period_and_observation(tmp_path):
    fixture = json.loads((ROOT / 'tests/fixtures/fire_combustion_native_contract.json').read_text())
    mask = fixture['combustion']['mask']
    flag = function((ROOT / 'src/common/Utilities/Util.h').read_text(), 'class TC_COMMON_API flag96').replace('TC_COMMON_API ', '') + ';'
    stub = STUB.replace('using uint64=', 'using uint8=uint8_t; using uint64=')
    insertion = stub.index('constexpr unsigned EFFECT_0')
    stub = stub[:insertion] + flag + '\n' + stub[insertion:]
    stub = stub.replace('AuraPeriod=1000,SpellClassMask=123;', 'AuraPeriod=1000;flag96 SpellClassMask{0x00c00017,0x1040,0};')
    stub = stub.replace('bool affected=true;', 'bool affected=true;flag96 SpellFamilyFlags;')
    stub = stub.replace('bool IsAffected(unsigned family,unsigned mask)const{return affected&&family==SPELLFAMILY_MAGE&&mask==123;}', 'bool IsAffected(uint32 familyName,flag96 const& familyFlags)const;')
    stub = stub.replace('struct Unit {', 'struct CastSpellExtraArgs {int bp=0;explicit CastSpellExtraArgs(bool){}CastSpellExtraArgs& AddSpellBP0(int v){bp=v;return *this;}};\nstruct Unit {int submitted=0;unsigned child=0;void CastSpell(Unit*,unsigned id,CastSpellExtraArgs const& args){child=id;submitted=args.bp;}')
    affected = function((ROOT / 'src/server/game/Spells/SpellInfo.cpp').read_text(), 'bool SpellInfo::IsAffected(')
    consumer = function((SPELLS / 'spell_mage_fire.cpp').read_text(), 'void HandleScriptEffect(SpellEffIndex effIndex)')
    # Only this exact 11129 loader correction is compiled, not a parallel mask.
    correction_source=(ROOT / 'src/server/game/Spells/SpellMgrCorrectionsPart04.cpp').read_text()
    start=correction_source.index('    ApplySpellFix({ 11129 }')
    correction=correction_source[start:correction_source.index('    });',start)+7]
    for name in ('Define.h','Player.h','SpellAuraEffects.h','SpellAuras.h','SpellInfo.h','SpellMgr.h','Util.h'):
        (tmp_path/name).write_text('#include "stub.h"\n')
    (tmp_path/'stub.h').write_text(stub)
    setup=[]
    for index,row in enumerate(fixture['sources']):
        flags=','.join(str(v) for v in row['family_flags'])
        setup.append(f"info[{index}].Id={row['spell_id']};info[{index}].SpellFamilyFlags={{{flags}}};info[{index}].Effects[{row['effect_index']}].AuraPeriod={row['base_period_ms']};effect[{index}]={{&info[{index}],30006,{row['effect_index']},{[6000,3000,1500,1500][index]}}};")
    main=r'''
#include "stub.h"
#include "Bots/BotFireCombustionObservation.h"
#include "Spells/SpellCombustion.h"
#include <cassert>
#include <iostream>
#include <limits>
using SpellEffIndex=unsigned;
constexpr unsigned SPELL_MAGE_COMBUSTION_DAMAGE=83853;
Player actor;Unit target;
Unit* GetCaster(){return &actor;}Unit* GetHitUnit(){return &target;}
SpellInfo const* GetSpellInfo(){return &manager.combustion;}
int GetEffectValue(){return manager.combustion.Effects[0].BasePoints;}
template<class F>void ApplySpellFix(std::initializer_list<unsigned> ids,F fix){assert(ids.size()==1&&*ids.begin()==11129);fix(&manager.combustion);}
''' + affected + '\n' + consumer + '\nvoid Correct(){\n'+correction+'\n}\nint main(){\n'+ '\n'.join(setup)+r'''
 actor.guid=30006;manager.periodic.haste=.75f;
 target.effects={&effect[0],&effect[1],&effect[2]};
 HandleScriptEffect(0);assert(actor.submitted==500); // original mask excludes Ignite and Living Bomb
 Correct();auto once=manager.combustion.Effects[0].SpellClassMask;Correct();assert(once==manager.combustion.Effects[0].SpellClassMask);
 assert(once.IsEqual(0x08c00017,0x00021040,0));
 HandleScriptEffect(0);assert(actor.child==83853&&actor.submitted==4500);
 auto observed=BotFireCombustionObservation::Capture(&actor,&target,1000,1002);
 assert(observed.SummedBasePoints==actor.submitted&&observed.TickCount==13);
 assert(actor.submitted*observed.TickCount==58500);
 assert(observed.Components.size()==3);
 std::cout<<BotFireCombustionObservation::ToJson(observed)<<'\n';
 // Child haste changes schedule, never source-rate snapshot.
 manager.periodic.haste=1;HandleScriptEffect(0);
 assert(actor.submitted==4500);assert(BotFireCombustionObservation::Capture(&actor,&target,1000,1002).TickCount==10);
 target.effects={&effect[0],&effect[1],&effect[3]};HandleScriptEffect(0);assert(actor.submitted==4500);
 // Individual native filter negatives, including shared word2=8 alone.
 for(unsigned i=0;i<4;++i){
  target.effects={&effect[i]};HandleScriptEffect(0);assert(actor.submitted>0);
  effect[i].owner=30007;actor.submitted=0;HandleScriptEffect(0);assert(actor.submitted==0);effect[i].owner=30006;
  info[i].school=16;HandleScriptEffect(0);assert(actor.submitted==0);info[i].school=4;
  info[i].SpellFamilyName=9;HandleScriptEffect(0);assert(actor.submitted==0);info[i].SpellFamilyName=3;
  auto flags=info[i].SpellFamilyFlags;info[i].SpellFamilyFlags={0,0,8};HandleScriptEffect(0);assert(actor.submitted==0);info[i].SpellFamilyFlags=flags;
  auto period=info[i].Effects[effect[i].index].AuraPeriod;info[i].Effects[effect[i].index].AuraPeriod=0;HandleScriptEffect(0);assert(actor.submitted==0);info[i].Effects[effect[i].index].AuraPeriod=period;
 }
 // Preserve fractions until a single final native integer conversion.
 target.effects={&effect[1],&effect[2]};effect[1].amount=2;effect[2].amount=2;
 manager.combustion.Effects[0].BasePoints=100;HandleScriptEffect(0);assert(actor.submitted==1);
 manager.combustion.Effects[0].BasePoints=150;HandleScriptEffect(0);assert(actor.submitted==2);
 assert(SpellCombustion::ScaledBasePoints(1e30,100)==INT32_MAX);
 assert(SpellCombustion::ScaledBasePoints(std::numeric_limits<double>::infinity(),100)==0);
}
'''
    main=main.replace('int main(){\n', 'int main(){\n SpellInfo info[4];AuraEffect effect[4];\n')
    source=tmp_path/'consumer.cpp';source.write_text(main);binary=tmp_path/'consumer'
    result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(tmp_path),'-I',str(ROOT/'src/server/game'),str(source),str(ROOT/'src/server/game/Bots/BotFireCombustionObservation.cpp'),'-o',str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    lines=subprocess.check_output([str(binary)],text=True).splitlines()
    observed=json.loads(lines[0]);assert len(lines[0].encode())<=2048
    assert observed['native_exact'] is False
    assert observed['component_columns']==['spell_id','effect_index','amount','source_base_period_ms','contribution']
    assert observed['components']==[[12654,0,6000,2000,3000],[44457,0,3000,3000,1000],[92315,1,1500,3000,500]]
    assert mask == [0x00c00017,0x1040,0]


def test_split_registration_and_native_include_contract():
    sources={p.name:p.read_text() for p in SPELLS.glob('spell_mage*.cpp')}
    assert all(len(s.splitlines())<1000 for s in sources.values())
    declarations=(SPELLS/'spell_mage_shared.h').read_text()
    main=sources['spell_mage.cpp']
    fixture=json.loads((ROOT/'tests/fixtures/fire_combustion_native_contract.json').read_text())
    for name, digest in fixture['unchanged_enum_sha256'].items():
        assert hashlib.sha256(function(declarations,'enum '+name).encode()).hexdigest()==digest,name
    for name, digest in fixture['unchanged_script_sha256'].items():
        matches=[s for s in sources.values() if re.search(r'class '+re.escape(name)+r'\s',s)]
        assert len(matches)==1,name
        assert hashlib.sha256(function(matches[0],'class '+name).encode()).hexdigest()==digest,name
    registration=function(main,'void AddSC_mage_spell_scripts()')
    for wrapper in re.findall(r'RegisterMageScript_\w+',registration):
        owner=next(s for s in sources.values() if 'void '+wrapper+'()' in s)
        original=re.search(r'(RegisterSpell(?:Script|AndAuraScriptPair)\([^\n]+\);)',function(owner,'void '+wrapper+'()'))[1]
        registration=registration.replace(wrapper+'();',original)
    assert re.findall(r'    (RegisterSpell(?:Script|AndAuraScriptPair)\([^\n]+\);)',registration)==fixture['registration_order']
    # Exact registration order is preserved via per-script cross-TU wrappers.
    for call in re.findall(r'    (RegisterMageScript_\w+)\(\);',main):
        assert declarations.count('void '+call+'();')==1
        assert sum(s.count('void '+call+'()') for s in sources.values())==1
    for name in ('spell_mage_fire.cpp','spell_mage_frost.cpp','spell_mage.cpp'):
        for header in ('ScriptMgr.h','SpellInfo.h','SpellAuras.h','SpellAuraEffects.h','Unit.h','Util.h','spell_mage_shared.h'):
            assert '#include "'+header+'"' in sources[name]
    cmake=(ROOT/'src/server/scripts/CMakeLists.txt').read_text()
    assert 'CollectSourceFiles(${SCRIPT_MODULE_PATH}' in cmake
    collection=(ROOT/'cmake/macros/AutoCollect.cmake').read_text()
    assert '*.cpp' in collection
    loader=(SPELLS/'spell_script_loader.cpp').read_text()
    assert 'AddSC_mage_spell_scripts();' in loader
    assert 'Spells/SpellCombustion.h' in sources['spell_mage_fire.cpp']
    helper=(ROOT/'src/server/game/Spells/SpellCombustion.h').read_text()
    for forbidden in ('GetPeriod(', 'CalcPeriod(', 'ApplySpellMod(', 'CalculateSpellDamage('):
        assert forbidden not in helper


def test_actual_child_period_and_tick_count_apply_haste_once(tmp_path):
    period=function((ROOT/'src/server/game/Spells/SpellInfo.cpp').read_text().replace('/*= {}*/', ''),'int32 SpellInfo::CalcPeriod(')
    ticks=function((ROOT/'src/server/game/Spells/Auras/SpellAuraEffects.cpp').read_text(),'uint32 AuraEffect::GetTotalTicks() const')
    source=tmp_path/'period.cpp';binary=tmp_path/'period'
    source.write_text(r'''
#include "Spells/SpellCombustion.h"
#include <optional>
#include <cassert>
template<class T>using Optional=std::optional<T>;
using SpellEffIndex=unsigned;
constexpr unsigned SPELL_ATTR3_IGNORE_CASTER_MODIFIERS=1,SPELL_ATTR5_SPELL_HASTE_AFFECTS_PERIODIC=2,SPELL_ATTR8_MELEE_HASTE_AFFECTS_PERIODIC=4,SPELL_ATTR5_EXTRA_INITIAL_PERIOD=8;
namespace SpellModOp {constexpr int Period=1;}
struct Unit;
struct WorldObject {Unit const* unit=nullptr;Unit const* ToUnit()const{return unit;}};
struct Player {template<class... T>void ApplySpellMod(T...)const{assert(false);}};
struct Unit {Player const* GetSpellModOwner()const{return nullptr;}};
struct SpellInfo {struct Effect {int32 AuraPeriod=0;bool IsEffect()const{return true;}}Effects[3];
 unsigned attributes=0;float haste=1;
 bool HasAttribute(unsigned flag)const{return (attributes&flag)!=0;}
 float CalcPeriodicHasteMod(Unit const*)const{return haste;}
 int32 CalcPeriod(WorldObject const*,SpellEffIndex,Optional<int32>)const;
};
struct Aura {bool IsPermanent()const{return false;}int GetMaxDuration()const{return 10000;}int GetRolledOverDuration()const{return 0;}};
struct AuraEffect {int32 _period=0;SpellInfo const* m_spellInfo=nullptr;Aura aura;
 Aura const* GetBase()const{return &aura;}uint32 GetTotalTicks()const;
};
''' + period + '\n' + ticks + r'''
int main(){
 Unit actor;WorldObject caster{&actor};SpellInfo ignite,bomb,pyro,child;
 ignite.Effects[0].AuraPeriod=2000;bomb.Effects[0].AuraPeriod=pyro.Effects[0].AuraPeriod=3000;child.Effects[0].AuraPeriod=1000;
 bomb.attributes=pyro.attributes=child.attributes=SPELL_ATTR5_SPELL_HASTE_AFFECTS_PERIODIC;
 for(float haste:{1.f,.75f}){
  ignite.haste=bomb.haste=pyro.haste=child.haste=haste;
  double rate=SpellCombustion::SourceRate(6000,ignite.Effects[0].AuraPeriod)+SpellCombustion::SourceRate(3000,bomb.Effects[0].AuraPeriod)+SpellCombustion::SourceRate(1500,pyro.Effects[0].AuraPeriod);
  assert(SpellCombustion::ScaledBasePoints(rate,100)==4500);
  AuraEffect dot;dot.m_spellInfo=&child;dot._period=child.CalcPeriod(&caster,0,{});
  if(haste==.75f){
   assert(ignite.CalcPeriod(&caster,0,{})==2000&&bomb.CalcPeriod(&caster,0,{})==2250&&pyro.CalcPeriod(&caster,0,{})==2250);
   assert(dot._period==750&&dot.GetTotalTicks()==13&&4500*dot.GetTotalTicks()==58500);
   double wrong=SpellCombustion::SourceRate(6000,ignite.CalcPeriod(&caster,0,{}))+SpellCombustion::SourceRate(3000,bomb.CalcPeriod(&caster,0,{}))+SpellCombustion::SourceRate(1500,pyro.CalcPeriod(&caster,0,{}));
   assert(SpellCombustion::ScaledBasePoints(wrong,100)*dot.GetTotalTicks()==65000);
  }else assert(dot._period==1000&&dot.GetTotalTicks()==10);
 }
}
''')
    result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'src/server/game'),'-I',str(ROOT/'src/common'),str(source),'-o',str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    subprocess.run([str(binary)],check=True)


def test_frost_cone_namespace_helper_and_actual_script_compile(tmp_path):
    frost=(SPELLS/'spell_mage_frost.cpp').read_text()
    main=(SPELLS/'spell_mage.cpp').read_text()
    # Include and declaration must come from the same production TU, not a
    # fixture replacement that would hide the split's missing native symbol.
    array_include='\n'.join(line for line in frost.splitlines() if line=='#include <array>')
    array_declaration='\n'.join(line for line in frost.splitlines() if line.startswith('static std::array<uint32, 2> const ImprovedConeOfColdSpellIds'))
    assert 'ImprovedConeOfColdSpellIds' not in main
    cone=function(frost,'class spell_mage_cone_of_cold')+';'
    # Public exposure only lets the fixture call private hook bodies; their
    # definitions and registration remain the production class.
    cone=cone.replace('class spell_mage_cone_of_cold', 'struct spell_mage_cone_of_cold')
    source=tmp_path/'cone.cpp';binary=tmp_path/'cone'
    source.write_text('#include "Define.h"\n#include "spell_mage_shared.h"\n#include <cassert>\n'+array_include+r'''
using SpellEffIndex=unsigned;
constexpr unsigned SPELLFAMILY_MAGE=3,EFFECT_0=0,SPELL_EFFECT_APPLY_AURA=6;
struct SpellInfo {unsigned rank=1;unsigned GetRank()const{return rank;}};
struct AuraEffect {SpellInfo info;bool affecting=true;
 bool IsAffectingSpell(SpellInfo const*)const{return affecting;}SpellInfo const* GetSpellInfo()const{return &info;}};
struct Unit {AuraEffect* aura=nullptr;unsigned cast=0;
 AuraEffect const* GetDummyAuraEffect(unsigned,unsigned,unsigned)const{return aura;}
 void CastSpell(Unit*,unsigned spell,bool triggered){assert(triggered);cast=spell;}};
Unit caster,target;SpellInfo info;
struct Hook {template<class... T>void Register(T...){}};
struct SpellScript {virtual ~SpellScript()=default;virtual bool Validate(SpellInfo const*){return false;}virtual void Register(){}
 Unit* GetCaster(){return &caster;}Unit* GetHitUnit(){return &target;}SpellInfo const* GetSpellInfo(){return &info;}
 template<class T>bool ValidateSpellInfo(T const& ids){return ids.size()==2&&ids[0]==83301&&ids[1]==83302;}
 Hook OnEffectHitTarget;
};
namespace Spells::Mage {
''' + array_declaration + '\n' + cone + r'''
}
int main(){Spells::Mage::spell_mage_cone_of_cold script;AuraEffect aura;caster.aura=&aura;
 assert(script.Validate(&info));script.Register();
 script.HandleConeOfColdScript(0);assert(target.cast==83301);
 aura.info.rank=2;script.HandleConeOfColdScript(0);assert(target.cast==83302);
 target.cast=0;aura.affecting=false;script.HandleConeOfColdScript(0);assert(target.cast==0);
 caster.aura=nullptr;script.HandleConeOfColdScript(0);assert(target.cast==0);
}
''')
    result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'src/common'),'-I',str(SPELLS),str(source),'-o',str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    subprocess.run([str(binary)],check=True)


def test_split_namespace_helpers_remain_with_their_consumers():
    # Inventory of non-script namespace helpers in the original Mage unit.
    # Enum dependencies are shared/hash-checked in the split contract above.
    definitions={
        'ImprovedConeOfColdSpellIds':'static std::array<uint32, 2> const ImprovedConeOfColdSpellIds',
        'ConjureRefreshmentData':'struct ConjureRefreshmentData',
        '_conjureData':'ConjureRefreshmentData const _conjureData[]',
        'MAX_CONJURE_REFRESHMENT_SPELLS':'uint8 const MAX_CONJURE_REFRESHMENT_SPELLS',
        'SummonerCheck':'class SummonerCheck',
    }
    for symbol,declaration in definitions.items():
        owners=[]
        for path in SPELLS.glob('spell_mage*.cpp'):
            text=path.read_text()
            if re.search(r'\b'+symbol+r'\b',text):
                assert declaration in text,(path.name,symbol)
                owners.append(path.name)
        assert len(owners)==1,(symbol,owners)
