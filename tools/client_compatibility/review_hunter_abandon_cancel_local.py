"""Review the closed cancellation and reject unsafe variants without game input."""
import argparse,copy,hashlib,json,time
from pathlib import Path
from . import lab_runtime as lab
from .hunter_abandon_cancel_evidence import proof,CLOSURE
from .observation.journal import entries
from .world.objects import INDEX


def review(directory,output):
    directory=directory.resolve();output=output.resolve()
    if directory.parent!=lab.ROOT/'evidence' or output.parent!=directory or output.exists():
        raise ValueError('requires a new review in the private open batch')
    data={str(p.relative_to(directory)):json.loads(p.read_text()) for p in directory.rglob('*.json')}
    digests={str(p.relative_to(directory)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
        for p in directory.rglob('*') if p.is_file() and p.suffix in ('.json','.png')}
    s='hunter_abandon_dialog03/episode.json';a='hunter_abandon_cancel02/episode.json'
    p='hunter_abandon_park01/episode.json';stop='primary_user_stop_source01.json'
    review_key=str(Path(data[a]['screen_review']['path']).relative_to(directory))
    events=[e for e in entries(lab.ROOT/'logs/modern_world.jsonl') if e.get('session')==data[a]['native_session'] and
        data[s]['started_at']<=e.get('time',0)<=data[a]['finished_at'] and e.get('name')=='CMSG_PET_ABANDON']
    outcome=proof(data,digests,events)
    mutations={
        'failed_cancel':(a,['completed'],False),
        'primary_present':(CLOSURE,['checks','primary_intentionally_stopped'],False),
        'wrong_native_pet_number':(s,['native_pet','fields',str(INDEX['UNIT_FIELD_PETNUMBER'])],4),
        'foreign_public_pet':(a,['public_pet','guid'],'Pet-foreign'),
        'named_pet_changed':(a,['retained_pet_after',0,'name'],'Wolf'),
        'disposable_foreign_owner':(a,['retained_pet_after',1,'owner'],5),
        'owner_money_changed':(p,['retained_class_fixture','money'],0),
        'owner_pose_changed':(p,['retained_class_fixture','position_x'],0),
        'foreign_popup':(s,['state','pet_popups',0,'which'],'RENAME_PET'),
        'confirmation_point':(a,['ordinary_input','value'],[579,192]),
        'model_controller':(a,['model'],'laya'),
        'unreviewed_control':(review_key,['reviewed'],False),
        'foreign_review_source':(review_key,['source','sha256'],'0'*64),
        'foreign_runtime':(a,['runtime','worldserver','pid'],0),
        'early_logout':(p,['started_at'],data[a]['started_at']-1),
        'changed_primary_saved_state':(stop,['after','native','online'],1),
        'lua_error':(a,['state','lua_errors'],['diagnostic unsafe variant'])}
    guards={}
    for name,(key,path,value) in mutations.items():
        changed=copy.deepcopy(data);target=changed[key]
        for part in path[:-1]:target=target[part]
        target[path[-1]]=value
        try:proof(changed,digests,events)
        except RuntimeError:guards[name]=True
        else:raise RuntimeError('unsafe cancellation variant admitted: '+name)
    try:proof(data,digests,[{'name':'CMSG_PET_ABANDON'}])
    except RuntimeError:guards['abandon_requested']=True
    else:raise RuntimeError('Abandon request admitted as cancellation')
    result={'schema':'client442_owned_abandon_cancel_local_review_v1','reviewed_at':time.time(),
        'actual_remote_verified':False,'inventory_admitted':False,'proof':outcome,
        'unsafe_variant_rejections':guards,'guards_passed':len(guards),'input_sent':False}
    lab.private_write(output,json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();review(a.directory,a.output)
