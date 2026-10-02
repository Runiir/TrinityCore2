"""Offload immutable, older private packet/event rotations before pruning them."""
import argparse,hashlib,json,re,subprocess,tarfile,time
from pathlib import Path
from dvclive import Live
from . import lab_runtime as lab
from .observation.journal import paths


def checkpoint(before,name,receipt):
    receipt=receipt.resolve()
    if not receipt.is_relative_to(lab.ROOT/'evidence') or receipt.exists():raise ValueError('require a new private receipt')
    if not re.fullmatch(r'442_[A-Za-z0-9_]+',name):raise ValueError('invalid checkpoint name')
    if subprocess.check_output(['git','status','--porcelain'],cwd=lab.REPO,text=True):
        raise RuntimeError('commit cleanup code before checkpointing')
    archive=lab.REPO/'artifacts/client_harness'/(name+'.tar.gz');pointer=str(archive.relative_to(lab.REPO))+'.dvc'
    if archive.exists() or (lab.REPO/pointer).exists():raise RuntimeError('checkpoint name exists')
    selected=[];retained=[]
    for source in [lab.ROOT/'logs/modern_world.jsonl',lab.ROOT/'evidence/world_packets.jsonl']:
        rotations=paths(source)[:-1] if source.exists() else paths(source)
        for file in rotations:
            if file in rotations[-2:] or file.stat().st_mtime>=before:
                retained.append(str(file.relative_to(lab.ROOT)));continue
            if file.is_symlink() or not re.fullmatch(re.escape(source.name)+r'\.part-\d+',file.name):
                raise RuntimeError('unsupported journal rotation')
            # Exact preservation, with authentication/credential bodies forbidden.
            count=0;max_time=0
            with file.open() as handle:
                for line in handle:
                    if not line.endswith('\n'):raise RuntimeError('incomplete immutable rotation')
                    row=json.loads(line);count+=1;max_time=max(max_time,row['time'])
                    if any(k in row for k in ['password','ticket','key','token','credential']):
                        raise RuntimeError('credential field in rotation')
                    if 'body' in row and ('AUTH' in row.get('name','') or 'ENCRYPT' in row.get('name','') or
                        row.get('name')=='SMSG_CONNECT_TO'):
                        raise RuntimeError('authentication body in rotation')
            if max_time>=before:
                retained.append(str(file.relative_to(lab.ROOT)));continue
            selected.append({'path':str(file.relative_to(lab.ROOT)),'bytes':file.stat().st_size,
                'sha256':lab.sha256(file),'rows':count,'last_time':max_time})
    if not selected:raise RuntimeError('no old closed rotations to offload')
    report={'schema':'client442_journal_checkpoint_v1','started_at':time.time(),'before':before,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'files':selected,'retained_rotations':retained,'active_journals_preserved':True,
        'bytes':sum(r['bytes'] for r in selected),'removed':[]}
    staging=lab.ROOT/'run'/name;staging.mkdir(mode=0o700)
    try:
        lab.private_write(staging/'manifest.json',json.dumps(report,indent=2)+'\n')
        with Live(dir=str(staging/'live'),save_dvc_exp=False,dvcyaml=False,report=None) as live:
            live.log_param('code_commit',report['code_commit']);live.log_param('scope','client442_closed_journal_rotations')
            live.log_metric('rotations',len(selected));live.log_metric('raw_bytes',report['bytes']);live.next_step()
        with tarfile.open(archive,'w:gz',compresslevel=3) as tar:
            for row in selected:tar.add(lab.ROOT/row['path'],arcname=row['path'])
            tar.add(staging,arcname='tracking')
        with tarfile.open(archive,'r:gz') as tar:
            for row in selected:
                with tar.extractfile(row['path']) as handle:actual=hashlib.file_digest(handle,'sha256').hexdigest()
                if actual!=row['sha256']:raise RuntimeError('archive verification failed')
        for command in [['dvc','add',str(archive.relative_to(lab.REPO))],['dvc','status',pointer],['dvc','push',pointer]]:
            subprocess.run(command,cwd=lab.REPO,check=True)
        if json.loads(subprocess.check_output(['dvc','status','--cloud','--json',pointer],cwd=lab.REPO,text=True)):
            raise RuntimeError('journal checkpoint remote is not synchronized')
        report.update(pointer=pointer,archive_sha256=lab.sha256(archive),archive_bytes=archive.stat().st_size,remote_verified=True)
        # Validate every source first so a changed source cannot cause partial pruning.
        for row in selected:
            file=lab.ROOT/row['path']
            if file.is_symlink() or file.stat().st_size!=row['bytes'] or lab.sha256(file)!=row['sha256']:
                raise RuntimeError('closed journal changed before pruning')
        for row in selected:
            (lab.ROOT/row['path']).unlink();report['removed'].append(row['path'])
    finally:
        report['finished_at']=time.time();lab.private_write(receipt,json.dumps(report,indent=2)+'\n')
        for file in sorted(staging.rglob('*'),reverse=True):
            if file.is_file():file.unlink()
            elif file.is_dir():file.rmdir()
        staging.rmdir()
    print(json.dumps({'pointer':pointer,'rotations':len(selected),'raw_bytes':report['bytes'],'archive_bytes':report['archive_bytes']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=float,required=True)
    p.add_argument('--name',required=True);p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args();checkpoint(a.before,a.name,a.receipt)
