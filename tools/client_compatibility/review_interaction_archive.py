"""Verify selected immutable receipts and attributed game images in one archive pass."""
import argparse,copy,hashlib,json,posixpath,subprocess,tarfile,time
from pathlib import Path,PurePosixPath
from . import lab_runtime as lab


def frame_members(value,parent,batch,manifest):
    found={}
    def visit(item,base=parent):
        if isinstance(item,list):
            for row in item:visit(row,base)
        elif isinstance(item,dict):
            # Reviewed lobby frames are copied into later receipts. Their file
            # names remain relative to the hash-bound source review JSON.
            source=item.get('path')
            if 'frame' in item and isinstance(source,str) and source.endswith('.json'):
                source_path=Path(source)
                if source_path.is_absolute():
                    try:source=str(source_path.relative_to(lab.ROOT))
                    except ValueError:raise ValueError('referenced frame review is outside the owned lab')
                else:source=str(PurePosixPath(base)/source)
                if (not source.startswith(batch+'/') or source not in manifest or
                        item.get('sha256')!=manifest[source]['sha256']):
                    raise ValueError('referenced frame review is absent or changed')
                base=str(PurePosixPath(source).parent)
            name=item.get('file')
            if isinstance(name,str) and name.lower().endswith(('.png','.jpg','.jpeg')):
                path=Path(name);candidates=[]
                if path.is_absolute():
                    try:candidates=[str(path.relative_to(lab.ROOT))]
                    except ValueError:raise ValueError('frame is outside the owned lab')
                else:
                    if '..' in path.parts:
                        # A sibling lobby review can retain its original frame.
                        # Resolve exactly that path, with no basename fallback.
                        sibling=posixpath.normpath(str(PurePosixPath(base)/name))
                        if not sibling.startswith(batch+'/'):
                            raise ValueError('frame path escapes its batch')
                        if sibling not in manifest or not item.get('sha256'):
                            raise ValueError('sibling frame is absent or lacks a digest')
                        candidates=[sibling]
                    else:candidates=[str(PurePosixPath(base)/name),str(PurePosixPath(batch)/name),name]
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
            for child in item.values():visit(child,base)
    visit(value);return found


def historical_baseline(value,reviews):
    """Resolve a copied failure baseline only through its bound prior archive review."""
    if not isinstance(value,dict):return value,[]
    reference=value.get('original_failure',{})
    baseline=value.get('spell_baseline',{})
    if not reviews or not reference or not isinstance(baseline.get('frame'),dict):return value,[]
    source=Path(reference.get('path','')).resolve()
    if (source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence') or source.is_symlink() or
        not source.is_file() or lab.sha256(source)!=reference.get('sha256')):
        raise ValueError('historical baseline source is absent or changed')
    previous=json.loads(source.read_text())
    if previous.get('completed') is not False or not previous.get('finished_at') or not previous.get('failure'):
        raise ValueError('historical baseline requires a closed failure')
    if baseline!=previous.get('spell_baseline'):raise ValueError('copied historical baseline differs')
    frame=baseline['frame'];name=frame.get('file','');image=(source.parent/name).resolve()
    if (Path(name).is_absolute() or '..' in Path(name).parts or not image.is_relative_to(source.parent) or
        not name.endswith('.png') or not isinstance(frame.get('sha256'),str)):
        raise ValueError('historical baseline frame identity is invalid')
    receipt_member=str(source.relative_to(lab.ROOT));frame_member=str(image.relative_to(lab.ROOT))
    matches=[]
    for path in reviews:
        path=path.resolve()
        if not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink() or not path.is_file():
            raise ValueError('historical archive review is outside the owned lab')
        digest=lab.sha256(path)
        if not any(r.get('path')==str(path) and r.get('sha256')==digest
            for r in value.get('bridge_recovery_sources',[])):continue
        report=json.loads(path.read_text());pointer=report.get('pointer','');target=PurePosixPath(pointer)
        if (report.get('schema')!='client442_qualification_archive_review_v1' or
            report.get('cloud_verified') is not True or target.is_absolute() or '..' in target.parts or
            not pointer.startswith('artifacts/client_harness/442_') or not pointer.endswith('.tar.gz.dvc') or
            not (lab.REPO/pointer).is_file()):continue
        old_receipts=[r for r in report.get('receipts',[]) if r.get('member')==receipt_member and
            r.get('sha256')==reference['sha256'] and r.get('verified') is True]
        old_frames=[r for r in report.get('frames',[]) if r.get('member')==frame_member and
            r.get('sha256')==frame['sha256'] and r.get('verified') is True]
        if len(old_receipts)==len(old_frames)==1:
            matches.append({'pointer':pointer,'archive_sha256':report['archive_sha256'],
                'source_receipt':reference,'member':frame_member,'sha256':frame['sha256'],
                'review':{'path':str(path),'sha256':digest},'verified':True})
    if len(matches)!=1:raise ValueError('historical frame has no unique bound verified archive review')
    local=copy.deepcopy(value);del local['spell_baseline']['frame']
    return local,matches


def review(directory,names,output,historical_reviews=()):
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
    batch=str(directory.relative_to(lab.ROOT));receipts={};frames={};historical=[]
    for name in names:
        local=(directory/name).resolve()
        if not local.is_relative_to(directory) or local.suffix!='.json' or local.is_symlink():raise ValueError('require JSON receipts within the batch')
        member=str(local.relative_to(lab.ROOT))
        if member not in manifest or lab.sha256(local)!=manifest[member]['sha256']:
            raise RuntimeError('selected receipt differs from the checkpoint: '+member)
        receipts[member]=manifest[member]['sha256']
        value,prior=historical_baseline(json.loads(local.read_text()),historical_reviews);historical.extend(prior)
        frames.update(frame_members(value,str(PurePosixPath(member).parent),batch,manifest))
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
        'review_tool_sha256':lab.sha256(Path(__file__)),
        'pointer':pointer,'archive_sha256':checkpoint['sha256'],'cloud_verified':True,
        'receipts':[{'member':p,'sha256':h,'verified':True} for p,h in sorted(receipts.items())],
        'frames':[{'member':p,'sha256':h,'verified':True} for p,h in sorted(frames.items())],
        'historical_frames':historical,
        'limits':'Archive/frame integrity only. Gameplay qualification still requires scoped successful outcomes and visual review.'}
    lab.private_write(output,json.dumps(report,indent=2)+'\n')
    print(json.dumps({'receipts':len(receipts),'frames':len(frames),'output':str(output)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--receipt',action='append',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--historical-review',action='append',type=Path,default=[])
    a=p.parse_args();review(a.directory,a.receipt,a.output,a.historical_review)
