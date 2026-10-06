"""Capture one observed stock Blood Pact click without admitting a guessed spell shape."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import pets,character,SCRIPT_BOUNDARY
from .interaction_pet_command_probe import read,expected_guid
from .interaction_pet_target import retained_imp
from .interaction_pet_react_modes import suite as restored_suite,public_bar
from .interaction_pet_commands import PET_KEYS
from .interaction_macros import require
from .observation.journal import entries
from .pet_autocast_capture_evidence import button,native_buttons


def capture(t,o):
    baseline=t.receipt['baseline'];native=native_buttons(t.receipt['native_catalog'],o.pet)
    before=read(t,'manual_spell_control');row,point=button(before['probe'],o.pet,6307,True)
    if public_bar(before['probe'])!=baseline['public_bar']:
        raise RuntimeError('manual spell capture requires the exact original enabled bar')
    since=time.time();t.receipt['manual_spell_started_at']=since;t.persist()
    def outcome(b,a,s):
        after=read(t,'manual_spell_local');o.poll()
        scoped=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl')
            if p.get('session')==o.session and since<=p.get('time',0)<=time.time()
            and (p.get('name','').startswith('CMSG_PET_') or p.get('name')=='CMSG_CAST_SPELL')]
        modern=[p for p in scoped if p.get('direction')=='from_client']
        forwarded=[p for p in scoped if p.get('direction')=='to_native']
        t.receipt['manual_spell_request_capture']={'spell':6307,'slot':5,'modern_requests':modern,
            'native_requests':forwarded,'public':after,'wire_layout_inferred':False};t.persist()
        persisted=retained_imp(t.fixture,pets(5));catalogs=[c for c in o.catalogs if c['guid']==o.pet['guid']]
        checks={'one_actual_stock_pet_action':len(modern)==1 and modern[0]['name']=='CMSG_PET_ACTION',
            'raw_body_captured':len(modern)==1 and isinstance(modern[0].get('body'),str)
                and bool(modern[0]['body']) and len(modern[0]['body'])%2==0
                and all(c in '0123456789abcdef' for c in modern[0]['body']),
            'no_native_spell_or_pet_action':not forwarded,
            'no_abandon':not any(p['name']=='CMSG_PET_ABANDON' for p in scoped),
            'native_catalog_unchanged':bool(catalogs) and native_buttons(catalogs[-1],o.pet)==native,
            'native_saved_unchanged':{k:persisted[k] for k in PET_KEYS}==baseline['pet'] and persisted['Reactstate']==3,
            'public_bar_unchanged':public_bar(after['probe'])==baseline['public_bar'],
            'public_owned_pet':after['probe'].get('pet_guid')==expected_guid(o.pet)
                and after['probe'].get('owner_guid')==t.guid,
            'owned_native_pet':o.present(),'owned_online':character(5,2)['online']==1,
            'public_idle':after['probe'].get('pet_speed')==after['probe'].get('player_speed')==0,
            'ui_clean':after['ui_clean']}
        return {'status':'owned_manual_spell_shape_capture_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'modern_requests':modern,'native_requests':forwarded,'public':after,
                'native_buttons':native,'observed_button':row,'qualification_added':False,'wire_layout_inferred':False}}
    require(t.step('diagnostic.pet_manual_blood_pact','Capture one observed stock Blood Pact left-click and require unchanged native state.',
        {'cast':{'kind':'click','value':point,'button':1,'hold':.4,'description':'Left-click the observed stock Blood Pact button5 once.'}},
        outcome,diagnostic_action='cast'),'owned_manual_spell_shape_capture_pass')


def suite(t,preparation,entry):
    restored_suite(t,preparation,entry,sequence=((3,'fixture.pet_assist_restore'),),capture=capture)
    t.receipt.update(phase='owned_manual_spell_shape_capture_complete',qualified_scope=
        'One idle owned Imp stock Blood Pact click, actual request body, unchanged native state, '
        'supported Assist readback and full original restoration. Diagnostic only; no manual spell qualification.')


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
