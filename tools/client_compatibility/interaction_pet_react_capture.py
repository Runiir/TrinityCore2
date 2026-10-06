"""Capture stock Passive and Assist with healthy rejection and full restoration."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,character,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_follow_capture import FollowPresence,follow_request
from .interaction_pet_command_probe import read,expected_guid
from .interaction_pet_target import pair,retained_imp
from .interaction_pet_control_training import protected
from .interaction_pet_dismiss import vitals
from .interaction_pet_commands import PET_KEYS
from .interaction_spellbook_recon import resources
from .interaction_ground_movement import position
from .interaction_sit_stand import pose,afk
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import latest
from .world.gameobjects import modern_guid


def active_mode(probe,token):
    rows=[r for r in probe.get('actions',[]) if r.get('available') and r.get('is_token') and r.get('name')==token]
    return len(rows)==1 and rows[0].get('active') is True


def capture(t,o,value,token,label):
    since=time.time();guid=o.pet['guid'];t.receipt[label+'_started_at']=since;t.persist()
    def outcome(b,a,s):
        o.poll();requests=[p for p in o.requests if p['time']>=since];sample=read(t,label+'_public')
        modern=[p for p in requests if p['name']=='CMSG_PET_ACTION' and p['direction']=='from_client']
        native=[p for p in requests if p['direction']=='to_native'];decoded=follow_request(modern[0]) if len(modern)==1 else None
        rejected=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==o.session and r.get('time',0)>=since
            and r.get('event')=='pet_action_translation_rejected')
        checks={'one_stock_owned_react_request':bool(decoded and decoded['guid']==list(modern_guid(guid,o.pet['map']))
                and decoded['action_type']==6 and decoded['action_value']==value and decoded['target']==[0,0]
                and decoded['position']==[0.,0.,0.]),'no_native_action':not native,
            'no_abandon':not any(p['name']=='CMSG_PET_ABANDON' for p in requests),
            'healthy_rejection':bool(rejected and rejected.get('error')=='unsupported pet action shape'),
            'owned_native_pet':o.present() and o.pet['guid']==guid,'owned_online':character(5,2)['online']==1,
            'public_mode_selected':active_mode(sample['probe'],token),'public_owned_pet':sample['probe'].get('pet_guid')==expected_guid(o.pet),
            'ui_clean':sample['ui_clean']}
        return {'status':'owned_react_request_capture_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'requests':requests,'decoded':decoded,'rejection':rejected,'public':sample,
                'qualification_added':False}}
    return require(t.step(label,'Capture the exact ordinary stock pet react request while native mode remains unchanged.',
        {'mode':{'kind':'chat','value':'/petpassive' if value==0 else '/petassist','description':'Submit one stock secure pet react command.'}},
        outcome,diagnostic_action='mode'),'owned_react_request_capture_pass')


def suite(t,preparation,entry):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session'];e=entry_source(t,entry,session,preparation)
    o=FollowPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    identity=retained_imp(t.fixture,pets(5));baseline=read(t,'react_baseline');p=baseline['probe']
    catalogs=[c for c in o.catalogs if o.pet and c['guid']==o.pet['guid']]
    if (t.fixture['guid']!=5 or not o.present() or not catalogs or catalogs[-1]['react']!=3 or
        catalogs[-1]['command']!=1 or not active_mode(p,'PET_MODE_ASSIST') or p.get('pet_guid')!=expected_guid(o.pet)
        or pair(o.player,'UNIT_FIELD_TARGET')!=0 or resources(inventory)!=e['resources'] or
        saved(5)!=e['entered_saved'] or not all(protected(old).values())):
        raise RuntimeError('capture requires the unchanged trained Assist/Follow native baseline')
    before={'resources':resources(inventory),'saved':saved(5),'position':position(5),'vitals':vitals(o),
        'pet':{k:identity[k] for k in PET_KEYS},'pose':pose(inventory),'afk':afk(inventory),'money':character(5,2)['money']}
    t.receipt.update(native_session=session,native_pet=o.pet,native_catalog=catalogs[-1],baseline=before,
        sources=[{'path':str(q.resolve()),'sha256':lab.sha256(q)} for q in (preparation,entry)],qualification_added=False)
    t.persist();attempted=False;assist_restored=False
    try:
        attempted=True;capture(t,o,0,'PET_MODE_PASSIVE','diagnostic.pet_passive_capture')
        capture(t,o,3,'PET_MODE_ASSIST','diagnostic.pet_assist_restore');assist_restored=True
    except Exception as error:t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        try:
            if attempted and not assist_restored:capture(t,o,3,'PET_MODE_ASSIST','fixture.pet_assist_restore')
        finally:
            t.clean_panels();sample=read(t,'react_restored');state,frame=t.observe('react_complete');o.poll()
            current=retained_imp(t.fixture,pets(5));checks={'native_resources':resources(inventory)==before['resources'],
                'saved_rows':saved(5)==before['saved'],'position':position(5)==before['position'],
                'native_vitals':vitals(o)==before['vitals'],'retained_pet':{k:current[k] for k in PET_KEYS}==before['pet'],
                'pose':pose(inventory)==before['pose'],'afk':afk(inventory)==before['afk'],
                'money':character(5,2)['money']==before['money'],'owned_native_pet':o.present(),
                'public_assist':active_mode(sample['probe'],'PET_MODE_ASSIST'),
                'empty_selection':not state['target'].get('exists') and pair(o.player,'UNIT_FIELD_TARGET')==0,
                'panels_closed':not state.get('panels') and not state.get('bags'),'ui_clean':sample['ui_clean'],
                'protected':all(protected(old).values())}
            t.receipt.update(restoration_checks=checks,protected_checks=protected(old),restored_frame=frame,
                restored_public=sample);t.persist()
            if not all(checks.values()):raise RuntimeError('stock react capture restoration differs')
    t.receipt.update(completed=True,phase='owned_react_request_capture_complete',
        qualified_scope='Diagnostic actual stock Passive and Assist request shapes, healthy rejection and public local selection '
            'with whole original-state restoration. Native Assist remains unchanged; neither react mode is qualified.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
