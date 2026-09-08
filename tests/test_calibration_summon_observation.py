"""Production summon collector/JSON serializer with stub native objects, no effects."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_native_guardian_timeline_without_primary_pet(tmp_path):
    header = (ROOT/'src/server/game/Bots/BotCalibrationSummonObservation.h').read_text()
    # Keep the complete production collector/serializer; replace only native dependencies.
    header = re.sub(r'^#include "[^"]+"\n', '', header, flags=re.MULTILINE)
    bot_source = (ROOT/'src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp').read_text()
    start = bot_source.index('auto capturePetTimelineState =')
    end = bot_source.index('\n    };',start)+7
    collector = bot_source[start:end]
    # Compile the actual death/movement/ordinary timeline call expressions.
    callsites = re.findall(r'capturePetTimelineState\(entry(?:, target)?\);', bot_source[end:])
    assert len(callsites) == 3
    assert callsites[1:] == ['capturePetTimelineState(entry, target);'] * 2
    cpp = r'''
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <iostream>
#include <limits>
using uint64=uint64_t;using uint32=uint32_t;using uint8=uint8_t;
struct ObjectGuid {uint64 raw=0;uint64 GetRawValue()const{return raw;}uint32 GetCounter()const{return raw;}explicit operator bool()const{return raw!=0;}static ObjectGuid const Empty;};
ObjectGuid const ObjectGuid::Empty{};
constexpr int BASE_ATTACK=0,SPELL_SCHOOL_MASK_FIRE=4,UNIT_FIELD_MINDAMAGE=3,UNIT_FIELD_MAXDAMAGE=4,UNIT_MOD_CAST_HASTE=2,SUMMON_SLOT_TOTEM_FIRE=0,UNIT_CREATED_BY_SPELL=0,CURRENT_GENERIC_SPELL=0,CURRENT_CHANNELED_SPELL=1,CURRENT_AUTOREPEAT_SPELL=2;
struct SpellInfo{uint32 Id=12345;};struct Spell{SpellInfo info;SpellInfo const* GetSpellInfo(){return &info;}};
struct Creature;struct TempSummon;struct Totem;
struct Unit{
 ObjectGuid guid;Unit* owner=nullptr;Unit* victim=nullptr;Unit* helper=nullptr;std::set<Unit*> m_Controlled;
 float spellTime=0.8f,minDamage=17.25f,maxDamage=29.5f,attackPower=432.5f;int firePower=111;uint32 level=85;uint64 health=1234,maxHealth=2345;
 float GetFloatValue(int field){return field==UNIT_FIELD_MINDAMAGE?minDamage:(field==UNIT_FIELD_MAXDAMAGE?maxDamage:spellTime);}
 uint32 getLevel(){return level;}uint64 GetHealth(){return health;}uint64 GetMaxHealth(){return maxHealth;}
 float GetTotalAttackPowerValue(int type){return attackPower;}int SpellBaseDamageBonusDone(int school){return firePower;}
 bool alive=true,valid=true,engaged=true,guardian=false,pet=false,totem=false,ai=true;uint32 created=0;Spell* current=nullptr;
 virtual ~Unit()=default;
 ObjectGuid GetGUID()const{return guid;}Unit* GetVictim(){return victim;}bool IsAlive(){return alive;}
 bool IsValidAttackTarget(Unit* target){return target->valid;}bool IsEngaged(){return engaged;}Unit* getAttackerForHelper(){return engaged?helper:nullptr;}
 // Nonvirtual WorldObject accessor resolves UNIT_FIELD_SUMMONEDBY.
 Unit* GetOwner(){return owner;}Totem* ToTotem();Unit* GetCharmerOrOwner(){return owner;}bool IsTotem(){return totem;}bool IsGuardian(){return guardian;}bool IsPet(){return pet;}bool IsAIEnabled(){return ai;}
 virtual Creature* ToCreature(){return nullptr;}virtual TempSummon* ToTempSummon(){return nullptr;}
 uint32 GetUInt32Value(int){return created;}Spell* GetCurrentSpell(int type){return type==0?current:nullptr;}
};
struct Creature:Unit{uint32 entry=0;Creature* ToCreature()override{return this;}uint32 GetEntry(){return entry;}};
struct TempSummon:Creature{Unit* summoner=nullptr;TempSummon* ToTempSummon()override{return this;}Unit* GetSummoner(){return summoner;}};
// Native Minion owner is separate from WorldObject owner-GUID lookup.
// Totem InitStats skips SetMinion, so only nativeOwner is populated.
struct Minion:TempSummon{Unit* nativeOwner=nullptr;Unit* GetOwner(){return nativeOwner;}};
struct Guardian:Minion{int bonus=777,ownerBonus=2222;int GetBonusDamage()const{return bonus;}int GetOwnerSpellDamageBonus()const{return ownerBonus;}};
struct Totem:Minion{Totem(){totem=true;}};
Totem* Unit::ToTotem(){return IsTotem()?static_cast<Totem*>(this):nullptr;}
struct Map{std::map<uint64,Creature*> creatures;Creature* GetCreature(ObjectGuid guid){return creatures.count(guid.raw)?creatures[guid.raw]:nullptr;}};
struct CharmInfo{uint8 GetCommandState(){return 0;}bool IsCommandAttack(){return false;}};
struct Pet:Creature{CharmInfo* GetCharmInfo(){return nullptr;}};
struct Player:Unit{ObjectGuid m_SummonSlot[1];Map map;Map* GetMap(){return &map;}Pet* GetPet(){return nullptr;}};
struct CalibrationMetrics{struct DecisionTimelineEntry{
 std::string SummonObservationJson;uint64 ElapsedMs=500;bool PetAlive=false,PetAttacking=false,PetCommandAttack=false;uint32 PetVictimGuid=0,PetCommandState=0,PetCurrentGenericSpellId=0,PetCurrentChanneledSpellId=0,PetCurrentAutorepeatSpellId=0;
};};
'''+header+r'''
int main(){
 Player owner;owner.firePower=9999;owner.guid.raw=4294967297ULL;Player foreign;foreign.guid.raw=4294967300ULL;
 Unit target;target.guid.raw=99;owner.helper=&target;
 Totem fire;fire.guid.raw=500;fire.entry=15439;fire.created=2894;fire.nativeOwner=&owner;fire.summoner=&owner;
 owner.m_SummonSlot[0]=fire.guid;owner.map.creatures[500]=&fire;
 Guardian guardian;guardian.guid.raw=600;guardian.entry=15438;guardian.created=32982;guardian.guardian=true;guardian.owner=&fire;guardian.summoner=&fire;
 fire.m_Controlled.insert(&guardian); // deliberately absent from player's controlled list
 TempSummon unrelated;unrelated.guid.raw=700;unrelated.entry=15438;unrelated.guardian=true;unrelated.owner=&foreign;unrelated.summoner=&foreign;owner.m_Controlled.insert(&unrelated);
 Player* bot=&owner;
'''+collector+r'''
 CalibrationMetrics::DecisionTimelineEntry entry;
 capturePetTimelineState(entry,&target);std::cout<<entry.SummonObservationJson<<'\n';
 owner.spellTime=0.5f;owner.m_Controlled.insert(&guardian);owner.victim=&target;guardian.victim=&target;Spell cast;guardian.current=&cast;entry.ElapsedMs=1000;
 capturePetTimelineState(entry,&target);std::cout<<entry.SummonObservationJson<<'\n';
 fire.m_Controlled.clear();owner.m_Controlled.clear();owner.m_SummonSlot[0]={};owner.victim=nullptr;owner.engaged=false;entry.ElapsedMs=1500;
 capturePetTimelineState(entry,&target);std::cout<<entry.SummonObservationJson<<'\n';
 owner.m_SummonSlot[0]=fire.guid;fire.nativeOwner=&foreign;fire.m_Controlled.insert(&guardian);entry.ElapsedMs=2000;
 capturePetTimelineState(entry,&target);std::cout<<entry.SummonObservationJson<<'\n';
 for(float divisor:{0.0f,-1.0f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}){
  owner.spellTime=divisor;capturePetTimelineState(entry,&target);std::cout<<entry.SummonObservationJson<<'\n';
 }
 std::cout<<BotCalibrationSummonObservation::Capture(nullptr,nullptr,2500)<<'\n';
 // A matching entry can be observed even if native runtime type is not Guardian.
 Creature ordinary;ordinary.entry=15438;ordinary.guid.raw=800;ordinary.owner=&owner;
 owner.m_Controlled.clear();owner.m_Controlled.insert(&ordinary);
 std::cout<<BotCalibrationSummonObservation::Capture(&owner,&target,3000)<<'\n';
}
'''
    # Use actual production target-passing expressions in both alive paths.
    cpp = cpp.replace('Player* bot=&owner;', 'Player* bot=&owner; Unit* targetPtr=&target;')
    cpp = cpp.replace('capturePetTimelineState(entry,&target);', callsites[1].replace(', target)', ', targetPtr)'), 1)
    cpp = cpp.replace('capturePetTimelineState(entry,&target);', callsites[2].replace(', target)', ', targetPtr)'), 1)
    cpp = cpp.replace('capturePetTimelineState(entry,&target);', callsites[0], 1)
    path=tmp_path/'fixture.cpp';path.write_text(cpp);binary=tmp_path/'fixture'
    result=subprocess.run(['c++','-std=c++17',str(path),'-o',str(binary)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    result=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
    samples=list(map(json.loads,result.stdout.splitlines()))
    idle,active,absent,foreign=samples[:4]
    assert abs(idle["owner_spell_speed_multiplier"]-1.25)<0.000001
    assert active["owner_spell_speed_multiplier"]==2.0
    assert all(sample["owner_spell_speed_multiplier"] is None for sample in samples[4:])
    assert idle['owner_guid']==4294967297
    assert idle['owner_victim_guid']==0 and not idle['owner_victim_valid']
    assert idle['offensive_target_guid']==idle['owner_helper_target_guid']==99
    assert idle['owner_engaged'] and idle['owner_helper_target_valid']
    assert idle['fire_slot']=={'guid':500,'present':True,'owned':True,'entry':15439,'created_by_spell':2894,'alive':True}
    assert idle['foreign_guardians_excluded']==1
    guardian=idle['guardians'][0]
    assert guardian['guid']==600 and guardian['runtime_type']=='guardian' and guardian['ai_enabled']
    assert guardian['owner_chain']==[500]  # generic accessor stops at the totem
    assert guardian['summoner_chain']==[500,4294967297]
    assert guardian['victim_guid']==0 and not guardian['victim_valid']
    assert guardian['current_generic_spell']==0
    assert idle['owner_fire_spell_power']==9999
    assert guardian['level']==85 and guardian['health']==1234 and guardian['max_health']==2345
    assert guardian['melee_attack_power']==432.5
    assert guardian['base_attack_min_damage']==17.25 and guardian['base_attack_max_damage']==29.5
    assert guardian['guardian_bonus_damage']==777 and guardian['local_fire_spell_power']==111
    assert guardian['guardian_owner_spell_damage_bonus']==2222
    assert samples[-2]['owner_fire_spell_power'] is None
    assert samples[-1]['guardians'][0]['guardian_bonus_damage'] is None
    assert samples[-1]['guardians'][0]['guardian_owner_spell_damage_bonus'] is None
    assert samples[-1]['guardians'][0]['runtime_type']=='creature'
    assert samples[-1]['guardians'][0]['local_fire_spell_power']==111
    assert len(active['guardians'])==1  # duplicate player/totem membership deduplicated
    assert active['owner_victim_guid']==active['guardians'][0]['victim_guid']==99
    assert active['owner_victim_valid'] and active['guardians'][0]['victim_valid']
    assert active['guardians'][0]['current_generic_spell']==12345
    assert absent['guardians']==[] and absent['fire_slot']['guid']==0 and not absent['fire_slot']['present']
    assert not absent['owner_engaged'] and absent['owner_helper_target_guid']==0
    assert foreign['guardians']==[] and foreign['fire_slot']['present'] and not foreign['fire_slot']['owned']
    assert [sample['observed_elapsed_ms'] for sample in [idle,active,absent,foreign]]==[500,1000,1500,2000]
