"""Restore local Assist through the freshly reviewed stock pet button."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,character,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_follow_capture import FollowPresence,follow_request
from .interaction_pet_command_probe import read,expected_guid
from .interaction_pet_react_capture import active_mode
from .interaction_pet_control_training import protected
from .interaction_pet_target import retained_imp,pair
from .interaction_pet_dismiss import vitals
from .interaction_pet_commands import PET_KEYS
from .interaction_ground_movement import position
from .interaction_sit_stand import pose,afk
from .interaction_spellbook_recon import resources
from .interaction_bridge_deploy import shot
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import latest
from .world.gameobjects import modern_guid


def failed_source(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):raise ValueError('require private failed capture')
    d=json.loads(path.read_text());cases=d.get('cases',[]);checks=d.get('restoration_checks',{})
    if (d.get('completed') or not d.get('finished_at') or d.get('failure')!='RuntimeError: stock react capture restoration differs'
        or d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or len(cases)!=3
        or cases[0].get('id')!='diagnostic.pet_passive_capture' or cases[0].get('status')!='owned_react_request_capture_pass'
        or not all(cases[0]['oracle']['checks'].values()) or any(c['oracle'].get('requests') for c in cases[1:])
        or len(checks)!=14 or checks.get('public_assist') is not False
        or not all(v for k,v in checks.items() if k!='public_assist')):
        raise RuntimeError('failed same-runtime public Assist-only restoration source differs')
    t.receipt['failed_source']={'path':str(path),'sha256':lab.sha256(path)};return d


def baseline(t,path):
    failed=failed_source(t,path);preparation,entry=[Path(s['path']) for s in failed['sources']]
    if any(lab.sha256(Path(s['path']))!=s['sha256'] for s in failed['sources']):raise RuntimeError('capture sources changed')
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session'];e=entry_source(t,entry,session,preparation)
    o=FollowPresence(session,5,e['started_at']).poll();inventory=Inventory(lab.ROOT,session,5).poll()
    if not o.present() or o.pet['guid']!=failed['native_pet']['guid'] or session!=failed['native_session']:
        raise RuntimeError('failed capture owned pet or native session changed')
    t.receipt.update(native_session=session,native_pet=o.pet,baseline=failed['baseline']);return old,failed,o,inventory


def capture(t,path):
    old,failed,o,inventory=baseline(t,path);sample=read(t,'current_local_passive')
    if not active_mode(sample['probe'],'PET_MODE_PASSIVE') or sample['probe'].get('pet_guid')!=expected_guid(o.pet):
        raise RuntimeError('local failed Passive selection changed before read-only capture')
    t.receipt.update(public_before=sample,frame=shot(t.out/'assist_button.png'),completed=True,
        phase='await_owned_assist_button_review',qualified_scope='Read-only failed local pet-mode restoration inspection only.')


def restore(t,path,capture_path,review_path):
    old,failed,o,inventory=baseline(t,path);d=json.loads(capture_path.read_text())
    if (not d.get('completed') or d.get('failure') or not d.get('finished_at')
        or d.get('phase')!='await_owned_assist_button_review' or d.get('actor')!=t.fixture
        or d.get('runtime')!=t.receipt['runtime'] or d.get('failed_source',{}).get('sha256')!=lab.sha256(path)):
        raise RuntimeError('closed read-only Assist button capture differs')
    review=json.loads(review_path.read_text());frame=review.get('frame',{});image=review_path.parent/frame.get('file','')
    m=frame.get('monitor',{});current=owned_input.focus();point=review.get('point',[])
    if (review.get('reviewed') is not True or review.get('control')!='PetActionButton8 Assist'
        or review.get('capture_sha256')!=lab.sha256(capture_path) or frame!=d['frame']
        or not image.resolve().is_relative_to(lab.ROOT/'evidence') or not image.is_file() or lab.sha256(image)!=frame.get('sha256')
        or not 0<=time.time()-image.stat().st_mtime<=120 or not m.get('second_monitor_verified')
        or m.get('pid')!=t.receipt['runtime']['client']['pid'] or m.get('input_isolation',{}).get('actor')!='scout'
        or m.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid']
        or len(point)!=2 or any(type(v) is not int for v in point) or not (460<=point[0]<500 and 635<=point[1]<673)):
        raise RuntimeError('fresh reviewed visible stock Assist button differs')
    sample=read(t,'assist_recovery_before')
    if not active_mode(sample['probe'],'PET_MODE_PASSIVE'):raise RuntimeError('failed local Passive selection changed')
    t.receipt['button_review']={'path':str(review_path),'sha256':lab.sha256(review_path),'frame':frame};t.persist();since=time.time()
    def outcome(b,a,selected):
        o.poll();requests=[p for p in o.requests if p['time']>=since];modern=[p for p in requests if p['direction']=='from_client']
        decoded=follow_request(modern[0]) if len(modern)==1 else None;sample=read(t,'assist_button_result')
        rejected=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==o.session and r.get('time',0)>=since
            and r.get('event')=='pet_action_translation_rejected')
        checks={'reviewed_stock_button':selected=='assist','one_owned_assist_request':bool(decoded and decoded['guid']==
                list(modern_guid(o.pet['guid'],0)) and decoded['word']==0x03000003 and decoded['target']==[0,0]
                and decoded['position']==[0.,0.,0.]),'no_native_command':not any(p['direction']=='to_native' for p in requests),
            'no_abandon':not any(p['name']=='CMSG_PET_ABANDON' for p in requests),
            'healthy_rejection':bool(rejected and rejected.get('error')=='unsupported pet action shape'),
            'public_assist_restored':active_mode(sample['probe'],'PET_MODE_ASSIST'),'owned_pet':o.present(),
            'ui_clean':sample['ui_clean']}
        return {'status':'owned_assist_button_capture_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'requests':requests,'decoded':decoded,'public':sample,'rejection':rejected}}
    require(t.step('diagnostic.pet_assist_button_restore','Click the reviewed stock Assist button once to restore local mode.',
        {'assist':{'kind':'click','value':point,'hold':.4,'description':'Click visible pet Assist button8.'}},outcome,
        diagnostic_action='assist'),'owned_assist_button_capture_pass')
    t.clean_panels();sample=read(t,'assist_recovery_restored');state,frame=t.observe('assist_recovery_complete');o.poll()
    before=failed['baseline'];pet=retained_imp(t.fixture,pets(5));checks={'resources':resources(inventory)==before['resources'],
        'saved':saved(5)==before['saved'],'position':position(5)==before['position'],'vitals':vitals(o)==before['vitals'],
        'retained_pet':{k:pet[k] for k in PET_KEYS}==before['pet'],'pose':pose(inventory)==before['pose'],
        'afk':afk(inventory)==before['afk'],'money':character(5,2)['money']==before['money'],'owned_pet':o.present(),
        'public_assist':active_mode(sample['probe'],'PET_MODE_ASSIST'),'empty_selection':not state['target'].get('exists')
            and pair(o.player,'UNIT_FIELD_TARGET')==0,'panels_closed':not state.get('panels') and not state.get('bags'),
        'ui_clean':sample['ui_clean'],'protected':all(protected(old).values())}
    t.receipt.update(restoration_checks=checks,protected_checks=protected(old),restored_frame=frame,qualification_added=False)
    if not all(checks.values()):raise RuntimeError('actual Assist button recovery restoration differs')
    t.receipt.update(completed=True,phase='owned_assist_button_recovery_complete',qualified_scope='Actual stock Assist button request '
        'and local restoration after the failed unsupported slash command. Native Assist was unchanged throughout; no react qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['capture','restore'])
    for name in ('failed','output'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('capture','review'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.operation=='capture':capture(t,a.failed)
            else:restore(t,a.failed,a.capture,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
