"""Verify captured stock reaction modes with real native catalogs and saved mode."""
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
from .interaction_spellbook_recon import resources
from .interaction_ground_movement import position
from .interaction_sit_stand import pose,afk
from .interaction_actionbar_pages import detail
from .interaction_trial import binding_key
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX
from .pet_command_evidence import command_checks
from .pet_react_evidence import mode_button,info_pairs,readback_checks


def public_bar(probe):
    return [{k:r.get(k) for k in ('slot','name','spell_id','active','autocast_allowed','autocast_enabled')}
        for r in probe['actions']]


def mode(t,o,wanted,label):
    control=read(t,label+'_control');row,point=mode_button(control['probe'],wanted)
    if control['probe'].get('pet_guid')!=expected_guid(o.pet):raise RuntimeError('pet button owner changed')
    action=({'kind':'chat','value':'/petpassive','description':'Use the captured stock secure Passive command.'} if wanted==0 else
        {'kind':'click','value':point,'hold':.4,'description':f"Click the observed stock {row['name']} button{row['slot']}."})
    since=time.time();t.receipt[label+'_started_at']=since;t.persist()
    def outcome(b,a,s):
        reload_since=time.time();t.execute({'kind':'chat','value':'/reload'});o.poll()
        sample=read(t,label+'_native_refreshed');o.poll();catalogs=[c for c in o.catalogs if c['guid']==o.pet['guid']
            and c['packet']['time']>=reload_since]
        requests=[p for p in o.requests if p['time']>=since]
        queries=info_pairs(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,reload_since,time.time())
        accepted_position=position(5);deadline=time.monotonic()+5;samples=[]
        while True:
            persisted=retained_imp(t.fixture,pets(5));samples.append({'time':time.time(),'id':persisted['id'],
                'Reactstate':persisted['Reactstate'],'input_replayed':False})
            if persisted['Reactstate']==wanted or time.monotonic()>deadline:break
            time.sleep(.2)
        catalog=catalogs[-1] if catalogs else None;checks=command_checks(requests,o.pet,wanted,action_type=6)
        checks.update(readback_checks(catalog,o.pet,wanted,queries,sample,persisted))
        checks.update(owned_native_pet=o.present(),native_owner_unchanged=pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')==5,
            native_pet_number=o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])==2,
            owner_position=accepted_position==t.receipt['baseline']['position'])
        return {'status':'owned_native_react_mode_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'command_requests':requests,'reload_started_at':reload_since,'native_catalogs':catalogs,
                'native_info_queries':queries,'public':sample,'persisted_react':persisted['Reactstate'],
                'persistence_settling':samples,'owner_position':accepted_position,'observed_button':row}}
    require(t.step(label,'Set a stock pet reaction mode and verify real native catalog, saved mode and public selection.',
        {'mode':action},outcome,diagnostic_action='mode'),'owned_native_react_mode_pass')


def suite(t,preparation,entry,*,sequence=((0,'pets.passive'),(3,'pets.assist')),capture=None):
    diagnostic=sequence==((3,'fixture.pet_assist_restore'),) and callable(capture)
    if not diagnostic and (capture is not None or sequence not in (
            ((0,'pets.passive'),(3,'pets.assist')),((1,'pets.defensive'),(3,'fixture.pet_assist_restore')))):
        raise ValueError('requires an exact captured mode lifecycle ending in original Assist')
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session'];e=entry_source(t,entry,session,preparation)
    o=FollowPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll();identity=retained_imp(t.fixture,pets(5))
    sample=read(t,'react_native_baseline');catalogs=[c for c in o.catalogs if o.pet and c['guid']==o.pet['guid']]
    if (t.fixture['guid']!=5 or not o.present() or not catalogs or catalogs[-1]['react']!=3 or catalogs[-1]['command']!=1
        or identity['Reactstate']!=3 or not active_mode(sample['probe'],'PET_MODE_ASSIST')
        or sample['probe'].get('pet_guid')!=expected_guid(o.pet) or pair(o.player,'UNIT_FIELD_TARGET')!=0
        or resources(inventory)!=e['resources'] or saved(5)!=e['entered_saved'] or not all(protected(old).values())):
        raise RuntimeError('requires the unchanged native trained Assist baseline')
    baseline={'resources':resources(inventory),'saved':saved(5),'position':position(5),'vitals':vitals(o),
        'pet':{k:identity[k] for k in PET_KEYS},'react':3,'pose':pose(inventory),'afk':afk(inventory),
        'money':character(5,2)['money'],'public_bar':public_bar(sample['probe'])}
    t.receipt.update(baseline=baseline,native_session=session,native_pet=o.pet,native_catalog=catalogs[-1],
        sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in (preparation,entry)],qualification_added=False)
    t.persist();assist_complete=False
    try:
        if diagnostic:capture(t,o)
        for wanted,label in sequence:mode(t,o,wanted,label)
        assist_complete=True
    except Exception as error:t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        try:
            if not assist_complete:
                # One restoration attempt, through the real stock button and
                # native readback; the failed whole trial remains excluded.
                mode(t,o,3,'fixture.pet_assist_restore')
        finally:
            t.clean_panels();layout=detail(t,'react_cleanup_pose_binding')
            if pose(inventory)['stand']!=baseline['pose']['stand']:
                t.execute({'kind':'key','value':binding_key(layout['keys']['SITORSTAND'][0]),'hold':.4})
            if afk(inventory)!=baseline['afk']:t.execute({'kind':'chat','value':'/afk'})
            t.execute({'kind':'hover','value':[1000,360]});sample=read(t,'react_whole_restored')
            state,frame=t.observe('react_whole_complete');o.poll();accepted_position=position(5);identity=retained_imp(t.fixture,pets(5))
            checks={'resources':resources(inventory)==baseline['resources'],'saved':saved(5)==baseline['saved'],
                'position':accepted_position==baseline['position'],'vitals':vitals(o)==baseline['vitals'],
                'retained_pet':{k:identity[k] for k in PET_KEYS}==baseline['pet'],'persisted_assist':identity['Reactstate']==3,
                'pose':pose(inventory)==baseline['pose'],'afk':afk(inventory)==baseline['afk'],
                'money':character(5,2)['money']==baseline['money'],'owned_pet':o.present(),
                'public_assist':active_mode(sample['probe'],'PET_MODE_ASSIST'),
                'public_pet_bar':public_bar(sample['probe'])==baseline['public_bar'],
                'empty_selection':not state['target'].get('exists') and pair(o.player,'UNIT_FIELD_TARGET')==0,
                'public_owner_xy':math.dist(accepted_position[:2],state['world_position'][:2])<.2,
                'panels_closed':not state.get('panels') and not state.get('bags'),
                'ui_clean':sample['ui_clean'],'protected':all(protected(old).values())}
            t.receipt.update(restoration_checks=checks,protected_checks=protected(old),restored_frame=frame,
                restored_public=sample);t.persist()
            if not all(checks.values()):raise RuntimeError('native pet reaction-mode restoration differs')
    t.receipt.update(completed=True,phase='owned_native_react_modes_complete',qualified_scope='One idle trained owned Imp, '
        'captured stock modes '+', '.join(label for _,label in sequence)+', exact owned native commands, actual requested-mode catalogs '
        'on ordinary reload, native persisted Reactstate and public selection, followed by original resources, saved rows, '
        'position, money, pose, pet/bar and protected actors restoration. Combat reaction behavior and other pets/classes remain open.')
    if diagnostic:t.receipt.update(phase='owned_pet_diagnostic_capture_complete',qualified_scope=
        'Diagnostic capture only, followed by supported native Assist readback and whole original-state restoration. '
        'No captured-operation gameplay qualification.')


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
