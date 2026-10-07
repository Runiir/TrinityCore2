"""Check the closed occupied-pair sources before archiving; never admit inventory."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .hunter_pair_evidence import CLOSURE,proof
from .review_native_feedback_checkpoint import packet_key
from .observation.journal import entries


def review(directory,output):
    directory=directory.resolve();output=output.resolve()
    if (directory.parent!=lab.ROOT/'evidence' or output.exists() or
        not output.is_relative_to(directory)):
        raise ValueError('requires new local review inside the private closed pair batch')
    data={};digests={}
    for p in directory.rglob('*'):
        if p.suffix not in ('.json','.png') or not p.is_file():continue
        if p.is_symlink():raise ValueError('pair source must not be a symlink')
        key=str(p.relative_to(directory));digests[key]=lab.sha256(p)
        if p.suffix=='.json':data[key]=json.loads(p.read_text())
    refs=data[CLOSURE]['sources']
    calls=[data[str(Path(refs[i]['path']).relative_to(directory))] for i in (3,5)]
    wanted={packet_key(p) for c in calls for p in c['call_pet_packets']}
    if not 0<len(wanted)<=256:raise RuntimeError('bounded ordinary pair packet set differs')
    packets={packet_key(p) for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if packet_key(p) in wanted}
    outcome=proof(data,digests,packets)
    result={'schema':'client442_owned_pair_local_review_v1','reviewed_at':time.time(),
        'closure':{'path':str(directory/CLOSURE),'sha256':digests[CLOSURE]},
        'actual_remote_verified':False,'inventory_admitted':False,'proof':outcome}
    lab.private_write(output,json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();review(a.directory,a.output)
