"""Compile the actual completion script and native cancellation after target removal."""
from pathlib import Path
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[4]
SCRIPT=ROOT/'src/server/scripts/Spells/spell_hunter_tame_completion.cpp'
SPELL=ROOT/'src/server/game/Spells/Spell.cpp'

STUBS=r'''
#include <cstdint>
#include <functional>
#include <initializer_list>
#include <iostream>
#include <string>
#include <vector>
using uint32=uint32_t; using ObjectGuid=uint64_t;
enum {CLASS_HUNTER=3,HUNTER_PET=1,UNIT_CREATED_BY_SPELL,CURRENT_CHANNELED_SPELL,
    SPELL_EFFECT_TAMECREATURE,SPELL_MISS_NONE,SPELL_FAILED_INTERRUPTED};
enum SpellState {SPELL_STATE_NULL,SPELL_STATE_PREPARING,SPELL_STATE_LAUNCHED,
    SPELL_STATE_CHANNELING,SPELL_STATE_FINISHED};
enum class AuraRemoveFlags {ByCancel};
struct Unit {
    ObjectGuid guid=6; ObjectGuid GetGUID() const {return guid;}
    Unit* ToUnit() {return this;}
    void RemoveOwnedAura(uint32,ObjectGuid,int,AuraRemoveFlags) {}
    void RemoveDynObject(uint32) {} void RemoveGameObject(uint32,bool) {}
};
struct SpellInfo {
    uint32 Id=1515; bool effect=true;
    bool IsChanneled() const {return Id==1515;}
    bool HasEffect(int) const {return effect;}
};
namespace ObjectAccessor {Unit* GetUnit(Unit&,ObjectGuid) {return nullptr;}}
struct Manager {void NotifyNativeSpellCancelled(void*) {}};
Manager manager;Manager* sBotWorldPopulationMgr=&manager;
struct Targets {ObjectGuid guid=100;ObjectGuid GetUnitTargetGUID() const {return guid;}};
struct Spell {
    struct TargetInfo {int MissCondition=0;ObjectGuid TargetGUID=100;void DoDamageAndTriggers(Spell*);};
    SpellState m_spellState=SPELL_STATE_CHANNELING;bool m_autoRepeat=false;
    SpellInfo info;SpellInfo const* m_spellInfo=&info;SpellInfo const* aura=nullptr;
    Unit caster;Unit* m_caster=&caster;Unit* m_originalCaster=nullptr;ObjectGuid m_originalCasterGUID=6;
    Spell** m_selfContainer=nullptr;std::vector<TargetInfo> m_UniqueTargetInfo;
    std::vector<int> m_appliedMods;Targets m_targets;
    int updates=0,interruptions=0,failures=0,successes=0;
    SpellState getState() const {return m_spellState;}
    SpellInfo const* GetSpellInfo() const {return &info;}
    bool IsTriggeredByAura(SpellInfo const* p) const {return p==aura;}
    void SendChannelUpdate(uint32) {++updates;}
    void SendInterrupted(int) {++interruptions;}
    void SendCastResult(int) {++failures;}
    void CancelGlobalCooldown() {}void SetReferencedFromCurrent(bool) {}
    void finish(bool ok=true) {m_spellState=SPELL_STATE_FINISHED;if(ok)++successes;}
    void cancel();
    void CallScriptAfterHitHandlers();void CallScriptAfterCastHandlers();
};
struct Creature {
    ObjectGuid guid=100;uint32 entry=299;
    ObjectGuid GetGUID() const {return guid;}uint32 GetEntry() const {return entry;}
};
struct Pet {
    bool world=true;int type=HUNTER_PET;ObjectGuid owner=6;uint32 entry=299,created=13481;
    bool IsInWorld() const {return world;}int getPetType() const {return type;}
    ObjectGuid GetOwnerGUID() const {return owner;}uint32 GetEntry() const {return entry;}
    uint32 GetUInt32Value(int) const {return created;}
};
struct Player:Unit {
    bool player=true,present=false;int cls=CLASS_HUNTER;Spell* channel=nullptr;Pet pet;
    Player* ToPlayer() {return player?this:nullptr;}int getClass() const {return cls;}
    ObjectGuid GetPetGUID() const {return present?200:0;}
    Spell* GetCurrentSpell(int) const {return channel;}Pet* GetPet() {return present?&pet:nullptr;}
};
struct SpellScript;
struct Hook {
    std::function<void(SpellScript*)> callback;
    template<class T>void Register(void(T::*method)()) {
        callback=[method](SpellScript* script){(static_cast<T*>(script)->*method)();};
    }
    int calls=0;
    void Call(SpellScript* script) {if(callback){++calls;callback(script);}}
};
struct SpellScript {
    Player* player=nullptr;Creature* target=nullptr;Spell* trigger=nullptr;bool known=true;
    Hook BeforeHit,AfterHit,AfterCast;virtual bool Validate(SpellInfo const*) {return true;}
    virtual void Register() {}bool ValidateSpellInfo(std::initializer_list<int>) {return known;}
    Player* GetCaster() const {return player;}Creature* GetHitCreature() const {return target;}
    Spell* GetSpell() const {return trigger;}
};
SpellScript* active;
void Spell::CallScriptAfterHitHandlers() {active->AfterHit.Call(active);}
void Spell::CallScriptAfterCastHandlers() {active->AfterCast.Call(active);}
'''
MAIN=r'''
int main(int argc,char** argv) {
    std::string fault=argv[1];Spell parent,child,other;child.info.Id=13481;child.aura=&parent.info;
    Player player;Creature target;player.channel=&parent;
    spell_hun_tame_beast_completion script;script.player=&player;script.target=&target;script.trigger=&child;
    active=&script;script.Register();
    if(fault=="retired_after_hit") {
        script.AfterCast.callback=nullptr;
        script.AfterHit.Register(&spell_hun_tame_beast_completion::AfterTame);
    }
    if(fault=="non_player")player.player=false;
    if(fault=="non_hunter")player.cls=9;
    if(fault=="no_target")script.target=nullptr;
    if(fault=="had_pet")player.present=true;
    if(fault=="no_channel")player.channel=nullptr;
    if(fault=="wrong_channel")parent.info.Id=999;
    if(fault=="not_channeling")parent.m_spellState=SPELL_STATE_PREPARING;
    if(fault=="direct_trigger")child.aura=nullptr;
    if(fault=="wrong_target")parent.m_targets.guid=101;
    script.BeforeHit.Call(&script);
    // The triggered native effect creates the pet and finishes only itself.
    player.present=true;child.finish();
    if(fault=="no_pet")player.present=false;
    if(fault=="not_in_world")player.pet.world=false;
    if(fault=="summoned_pet")player.pet.type=2;
    if(fault=="foreign_owner")player.pet.owner=7;
    if(fault=="wrong_entry")player.pet.entry=300;
    if(fault=="wrong_creator")player.pet.created=883;
    if(fault=="replaced_channel")player.channel=&other;
    if(fault=="already_finished")parent.m_spellState=SPELL_STATE_FINISHED;
    // Native target lookup fails after EffectTameCreature despawns the wolf.
    // The actual core guard returns before dispatching any AfterHit hook.
    Spell::TargetInfo hit;hit.DoDamageAndTriggers(&child);
    // Spell::cast calls AfterCast after handle_immediate, even if the effect
    // already finished the child. Use the actual registered callback.
    if(fault!="old_path")child.CallScriptAfterCastHandlers();
    if(fault=="repeat")child.CallScriptAfterCastHandlers();
    // The wild target is now gone. Run the real core cancellation function,
    // which Spell::update calls when that explicit target is unavailable.
    parent.cancel();
    std::cout<<parent.updates<<' '<<parent.interruptions<<' '<<parent.failures<<' '
        <<parent.successes<<' '<<other.successes<<' '<<child.successes<<'\n';
    SpellInfo good;good.Id=13481;
    bool valid=script.Validate(&good);good.Id=1515;bool foreign=script.Validate(&good);
    good.Id=13481;good.effect=false;bool effect=script.Validate(&good);
    good.effect=true;script.known=false;bool known=script.Validate(&good);
    std::cout<<valid<<' '<<foreign<<' '<<effect<<' '<<known<<'\n';
    std::cout<<script.AfterHit.calls<<' '<<script.AfterCast.calls<<'\n';
}
'''


@pytest.fixture(scope='module')
def compiled(tmp_path_factory):
    text=SCRIPT.read_text();start=text.index('class spell_hun_tame_beast_completion')
    script=text[start:text.index('void AddSC_',start)].replace(': public SpellScript\n{',': public SpellScript\n{\npublic:',1)
    core=SPELL.read_text();start=core.index('void Spell::cancel()')
    cancel=core[start:core.index('void Spell::cast(',start)]
    start=core.index('void Spell::TargetInfo::DoDamageAndTriggers(Spell* spell)')
    dispatch=core[start:core.index('    // other targets executed',start)]
    dispatch+='    spell->CallScriptAfterHitHandlers();\n}\n'
    directory=tmp_path_factory.mktemp('native_tame_completion');source=directory/'tame.cpp';binary=directory/'tame'
    source.write_text(STUBS+script+cancel+dispatch+MAIN)
    subprocess.run(['g++','-std=c++17','-O0',str(source),'-o',str(binary)],check=True,capture_output=True,text=True)
    return binary


def result(binary,fault):
    lines=subprocess.check_output([str(binary),fault],text=True).splitlines()
    assert lines[1]=='1 0 0 0'
    return list(map(int,lines[0].split()))


@pytest.mark.parametrize('fault',['valid','repeat'])
def test_successful_trigger_finishes_exact_parent_before_target_loss(compiled,fault):
    assert result(compiled,fault)==[1,0,0,1,0,1]


def test_previous_native_path_reproduces_failure_after_pet_creation(compiled):
    assert result(compiled,'old_path')==[1,1,1,0,0,1]


def test_retired_after_hit_candidate_is_skipped_by_native_target_removal(compiled):
    assert result(compiled,'retired_after_hit')==[1,1,1,0,0,1]
    assert subprocess.check_output([str(compiled),'retired_after_hit'],text=True).splitlines()[2]=='0 0'


def test_success_uses_registered_after_cast_after_native_hit_dispatch_is_skipped(compiled):
    assert subprocess.check_output([str(compiled),'valid'],text=True).splitlines()[2]=='0 1'
    core=SPELL.read_text();start=core.index('void Spell::cast(')
    cast=core[start:core.index('template <class Container>',start)]
    assert cast.index('handle_immediate();')<cast.index('CallScriptAfterCastHandlers();')


@pytest.mark.parametrize('fault',['non_player','non_hunter','no_target','had_pet','no_channel',
    'wrong_channel','not_channeling','direct_trigger','wrong_target','no_pet','not_in_world',
    'summoned_pet','foreign_owner','wrong_entry','wrong_creator','replaced_channel'])
def test_failed_foreign_or_replaced_trigger_cannot_finish_the_parent(compiled,fault):
    r=result(compiled,fault);assert r[1:]==[1,1,0,0,1]


def test_an_already_finished_parent_gets_no_extra_terminal_update(compiled):
    assert result(compiled,'already_finished')==[0,0,0,0,0,1]


def test_completion_script_is_loaded_and_bound_only_to_final_native_trigger():
    loader=(ROOT/'src/server/scripts/Spells/spell_script_loader.cpp').read_text()
    assert loader.count('AddSC_hunter_tame_completion_spell_scripts();')==2
    sql=(ROOT/'sql/updates/world/4.3.4/2026_10_07_00_world.sql').read_text()
    assert "VALUES (13481, 'spell_hun_tame_beast_completion')" in sql
    assert 'DELETE FROM `spell_script_names` WHERE `spell_id` = 13481 AND' in sql
