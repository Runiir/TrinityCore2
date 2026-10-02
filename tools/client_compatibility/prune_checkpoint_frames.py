"""Remove raw interaction frames only after a verified DVC checkpoint."""
import argparse,json,subprocess,time
from pathlib import Path
from . import lab_runtime as lab


def prune(directory):
    directory=directory.resolve()
    if directory.parent!=lab.ROOT/'evidence':raise ValueError('require a private lab evidence batch')
    receipt=json.loads((directory/'checkpoint_receipt.json').read_text())
    if receipt.get('cloud_verified') is not True:raise RuntimeError('checkpoint remote has not been verified')
    report_path=directory/'frame_pruning.json'
    if report_path.exists():raise RuntimeError('frame pruning already recorded')
    archive=lab.REPO/receipt['file'];pointer=str(archive.relative_to(lab.REPO))+'.dvc'
    if archive.parent!=lab.REPO/'artifacts/client_harness' or not archive.name.startswith('442_'):
        raise ValueError('unsupported checkpoint archive')
    if not archive.is_file() or archive.is_symlink() or lab.sha256(archive)!=receipt['sha256']:
        raise RuntimeError('verified checkpoint archive is unavailable or changed')
    cloud=json.loads(subprocess.check_output(['dvc','status','--cloud','--json',pointer],cwd=lab.REPO,text=True))
    if cloud:raise RuntimeError('checkpoint is not synchronized with its remote')
    frames=[]
    for record in receipt['file_manifest']:
        path=lab.ROOT/record['path']
        if path.suffix.lower()!='.png' or not path.is_relative_to(directory):continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=record['bytes'] or lab.sha256(path)!=record['sha256']:
            raise RuntimeError('raw frame differs from checkpoint: '+str(path))
        frames.append((path,record))
    report={'schema':'client442_frame_pruning_v1','started_at':time.time(),'checkpoint':pointer,
            'archive_sha256':receipt['sha256'],'remote_verified':True,'removed_frames':[],
            'bytes':sum(record['bytes'] for _,record in frames)}
    try:
        for path,record in frames:
            path.unlink();report['removed_frames'].append(record)
    finally:
        report['finished_at']=time.time();lab.private_write(report_path,json.dumps(report,indent=2)+'\n')
    print(json.dumps({'frames':len(frames),'bytes':report['bytes'],'receipt':str(report_path)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    prune(parser.parse_args().directory)
