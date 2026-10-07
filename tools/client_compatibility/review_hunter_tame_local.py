"""Review actual closed Tame journals and reject broken admission variants."""
import argparse,copy,json,time
from pathlib import Path
from . import lab_runtime as lab
from .hunter_tame_evidence import proof,collect,NAMES,CLOSURE,BEFORE,AFTER
from .observation.journal import entries


def review(directory,output):
    directory=directory.resolve();output=output.resolve()
    if directory.parent!=lab.ROOT/'evidence' or not output.is_relative_to(directory) or output.exists():
        raise ValueError('requires a new local review in the open owned batch')
    data={str(p.relative_to(directory)):json.loads(p.read_text()) for p in directory.rglob('*.json')}
    digests={str(p.relative_to(directory)):lab.sha256(p) for p in directory.rglob('*') if p.is_file()}
    tracking={'raw':set(),'packets':set(),'events':[],'instances':set()}
    for source,name in ((lab.ROOT/'logs/modern_world.jsonl','events.jsonl'),
            (lab.ROOT/'evidence/world_packets.jsonl','packets.jsonl'),
            (lab.ROOT/'evidence/owned_tame_request_packets.jsonl','owned_tame_request_packets.jsonl')):
        collect('tracking/'+name,entries(source),data,tracking)
    outcome=proof(data,digests,tracking);guards=[]
    def reject(name,change):
        d=copy.deepcopy(data);h=digests.copy();t=copy.deepcopy(tracking);change(d,h,t)
        try:proof(d,h,t)
        except (RuntimeError,ValueError,KeyError) as error:
            guards.append({'case':name,'rejected':True,'reason':str(error)})
        else:raise RuntimeError('invalid Tame admission variant accepted: '+name)
    for key in (*NAMES.values(),CLOSURE,BEFORE,AFTER):
        reject('whole_failed_'+key,lambda d,h,t,key=key:d[key].update(completed=False))
    reject('missing_actual_channel',lambda d,h,t:t['raw'].pop())
    reject('missing_actual_modern_delivery',lambda d,h,t:t['packets'].clear())
    reject('foreign_physical_instance',lambda d,h,t:t['instances'].clear())
    reject('lost_Harnesswolf',lambda d,h,t:d[AFTER]['public_stable']['pets'].pop(0))
    reject('stale_new_pet_level',lambda d,h,t:d[AFTER]['public_stable']['pets'][-1].update(level=9))
    reject('script_permission_changed',lambda d,h,t:d[NAMES['cast']].update(custom_script_permission='enabled'))
    reject('wrong_closure_source',lambda d,h,t:d[CLOSURE]['sources'][5].update(sha256='0'*64))
    reject('protected_actor_changed',lambda d,h,t:d[CLOSURE]['all_offline_snapshot']['1']['native'].update(money=0))
    reject('pet_not_persisted',lambda d,h,t:d[CLOSURE]['retained_pets'].pop())
    lab.private_write(output,json.dumps({'schema':'client442_owned_tame_local_review_v1',
        'reviewed_at':time.time(),'actual_remote_verified':False,'local_tracking_verified':True,
        'proof':outcome,'guard_count':len(guards),'guards':guards,'all_guards_rejected':True,
        'limits':'Local proof only. Complete actual remote archive verification is required before admission.'},indent=2)+'\n')
    print(json.dumps({'completed':True,'guards':len(guards),'proof':outcome}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();review(a.directory,a.output)
