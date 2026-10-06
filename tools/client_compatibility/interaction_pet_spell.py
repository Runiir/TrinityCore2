"""Validate one native owned Blood Pact and restore its aura through ordinary pet controls."""
import argparse,copy,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import pets,saved,character,SCRIPT_BOUNDARY
from .interaction_pet_command_probe import read,expected_guid
from .interaction_pet_target import retained_imp,pair,PetOracle,read_menu
from .interaction_pet_react_modes import suite as restored_suite,public_bar
from .interaction_pet_follow_capture import FollowPresence
from .interaction_pet_dismiss import vitals,dismiss_checks,dismiss_ready,public_pet
from .interaction_pet_summon import SummonOracle,summon_checks
from .interaction_pet_commands import PET_KEYS
from .interaction_spellbook_navigation import wire_known
from .interaction_ground_movement import position
from .interaction_operations import click_case
from .interaction_macros import require
from .observation.journal import entries
from .world.objects import INDEX
from .pet_autocast_capture_evidence import button
from .pet_spell_evidence import buffs,native_aura,request_checks


class SpellPresence(FollowPresence):
    def __init__(self,session,owner,started):
        super().__init__(session,owner,started);self.auras={};self.aura_packets=[]

    def inspect_packet(self,p):
        super().inspect_packet(p)
        if p.get('direction')=='from_native' and p.get('name') in ('SMSG_AURA_UPDATE','SMSG_AURA_UPDATE_ALL'):
            parsed=native_aura(p,self.owner)
            if parsed is None:return
            if parsed['all']:self.auras={}
            for row in parsed['entries']:
                if row['spell']:self.auras[row['slot']]=row
                else:self.auras.pop(row['slot'],None)
            self.aura_packets.append({'packet':p,'decoded':parsed})


def pet_vitals(o):
    if not o.present():raise RuntimeError('owned pet vitals require current native presence')
    fields=o.pet['fields'];names=('UNIT_FIELD_HEALTH','UNIT_FIELD_MAXHEALTH','UNIT_FIELD_POWER1','UNIT_FIELD_MAXPOWER1')
    if any(INDEX[n] not in fields for n in names):raise RuntimeError('native pet vitals are incomplete')
    return {n:fields[INDEX[n]] for n in names}


def cleanup_authority(t,o):
    control=read(t,'spell_cleanup_owned_control');o.poll()
    if (t.fixture.get('guid')!=5 or not control['ui_clean'] or not o.present() or o.pet.get('kind')!=3
        or pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')!=5
        or o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=2
        or 688 not in wire_known(t,o.session)):
        raise RuntimeError('ordinary spell cleanup lacks current owned pet and native summon authority')
    button(control['probe'],o.pet,6307,True)
    return control


def reset_pet(t,o):
    control=cleanup_authority(t,o)
    guid=o.pet['guid'];expected=expected_guid(o.pet);identity=retained_imp(t.fixture,pets(5))
    t.receipt['spell_reset_authority']={'public':control,'pet':copy.deepcopy(o.pet),'ordinary_controls_only':True};t.persist()
    try:
        t.execute({'kind':'chat','value':'/targetexact '+identity['name']})
        selected,_=t.observe('spell_cleanup_owned_target');target=PetOracle(o.session,5,o.started).poll()
        if selected['target'].get('guid')!=expected or target.selected()!=guid:
            raise RuntimeError('ordinary spell cleanup target differs from current owned pet')
        read_menu(t,target,expected);since=time.time()
        def dismissed(b,a,s):
            o.poll();checks,requests=dismiss_checks(o,guid,since,a,s)
            return {'status':'native_owned_pet_dismiss_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'cleanup_only':True}}
        require(click_case(t,'fixture.spell_restore.dismiss','Dismiss the owned Imp once to remove its temporary Blood Pact aura.',
            lambda c:c['kind']=='Button' and c.get('text')=='Dismiss',dismissed,
            await_state=dismiss_ready),'native_owned_pet_dismiss_pass')
        absent=public_pet(t,'spell_cleanup_absent');o.poll();state,frame=t.observe('spell_cleanup_absence')
        absence=(not o.present() and guid in o.removed and pair(o.player,'UNIT_FIELD_SUMMON')==0
            and absent.get('exists') is False and state['target'].get('exists') is False)
        t.receipt['spell_cleanup_absence']={'confirmed':absence,'public':absent,'frame':frame};t.persist()
        if not absence:raise RuntimeError('ordinary spell cleanup cannot prove absence before summon')
        summoned=SummonOracle(o.session,5,o.started).poll();since=time.time()
        def outcome(b,a,s):
            summoned.poll();checks,packets=summon_checks(summoned,since,guid,identity,s,absence)
            checks['ui_clean']=not a.get('lua_errors') and not a.get('blocked_actions')
            return {'status':'native_owned_pet_summon_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'packets':packets,'cleanup_only':True}}
        require(t.step('fixture.spell_restore.summon','Summon the same retained Imp once from confirmed absence.',
            {'summon':{'kind':'chat','value':'/cast Summon Imp'}},outcome,diagnostic_action='summon',
            await_state=lambda a:summoned.poll().present() and not a.get('player_cast',{}).get('active')),
            'native_owned_pet_summon_pass')
    finally:
        state,_=t.observe('spell_cleanup_reset_selection')
        if state['target'].get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
        t.clean_panels()


def restore_spell(t,o,original):
    t.clean_panels();state,frame=t.observe('spell_cleanup_inspection');o.poll()
    changed=(o.auras!=original['auras'] or buffs(state)!=original['public_buffs']
        or vitals(o)!=t.receipt['baseline']['vitals'] or pet_vitals(o)!=original['pet_vitals'])
    t.receipt['spell_cleanup_inspection']={'changed':changed,'auras':copy.deepcopy(o.auras),
        'public_buffs':buffs(state),'frame':frame,'input_replayed':False};t.persist()
    if changed:reset_pet(t,o)
    deadline=time.monotonic()+120;samples=[]
    while True:
        o.poll();owned=o.present();owner=vitals(o);pet=pet_vitals(o) if owned else None
        if (owned and owner==t.receipt['baseline']['vitals'] and pet==original['pet_vitals']
            and o.auras==original['auras']):break
        samples.append({'time':time.time(),'owner_vitals':owner,'pet_vitals':pet,'input_replayed':False})
        if time.monotonic()>deadline:break
        time.sleep(2)
    t.receipt['spell_cleanup_settling']=samples;t.persist()
    state,_=t.observe('spell_cleanup_before_clear')
    if state['target'].get('exists'):t.execute({'kind':'chat','value':'/cleartarget'})
    t.clean_panels();sample=read(t,'spell_cleanup_restored');state,frame=t.observe('spell_cleanup_complete');o.poll()
    identity=retained_imp(t.fixture,pets(5));baseline=t.receipt['baseline']
    checks={'native_auras':o.auras==original['auras'],'public_buffs':buffs(state)==original['public_buffs'],
        'owner_vitals':vitals(o)==baseline['vitals'],'pet_vitals':pet_vitals(o)==original['pet_vitals'],
        'owned_retained_pet':o.present() and pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')==5
            and o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])==2,
        'public_owned_pet':sample['probe'].get('pet_guid')==expected_guid(o.pet),
        'public_bar':public_bar(sample['probe'])==baseline['public_bar'],
        'saved':saved(5)==baseline['saved'] and {k:identity[k] for k in PET_KEYS}==baseline['pet'],
        'position':position(5)==baseline['position'],'money':character(5,2)['money']==baseline['money']}
    t.receipt['spell_cleanup']={'checks':checks,'frame':frame,'public':sample,'native_auras':copy.deepcopy(o.auras),
        'native_pet':copy.deepcopy(o.pet),'ordinary_controls_only':True};t.persist()
    if not all(checks.values()):raise RuntimeError('ordinary pet spell cleanup differs from original state')


def cast(t,base):
    o=SpellPresence(base.session,5,base.started).poll();state,frame=t.observe('spell_native_baseline')
    baseline=t.receipt['baseline'];original={'auras':copy.deepcopy(o.auras),'public_buffs':buffs(state),
        'pet_vitals':pet_vitals(o)}
    if (not o.present() or o.pet['guid']!=base.pet['guid'] or 688 not in wire_known(t,o.session)
        or 6307 in original['public_buffs'] or any(r['spell']==6307 for r in original['auras'].values())
        or vitals(o)!=baseline['vitals'] or original['pet_vitals']['UNIT_FIELD_HEALTH']!=original['pet_vitals']['UNIT_FIELD_MAXHEALTH']
        or original['pet_vitals']['UNIT_FIELD_POWER1']!=original['pet_vitals']['UNIT_FIELD_MAXPOWER1']):
        raise RuntimeError('requires original owned idle pet, no Blood Pact and known ordinary summon cleanup')
    t.receipt['spell_baseline']={**original,'frame':frame,'native_pet':copy.deepcopy(o.pet)};t.persist()
    try:
        control=read(t,'spell_native_control');row,point=button(control['probe'],o.pet,6307,True)
        input_pet=copy.deepcopy(o.pet);since=time.time();t.receipt['spell_started_at']=since;t.persist()
        def outcome(b,a,s):
            sample=read(t,'spell_native_applied');state,frame=t.observe('spell_native_outcome');o.poll()
            checks,requests=request_checks(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,since,time.time(),input_pet)
            aura=[r for r in o.auras.values() if r['spell']==6307]
            fresh=[p for p in o.aura_packets if p['packet']['time']>=since and
                any(r['spell']==6307 and r.get('caster')==input_pet['guid'] for r in p['decoded']['entries'])]
            identity=retained_imp(t.fixture,pets(5));accepted=position(5)
            checks.update(native_owned_buff=len(aura)==1 and aura[0].get('caster')==input_pet['guid'] and bool(fresh),
                public_buff=buffs(state).count(6307)==1,
                native_max_health_increased=vitals(o)['UNIT_FIELD_MAXHEALTH']>baseline['vitals']['UNIT_FIELD_MAXHEALTH'],
                other_native_auras={k:r for k,r in o.auras.items() if r['spell']!=6307}==original['auras'],
                owned_native_pet=o.present() and o.pet['guid']==input_pet['guid']
                    and pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')==5,
                public_owned_pet=sample['probe'].get('pet_guid')==expected_guid(input_pet)
                    and sample['probe'].get('owner_guid')==t.guid,
                public_bar=public_bar(sample['probe'])==baseline['public_bar'],
                persisted_bar={k:identity[k] for k in PET_KEYS}==baseline['pet'] and identity['Reactstate']==3,
                saved=saved(5)==baseline['saved'],position=accepted==baseline['position'],
                money=character(5,2)['money']==baseline['money'],ui_clean=sample['ui_clean'],
                public_idle=sample['probe'].get('pet_speed')==sample['probe'].get('player_speed')==0)
            return {'status':'owned_native_pet_spell_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'input_pet':input_pet,'native_buff':aura,
                    'native_aura_packets':fresh,'native_vitals':vitals(o),'public':sample,'state':state,'frame':frame,
                    'owner_position':accepted,'observed_button':row}}
        require(t.step('pets.spell_cast','Cast stock Blood Pact once and require native owned completion, aura and public buff.',
            {'cast':{'kind':'click','value':point,'button':1,'hold':.4}},outcome,diagnostic_action='cast'),
            'owned_native_pet_spell_pass')
    finally:restore_spell(t,o,original)


def suite(t,preparation,entry):
    restored_suite(t,preparation,entry,sequence=((3,'fixture.pet_assist_restore'),),capture=cast)
    t.receipt.update(phase='owned_native_pet_spell_complete',qualified_scope=
        'One idle owned Imp stock Blood Pact, exact owned native request/completion and native caster aura/public buff, '
        'ordinary pet cleanup and whole original-state restoration. Other spells, combat and other pets/classes remain open.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
