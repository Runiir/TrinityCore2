"""Capture observed stock autocast off/on requests; leave native admission unchanged."""
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
from .pet_autocast_capture_evidence import SPELLS,button,native_buttons,request_checks


def capture(t,o):
    baseline=t.receipt['baseline'];native=native_buttons(t.receipt['native_catalog'],o.pet)
    if not all(any(r['slot']==slot and r['spell_id']==spell and r['action_type']==0xc1 for r in native)
        for spell,slot in SPELLS.items()):raise RuntimeError('native autocast baseline is not both enabled captured spells')
    t.receipt['native_autocast_buttons']=native;t.persist()
    for spell in SPELLS:
        for wanted in (False,True):
            label=f'diagnostic.pet_autocast_{spell}_'+('on' if wanted else 'off')
            before=read(t,label+'_control');row,point=button(before['probe'],o.pet,spell,not wanted)
            since=time.time();t.receipt[label+'_started_at']=since;t.persist()
            def outcome(b,a,s):
                after=read(t,label+'_local');o.poll();rows=entries(lab.ROOT/'evidence/world_packets.jsonl')
                checks,modern,forwarded=request_checks(rows,o.session,since,time.time())
                t.receipt.setdefault('autocast_request_captures',[]).append({'label':label,'started_at':since,
                    'spell':spell,'local_wanted':wanted,'modern_requests':modern,'native_requests':forwarded,
                    'public':after,'wire_layout_inferred':False});t.persist()
                # The shape is deliberately opaque until this actual capture is reviewed.
                try:button(after['probe'],o.pet,spell,wanted);checks['public_toggle_control']=True
                except RuntimeError:checks['public_toggle_control']=False
                public=public_bar(after['probe']);expected=public_bar(before['probe'])
                for value in expected:
                    if value.get('spell_id')==spell:value['autocast_enabled']=wanted
                persisted=retained_imp(t.fixture,pets(5));catalogs=[c for c in o.catalogs if c['guid']==o.pet['guid']]
                checks.update(public_exact_local_toggle=public==expected,
                    native_catalog_unchanged=native_buttons(catalogs[-1],o.pet)==native,
                    native_saved_unchanged={k:persisted[k] for k in PET_KEYS}==baseline['pet'] and persisted['Reactstate']==3,
                    owned_native_pet=o.present(),owned_online=character(5,2)['online']==1,
                    public_idle=after['probe'].get('pet_speed')==after['probe'].get('player_speed')==0,
                    ui_clean=after['ui_clean'])
                return {'status':'owned_autocast_shape_capture_pass' if all(checks.values()) else 'client_or_protocol_failure',
                    'oracle':{'checks':checks,'modern_requests':modern,'native_requests':forwarded,
                        'public':after,'native_buttons':native,'persisted_abdata':persisted['abdata'],
                        'observed_button':row,'qualification_added':False,'wire_layout_inferred':False}}
            require(t.step(label,'Capture one observed stock pet autocast switch and verify unchanged native state.',
                {'toggle':{'kind':'click','value':point,'button':3,'hold':.4,
                    'description':f'Right-click observed {row["name"]} button{row["slot"]} once.'}},
                outcome,diagnostic_action='toggle'),'owned_autocast_shape_capture_pass')


def suite(t,preparation,entry):
    restored_suite(t,preparation,entry,sequence=((3,'fixture.pet_assist_restore'),),capture=capture)
    t.receipt.update(phase='owned_autocast_shape_capture_complete',qualified_scope=
        'Diagnostic actual stock Firebolt/Blood Pact autocast off/on wire bodies and local switches, '
        'unchanged native state, supported native Assist reload and whole restoration. No autocast gameplay qualification.')


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
