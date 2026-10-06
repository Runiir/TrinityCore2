"""Capture stock Defensive, keep its native rejection, and restore real Assist."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,character,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_follow_capture import FollowPresence
from .interaction_pet_command_probe import read,expected_guid
from .interaction_pet_control_training import protected
from .interaction_pet_target import pair,retained_imp
from .interaction_pet_dismiss import vitals
from .interaction_pet_react_capture import active_mode
from .interaction_pet_commands import PET_KEYS
from .interaction_pet_react_modes import mode,public_bar
from .interaction_spellbook_recon import resources
from .interaction_ground_movement import position
from .interaction_sit_stand import pose,afk
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import latest
from .pet_defensive_capture_evidence import button,request_checks


def suite(t,preparation,entry):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session'];e=entry_source(t,entry,session,preparation)
    o=FollowPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    pet=retained_imp(t.fixture,pets(5));sample=read(t,'defensive_capture_baseline')
    catalogs=[c for c in o.catalogs if o.pet and c['guid']==o.pet['guid']]
    if (t.fixture['guid']!=5 or not o.present() or not catalogs or catalogs[-1]['react']!=3
        or catalogs[-1]['command']!=1 or pet['Reactstate']!=3
        or not active_mode(sample['probe'],'PET_MODE_ASSIST') or sample['probe'].get('pet_guid')!=expected_guid(o.pet)
        or pair(o.player,'UNIT_FIELD_TARGET')!=0 or resources(inventory)!=e['resources']
        or saved(5)!=e['entered_saved'] or not all(protected(old).values())):
        raise RuntimeError('requires unchanged trained owned native Assist baseline')
    row,point=button(sample['probe'],o.pet)
    baseline={'resources':resources(inventory),'saved':saved(5),'position':position(5),'vitals':vitals(o),
        'pet':{k:pet[k] for k in PET_KEYS},'pose':pose(inventory),'afk':afk(inventory),
        'money':character(5,2)['money'],'public_bar':public_bar(sample['probe'])}
    t.receipt.update(baseline=baseline,native_session=session,native_pet=o.pet,native_catalog=catalogs[-1],
        sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in (preparation,entry)],
        qualification_added=False,observed_button=row);t.persist()
    since=time.time();t.receipt['defensive_started_at']=since;t.persist()
    try:
        def outcome(b,a,s):
            o.poll();requests=[p for p in o.requests if p['time']>=since];checks,decoded=request_checks(requests,o.pet)
            sample=read(t,'defensive_local_selection');native=retained_imp(t.fixture,pets(5))
            rejection=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session
                and r.get('time',0)>=since and r.get('event')=='pet_action_translation_rejected')
            modes=[r for r in sample['probe']['actions'] if r.get('name') in
                ('PET_MODE_PASSIVE','PET_MODE_DEFENSIVE','PET_MODE_ASSIST') and r.get('available') and r.get('is_token')]
            checks.update(healthy_rejection=bool(rejection and rejection.get('error')=='unsupported pet action shape'),
                local_defensive=active_mode(sample['probe'],'PET_MODE_DEFENSIVE'),
                local_other_modes_inactive=len(modes)==3 and all(r.get('active') is False for r in modes
                    if r['name']!='PET_MODE_DEFENSIVE'),native_saved_assist=native['Reactstate']==3,
                owned_native_pet=o.present(),owned_online=character(5,2)['online']==1,
                public_owned_pet=sample['probe'].get('pet_guid')==expected_guid(o.pet),
                public_idle=sample['probe']['pet_speed']==sample['probe']['player_speed']==0,ui_clean=sample['ui_clean'])
            return {'status':'owned_defensive_shape_capture_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'requests':requests,'decoded':decoded,'rejection':rejection,
                    'public':sample,'persisted_react':native['Reactstate'],'qualification_added':False}}
        require(t.step('diagnostic.pet_defensive_capture','Capture the visible stock Defensive request without native admission.',
            {'defensive':{'kind':'click','value':point,'hold':.4,'description':'Click the observed stock Defensive button9 once.'}},
            outcome,diagnostic_action='defensive'),'owned_defensive_shape_capture_pass')
    finally:
        try:mode(t,o,3,'fixture.pet_assist_restore')
        finally:
            t.clean_panels();t.execute({'kind':'hover','value':[1000,360]});sample=read(t,'defensive_capture_restored')
            state,frame=t.observe('defensive_capture_complete');o.poll();accepted=position(5);pet=retained_imp(t.fixture,pets(5))
            checks={'resources':resources(inventory)==baseline['resources'],'saved':saved(5)==baseline['saved'],
                'position':accepted==baseline['position'],'vitals':vitals(o)==baseline['vitals'],
                'retained_pet':{k:pet[k] for k in PET_KEYS}==baseline['pet'],'persisted_assist':pet['Reactstate']==3,
                'pose':pose(inventory)==baseline['pose'],'afk':afk(inventory)==baseline['afk'],
                'money':character(5,2)['money']==baseline['money'],'owned_pet':o.present(),
                'public_assist':active_mode(sample['probe'],'PET_MODE_ASSIST'),
                'public_pet_bar':public_bar(sample['probe'])==baseline['public_bar'],
                'empty_selection':not state['target'].get('exists') and pair(o.player,'UNIT_FIELD_TARGET')==0,
                'public_owner_xy':math.dist(accepted[:2],state['world_position'][:2])<.2,
                'panels_closed':not state.get('panels') and not state.get('bags'),'ui_clean':sample['ui_clean'],
                'protected':all(protected(old).values())}
            t.receipt.update(restoration_checks=checks,protected_checks=protected(old),restored_frame=frame,
                restored_public=sample);t.persist()
            if not all(checks.values()):raise RuntimeError('Defensive capture original restoration differs')
    t.receipt.update(completed=True,phase='owned_defensive_shape_capture_complete',qualified_scope='Diagnostic actual '
        'stock Defensive request and healthy native rejection, then supported stock Assist with real native reload '
        'catalog and persisted mode, and full restoration. No Defensive gameplay qualification.')


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
