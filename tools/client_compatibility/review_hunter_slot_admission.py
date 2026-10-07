"""Review the fresh closed slot chain and reject broken admission variants."""
import argparse,copy,json,time
from pathlib import Path
from . import lab_runtime as lab
from .hunter_slot_evidence import proof,NAMES
from .review_native_feedback_checkpoint import packet_key
from .observation.journal import Cursor


def review(directory,output):
    directory=directory.resolve();output=output.resolve()
    if directory.parent!=lab.ROOT/'evidence' or not output.is_relative_to(directory) or output.exists():
        raise RuntimeError('requires a new local review in the owned open batch')
    data={str(p.relative_to(directory)):json.loads(p.read_text()) for p in directory.rglob('*.json')}
    digests={str(p.relative_to(directory)):lab.sha256(p) for p in directory.rglob('*') if p.is_file()}
    keys={k:v+'/episode.json' for k,v in NAMES.items()};e=data[keys['restore']]
    wanted={packet_key(p) for p in e['call_pet_packets']}
    if not 0<len(wanted)<=16:raise RuntimeError('ordinary recovery packet bound differs')
    packets={packet_key(p) for p in Cursor(lab.ROOT/'evidence/world_packets.jsonl').poll() if packet_key(p) in wanted}
    result=proof(data,digests,packets);guards=[]
    def reject(name,change):
        d=copy.deepcopy(data);h=digests.copy();p=packets.copy();change(d,h,p)
        try:proof(d,h,p)
        except (RuntimeError,ValueError,KeyError) as error:
            guards.append({'case':name,'rejected':True,'reason':str(error)})
        else:raise RuntimeError('invalid slot admission variant accepted: '+name)
    for key in ('forward','back','restore','park','close'):
        reject('whole_failed_'+key,lambda d,h,p,key=key:d[keys[key]].update(completed=False))
    reject('wrong_destination',lambda d,h,p:d[keys['forward']].update(destination=6))
    reject('foreign_runtime',lambda d,h,p:d[keys['back']]['runtime']['modern_world'].update(pid=0))
    reject('scripts_enabled',lambda d,h,p:d[keys['forward']].update(custom_script_permission='enabled'))
    reject('wrong_review_image',lambda d,h,p:h.update({NAMES['forward_stage']+'/stable_slot_before.png':'0'*64}))
    reject('stable_pet_still_active',lambda d,h,p:d[keys['forward']]['retained_pet_after'][0].update(active=1))
    reject('renamed_pet',lambda d,h,p:d[keys['restore']]['retained_pet_after'][0].update(name='Wolf'))
    reject('old_tame_metadata_baseline',lambda d,h,p:d[keys['open']]['baseline_pets'][0].update(CreatedBySpell=79597))
    reject('generic_flyout_caption',lambda d,h,p:d[keys['recon']]['call_pet_spell'].update(name='Call Pet'))
    reject('missing_actual_recovery_packet',lambda d,h,p:p.remove(next(iter(p))))
    reject('recovery_from_failed_whole_trial',lambda d,h,p:d[keys['restore']].update(failed_recovery_source={'path':'old'}))
    reject('primary_preservation_failed',lambda d,h,p:d[keys['close']]['checks'].update(actor_1_unchanged=False))
    reject('wrong_closure_source',lambda d,h,p:d[keys['close']]['sources'][1].update(sha256='0'*64))
    def packet_change(d,name,body):
        row=next(p for p in d[keys['forward']]['capture_packets'] if p['name']==name)
        row['body']=body
    reject('wrong_native_update',lambda d,h,p:packet_change(d,'SMSG_PET_SLOT_UPDATED','04000000060000000000000000000000'))
    reject('native_failure_claimed_success',lambda d,h,p:packet_change(d,'SMSG_STABLE_RESULT','01'))
    reject('expired_private_capture',lambda d,h,p:d[keys['forward']]['capture_config'].update(expires_at=0))
    report={'schema':'client442_hunter_slot_local_review_v1','reviewed_at':time.time(),
        'actual_remote_verified':False,'local_tracking_verified':True,'proof':result,
        'guards':guards,'guard_count':len(guards),'all_guards_rejected':all(g['rejected'] for g in guards),
        'limits':'Local fresh slot closure and negative controls only. Full actual remote review is still required.'}
    lab.private_write(output,json.dumps(report,indent=2)+'\n')
    print(json.dumps({'verified':True,'guards':len(guards),'proof':result}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();review(a.directory,a.output)
