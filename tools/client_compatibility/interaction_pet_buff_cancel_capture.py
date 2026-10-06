"""Capture ordinary owner-buff cancellation on the explicitly unrestored Blood Pact fixture."""
import argparse,copy,json,struct,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import pets,saved,character,SCRIPT_BOUNDARY
from .interaction_pet_spell import SpellPresence,pet_vitals
from .interaction_pet_dismiss import vitals
from .interaction_pet_target import pair,retained_imp
from .interaction_pet_command_probe import read,expected_guid
from .interaction_pet_react_modes import suite as restored_suite,public_bar
from .interaction_pet_commands import PET_KEYS
from .interaction_ground_movement import position
from .interaction_macros import require
from .pet_spell_evidence import buffs
from .world.objects import INDEX
from .observation.journal import entries


def authority(t,o,sample,state):
    aura=[r for r in o.auras.values() if r['spell']==6307]
    if (t.fixture.get('guid')!=5 or not o.present() or o.pet.get('kind')!=3
        or pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')!=5
        or o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=2
        or len(aura)!=1 or aura[0].get('caster')!=o.pet['guid']
        or buffs(state).count(6307)!=1 or not sample.get('ui_clean')
        or sample['probe'].get('owner_guid')!=t.guid
        or sample['probe'].get('pet_guid')!=expected_guid(o.pet)):
        raise RuntimeError('stock buff cancellation lacks current owned Blood Pact authority')
    return aura[0]


def capture(t,base):
    o=SpellPresence(base.session,5,base.started).poll()
    sample=read(t,'buff_cancel_control');state,frame=t.observe('buff_cancel_baseline');o.poll()
    aura=authority(t,o,sample,state);baseline=t.receipt['baseline']
    original={'auras':copy.deepcopy(o.auras),'public_buffs':buffs(state),'pet_vitals':pet_vitals(o)}
    if (o.pet['guid']!=base.pet['guid'] or vitals(o)!=baseline['vitals']
        or public_bar(sample['probe'])!=baseline['public_bar']):
        raise RuntimeError('stock buff cancellation baseline changed')
    t.receipt.update(buff_cancel_baseline={**original,'frame':frame,'native_aura':aura,
        'native_pet':copy.deepcopy(o.pet)},known_unrestored_fixture=True,original_ui132_restored=False,
        qualification_added=False)
    t.persist();since=time.time();t.receipt['buff_cancel_started_at']=since;t.persist()
    def outcome(b,a,s):
        after=read(t,'buff_cancel_after');state,frame=t.observe('buff_cancel_outcome');o.poll()
        scoped=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('session')==o.session
            and since<=p.get('time',0)<=time.time() and p.get('name') in
            ('CMSG_CANCEL_AURA','CMSG_PET_CANCEL_AURA','CMSG_PET_ACTION','CMSG_PET_ABANDON',
             'CMSG_PET_SET_ACTION','CMSG_CAST_SPELL')]
        modern=[p for p in scoped if p.get('direction')=='from_client']
        native=[p for p in scoped if p.get('direction')=='to_native']
        identity=retained_imp(t.fixture,pets(5));accepted=position(5)
        checks={'one_actual_stock_cancel':len(modern)==1 and modern[0]['name']=='CMSG_CANCEL_AURA',
            'actual_raw_body':len(modern)==1 and isinstance(modern[0].get('body'),str)
                and bool(modern[0]['body']) and len(modern[0]['body'])%2==0
                and all(c in '0123456789abcdef' for c in modern[0]['body']),
            'native_player_cancel_only':len(native)==1 and native[0]['name']=='CMSG_CANCEL_AURA'
                and native[0].get('body')==struct.pack('<I',6307).hex(),
            'no_pet_cancel_cast_or_abandon':not any(p['name']!='CMSG_CANCEL_AURA' for p in scoped),
            'native_aura_unchanged':o.auras==original['auras'],
            'public_buffs_unchanged':buffs(state)==original['public_buffs'],
            'native_vitals_unchanged':vitals(o)==baseline['vitals'] and pet_vitals(o)==original['pet_vitals'],
            'current_owned_pet':o.present() and o.pet['guid']==base.pet['guid'],
            'public_owned_pet':after['probe'].get('pet_guid')==expected_guid(o.pet)
                and after['probe'].get('owner_guid')==t.guid,
            'native_saved_bar':{k:identity[k] for k in PET_KEYS}==baseline['pet'] and identity['Reactstate']==3,
            'public_bar':public_bar(after['probe'])==baseline['public_bar'],
            'saved':saved(5)==baseline['saved'],'position':accepted==baseline['position'],
            'money':character(5,2)['money']==baseline['money'],'owned_online':character(5,2)['online']==1,
            'public_idle':after['probe'].get('pet_speed')==after['probe'].get('player_speed')==0,
            'ui_clean':after['ui_clean']}
        return {'status':'owned_stock_buff_cancel_capture_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'modern_requests':modern,'native_requests':native,'native_aura':copy.deepcopy(o.auras),
                'native_pet':copy.deepcopy(o.pet),'public':after,'state':state,'frame':frame,
                'native_vitals':vitals(o),'wire_layout_inferred':False,'qualification_added':False}}
    require(t.step('diagnostic.pet_blood_pact.cancel','Capture one stock /cancelaura Blood Pact on the known unrestored owned buff.',
        {'cancel':{'kind':'chat','value':'/cancelaura Blood Pact','description':'Use the installed ordinary secure aura-cancel command once.'}},
        outcome,diagnostic_action='cancel'),'owned_stock_buff_cancel_capture_pass')


def suite(t,preparation,entry):
    restored_suite(t,preparation,entry,sequence=((3,'fixture.pet_assist_restore'),),capture=capture)
    t.receipt.update(phase='owned_stock_buff_cancel_capture_complete',qualified_scope=
        'One ordinary owner Blood Pact cancellation request, unchanged pet-owned native area aura and known unrestored '
        'UI132 diagnostic fixture state, Assist and same-fixture whole restoration. No pet cancellation or spell qualification; '
        'the original pre-UI132 aura/vitals still require repair.')


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
