"""Review the actual closed disposable Abandon and reject unsafe variants."""
import argparse,copy,hashlib,json,time
from pathlib import Path
from . import lab_runtime as lab
from .hunter_abandon_evidence import proof,CLOSURE
from .observation.journal import entries
from .review_native_feedback_checkpoint import packet_key
from .world.objects import INDEX


def review(directory,output):
    directory=directory.resolve();output=output.resolve()
    if directory.parent!=lab.ROOT/'evidence' or output.parent!=directory or output.exists():
        raise ValueError('requires a new local review inside the owned open batch')
    data={str(p.relative_to(directory)):json.loads(p.read_text()) for p in directory.rglob('*.json')}
    digests={}
    for p in directory.rglob('*'):
        if p.is_file() and p.suffix in ('.json','.png'):
            with p.open('rb') as f:digests[str(p.relative_to(directory))]=hashlib.file_digest(f,'sha256').hexdigest()
    a='hunter_abandon_confirm01/episode.json';s='hunter_abandon_dialog01/episode.json';p='hunter_abandon_park01/episode.json'
    e=data[a];session=e['native_session'];since=e['started_at'];until=e['finished_at']
    select=lambda rows,sessions:{packet_key(r) for r in rows if r.get('session') in sessions and since<=r.get('time',0)<=until and r.get('name')=='CMSG_PET_ABANDON'}
    packets=select(entries(lab.ROOT/'evidence/owned_pet_abandon_packets.jsonl'),{session})
    entry=data['hunter_abandon_entry01/episode.json'];journal=lab.ROOT/'logs/modern_world.jsonl'
    instances={r['session'] for r in entries(journal) if r.get('event')=='instance_authenticated' and
        r.get('account_id')==entry['actor']['account_id'] and entry['started_at']<=r.get('time',0)<=entry['finished_at']}
    if len(instances)!=1:raise RuntimeError('fresh owned Abandon instance attribution is absent or ambiguous')
    events=select(entries(journal),{session}|instances);outcome=proof(data,digests,packets,events)
    review_key=str(Path(e['screen_review']['path']).relative_to(directory))
    d='single_scout_deploy01/deployment.json'
    mutations={
        'failed_confirmation':(a,['completed'],False),'primary_present':(CLOSURE,['checks','primary_intentionally_stopped'],False),
        'named_pet_changed':(a,['retained_pet_after',0,'name'],'Wolf'),
        'named_pet_active':(a,['retained_pet_after',0,'active'],1),
        'foreign_pet_number':(a,['native_pet_before','fields',str(INDEX['UNIT_FIELD_PETNUMBER'])],4),
        'native_pet_not_removed':(a,['native_removed'],[]),'public_pet_still_present':(a,['public_pet','exists'],True),
        'owner_money_changed':(p,['retained_class_fixture','money'],0),
        'owner_pose_changed':(p,['retained_class_fixture','position_x'],0),
        'cancel_point':(a,['ordinary_input','value'],[701,192]),'foreign_popup':(s,['state','pet_popups',0,'which'],'RENAME_PET'),
        'model_controller':(a,['model'],'laya'),'unreviewed_control':(review_key,['reviewed'],False),
        'foreign_runtime':(a,['runtime','worldserver','pid'],0),'early_logout':(p,['started_at'],e['started_at']-1),
        'unbounded_probe':(a,['capture_config','expires_at'],e['capture_config']['created_at']+91),
        'armed_probe':(a,['capture_disarmed'],False),'missing_native_request':(a,['capture_packets'],e['capture_packets'][:1]),
        'unfinished_deployment':(d,['completed'],False),'primary_restarted':(d,['primary_stopped'],False),
        'changed_primary_saved_state':('primary_user_stop_source01.json',['after','native','online'],1),
        'lua_error':(a,['state','lua_errors'],['unsafe local variant'])}
    guards={}
    for name,(key,path,value) in mutations.items():
        changed=copy.deepcopy(data);target=changed[key]
        for part in path[:-1]:target=target[part]
        target[path[-1]]=value
        try:proof(changed,digests,packets,events)
        except RuntimeError:guards[name]=True
        else:raise RuntimeError('unsafe disposable Abandon variant admitted: '+name)
    for name,raw,metadata in [('raw_packet_missing',set(),events),('extra_request',packets,events|{('foreign',0,'from_client','CMSG_PET_ABANDON',None)})]:
        try:proof(data,digests,raw,metadata)
        except RuntimeError:guards[name]=True
        else:raise RuntimeError('unsafe Abandon tracking variant admitted: '+name)
    result={'schema':'client442_owned_abandon_local_review_v1','reviewed_at':time.time(),
        'actual_remote_verified':False,'inventory_admitted':False,'proof':outcome,
        'unsafe_variant_rejections':guards,'guards_passed':len(guards),'input_sent':False}
    lab.private_write(output,json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();review(a.directory,a.output)
