"""Verify selected immutable receipts and attributed game images in one archive pass."""
import argparse,hashlib,json,subprocess,tarfile,time
from pathlib import Path,PurePosixPath
from . import lab_runtime as lab


def frame_members(value,parent,batch,manifest):
    found={}
    def visit(item):
        if isinstance(item,list):
            for row in item:visit(row)
        elif isinstance(item,dict):
            name=item.get('file')
            if isinstance(name,str) and name.lower().endswith(('.png','.jpg','.jpeg')):
                path=Path(name);candidates=[]
                if path.is_absolute():
                    try:candidates=[str(path.relative_to(lab.ROOT))]
                    except ValueError:raise ValueError('frame is outside the owned lab')
                else:
                    if '..' in path.parts:raise ValueError('frame path escapes its receipt')
                    candidates=[str(PurePosixPath(parent)/name),str(PurePosixPath(batch)/name),name]
                matches=[p for p in dict.fromkeys(candidates) if p in manifest]
                if not matches:
                    matches=[p for p,r in manifest.items() if p.startswith(batch+'/') and
                        PurePosixPath(p).name==path.name and (not item.get('sha256') or r['sha256']==item['sha256'])]
                if len(matches)!=1:raise ValueError('frame attribution is absent or ambiguous: '+name)
                member=matches[0]
                if not member.startswith(batch+'/'):raise ValueError('frame belongs to a different batch')
                if item.get('sha256') and item['sha256']!=manifest[member]['sha256']:
                    raise ValueError('frame digest differs from the checkpoint: '+member)
                found[member]=manifest[member]['sha256']
            for child in item.values():visit(child)
    visit(value);return found


def review(directory,names,output):
    directory=directory.resolve();output=output.resolve()
    if directory.parent!=lab.ROOT/'evidence' or not output.is_relative_to(lab.ROOT/'evidence') or output.is_relative_to(directory) or output.exists():
        raise ValueError('require an owned batch and a new review outside its immutable archive')
    checkpoint=json.loads((directory/'checkpoint_receipt.json').read_text())
    archive=lab.REPO/checkpoint['file'];pointer=checkpoint['file']+'.dvc'
    if archive.parent!=lab.REPO/'artifacts/client_harness' or archive.is_symlink() or not checkpoint.get('cloud_verified') or lab.sha256(archive)!=checkpoint['sha256']:
        raise RuntimeError('checkpoint archive is absent, changed or unverified')
    if json.loads(subprocess.check_output(['dvc','status','--cloud','--json',pointer],cwd=lab.REPO,text=True)):
        raise RuntimeError('checkpoint remote is not synchronized')
    records=checkpoint['file_manifest'];manifest={r['path']:r for r in records}
    if len(manifest)!=len(records):raise ValueError('duplicate checkpoint manifest paths')
    batch=str(directory.relative_to(lab.ROOT));receipts={};frames={}
    for name in names:
        local=(directory/name).resolve()
        if not local.is_relative_to(directory) or local.suffix!='.json' or local.is_symlink():raise ValueError('require JSON receipts within the batch')
        member=str(local.relative_to(lab.ROOT))
        if member not in manifest or lab.sha256(local)!=manifest[member]['sha256']:
            raise RuntimeError('selected receipt differs from the checkpoint: '+member)
        receipts[member]=manifest[member]['sha256']
        frames.update(frame_members(json.loads(local.read_text()),str(PurePosixPath(member).parent),batch,manifest))
    selected={**receipts,**frames};seen=set()
    with tarfile.open(archive,'r|gz') as tar:
        for member in tar:
            if member.name not in selected:continue
            if member.name in seen or not member.isfile():raise RuntimeError('archive repeats or changes a selected member')
            with tar.extractfile(member) as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
            if digest!=selected[member.name]:raise RuntimeError('archive selected-member digest mismatch: '+member.name)
            seen.add(member.name)
    if seen!=set(selected):raise RuntimeError('archive is missing selected evidence')
    report={'schema':'client442_qualification_archive_review_v1','reviewed_at':time.time(),
        'pointer':pointer,'archive_sha256':checkpoint['sha256'],'cloud_verified':True,
        'receipts':[{'member':p,'sha256':h,'verified':True} for p,h in sorted(receipts.items())],
        'frames':[{'member':p,'sha256':h,'verified':True} for p,h in sorted(frames.items())],
        'limits':'Archive/frame integrity only. Gameplay qualification still requires scoped successful outcomes and visual review.'}
    lab.private_write(output,json.dumps(report,indent=2)+'\n')
    print(json.dumps({'receipts':len(receipts),'frames':len(frames),'output':str(output)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--receipt',action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();review(a.directory,a.receipt,a.output)
