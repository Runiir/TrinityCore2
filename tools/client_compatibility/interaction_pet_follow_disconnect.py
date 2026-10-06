"""Attribute the rejected owned Follow request and restore offline registration."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,character,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_pet_control_training import protected
from .interaction_pet_follow_capture import follow_request
from .interaction_bridge_deploy import shot
from .observation.journal import entries
from .world.gameobjects import modern_guid


def proof(failed,entry,packets,events):
    session=failed['native_session'];start=failed['follow_started_at'];end=failed['finished_at']
    events=[e for e in events if entry['started_at']<=e.get('time',0)<=end and e.get('event') in
        ('instance_authenticated','world_connection_closed','native_stream_closed')]
    rows=[p for p in packets if p.get('session')==session and start<=p.get('time',0)<=end and
        p.get('name') in ('CMSG_PET_ACTION','CMSG_PET_ABANDON')]
    if len(rows)!=1 or rows[0].get('name')!='CMSG_PET_ACTION' or rows[0].get('direction')!='from_client':
        raise RuntimeError('requires one rejected client Follow and no native command or abandonment')
    packet=rows[0];decoded=follow_request(packet);pet=failed['native_pet_before']
    if (decoded['guid']!=list(modern_guid(pet['guid'],pet['map'])) or decoded['word']!=0x03800001 or
        decoded['target']!=[0,0] or decoded['position']!=[0.,0.,0.]):
        raise RuntimeError('rejected Follow shape or owned pet differs')
    closes=[e for e in events if e.get('event')=='world_connection_closed' and
        e.get('error')=='unsupported pet action shape' and packet['time']<=e.get('time',0)<=packet['time']+1]
    if len(closes)!=1:raise RuntimeError('requires the unique immediate pet-action shape rejection')
    close=closes[0];instance=close['session']
    authenticated=[e for e in events if e.get('event')=='instance_authenticated' and
        e.get('session')==instance and e.get('account_id')==2 and
        entry['started_at']<=e.get('time',0)<=entry['finished_at']]
    canceled=[e for e in events if e.get('session')==session and
        e.get('event') in ('world_connection_closed','native_stream_closed') and
        e.get('error','').startswith('Operation canceled [system:125') and
        close['time']<=e.get('time',0)<=close['time']+1]
    if len(authenticated)!=1 or sorted(e['event'] for e in canceled)!=['native_stream_closed','world_connection_closed']:
        raise RuntimeError('owned instance authentication or native cancellation differs')
    return {'client_request':packet,'decoded':decoded,'authenticated':authenticated[0],
        'instance_closed':close,'native_canceled':canceled,'native_command_sent':False}


def recover(t,preparation,failed_path):
    old=prepared(t,preparation);failed_path=failed_path.resolve()
    if failed_path.name!='episode.json' or not failed_path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires the private owned closed Follow failure')
    failed=json.loads(failed_path.read_text());cases=failed.get('cases',[])
    if (t.fixture['guid']!=5 or failed.get('completed') is not False or not failed.get('finished_at') or
        failed.get('failure')!='RuntimeError: UI observation did not become decodable' or
        failed.get('actor')!=t.fixture or failed.get('runtime')!=t.receipt['runtime'] or
        failed.get('fixture_source',{}).get('sha256')!=lab.sha256(preparation) or
        len(cases)!=1 or cases[0].get('id')!='diagnostic.pet_follow.request' or
        cases[0].get('status')!='infrastructure_failure' or
        cases[0].get('input',{}).get('value')!='/petfollow'):
        raise RuntimeError('closed failed Follow trial differs')
    sources=failed['sources'];entry,probe=[closed(Path(s['path'])) for s in sources]
    if (len(sources)!=2 or any(lab.sha256(Path(s['path']))!=s['sha256'] for s in sources) or
        any(d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] for d in (entry,probe)) or
        entry.get('native_session')!=failed['native_session'] or entry.get('phase')!='owned_class_entered' or
        not probe.get('native_control_demon_known')):
        raise RuntimeError('closed owned entry or trained control source differs')
    p=proof(failed,entry,entries(lab.ROOT/'evidence/world_packets.jsonl'),
        entries(lab.ROOT/'logs/modern_world.jsonl'))
    row=character(5,2);current_saved=saved(5);current_pets=pets(5)
    natural={'online','totaltime','leveltime','logout_time','rest_bonus','latency'}
    checks=protected(old)
    checks.update(class_offline=row['online']==0,saved_rows=current_saved==entry['entered_saved'],
        stable_character={k:v for k,v in row.items() if k not in natural}==
            {k:v for k,v in entry['entered_native'].items() if k not in natural},
        retained_pet=[{k:v for k,v in r.items() if k!='savetime'} for r in current_pets]==
            [{k:v for k,v in r.items() if k!='savetime'} for r in failed['retained_pet_before']])
    t.receipt.update(failed_follow_source={'path':str(failed_path),'sha256':lab.sha256(failed_path)},
        sources=sources,follow_disconnect_proof=p,recovery_checks=checks,input_sent=False,
        retained_class_fixture=row,retained_class_saved=current_saved,retained_class_pets=current_pets,
        qualified_scope='Read-only failed Follow attribution and offline registration recovery. '
            'Whole Follow trial remains failed, restoration incomplete, and no gameplay qualification is added.')
    t.persist()
    if not all(checks.values()):raise RuntimeError('offline class state or protected originals differ')
    if actors.register(2)!=old['origin_actor']:raise RuntimeError('original registration differs')
    t.receipt.update(checks={k:checks[k] for k in
        ('original_character','original_saved_rows','native_worldserver','class_offline')},
        completed=True,phase='await_original_selection_review',frame=shot(t.out/'origin_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','failed-follow','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:recover(t,a.preparation,a.failed_follow)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
