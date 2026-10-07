"""Exercise admission boundaries against the actual closed local repeat receipts."""
import argparse,copy,json,time
from pathlib import Path
from . import lab_runtime as lab
from .review_native_feedback_checkpoint import proof,packet_key


def run(directory,output):
    data={str(p.relative_to(directory)):json.loads(p.read_text()) for p in directory.rglob('*.json')}
    names=['primary_range_error01/episode.json','primary_range_error02/episode.json']
    packets={packet_key(p) for n in names for p in data[n]['packets']}
    accepted=proof(data,packets,'repeat');results={'whole_accepted':True}
    variants={
        'failed_range':lambda d:d[names[1]].update(completed=False,failure='retained failed attempt'),
        'missing_native_error':lambda d:d[names[1]].update(error_pairs=[]),
        'stale_stock_error':lambda d:d[names[1]]['cases'][0]['before'].update(errors=d[names[1]]['public_errors']),
        'wrong_modern_reason':lambda d:d[names[1]]['error_pairs'][0]['client'].update(body='20'),
        'different_native_epoch':lambda d:d[names[1]]['runtime']['worldserver'].update(pid=0),
        'missing_normal_parking':lambda d:d['primary_combat_final_park01/episode.json'].update(completed=False),
        'wrong_attack_target':lambda d:next(p for p in d[names[1]]['packets'] if
            p['name']=='CMSG_ATTACK_SWING' and p['direction']=='to_native').update(body='0000000000000000')}
    for name,mutate in variants.items():
        changed=copy.deepcopy(data);mutate(changed)
        try:proof(changed,packets,'repeat')
        except (RuntimeError,ValueError,KeyError):results[name]=True
        else:raise RuntimeError('invalid repeat receipt was admitted: '+name)
    try:proof(data,set(),'repeat')
    except RuntimeError:results['missing_archive_packets']=True
    else:raise RuntimeError('missing remote packet tracking was admitted')
    report={'schema':'client442_native_feedback_admission_guards_v1','checked_at':time.time(),
        'checks':results,'source_episode_sha256':{n:lab.sha256(directory/n) for n in names},'accepted':accepted}
    lab.private_write(output,json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.directory,a.output)
