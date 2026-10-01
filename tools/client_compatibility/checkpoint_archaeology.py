"""Checkpoint closed lab evidence and head training metrics through DVC."""
import argparse
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from dvclive import Live
from . import lab_runtime as lab


def training_metrics(directory, target):
    receipt=json.loads((directory/'receipt.json').read_text())
    with Live(dir=str(target),save_dvc_exp=False,dvcyaml=False,report=None) as live:
        for row in receipt['history']:
            live.log_metric('validation_accuracy',row['validation_accuracy'])
            live.log_metric('training_loss_sum',row['loss'])
            live.log_metric('elapsed_seconds',row['elapsed_seconds'])
            live.next_step()
        live.log_metric('test_accuracy',receipt['test_accuracy'])
        live.log_metric('shadow_accepted',int(receipt['shadow_accepted']))
        live.log_param('adapter_sha256',receipt['adapter_sha256'])
        live.log_param('code_commit',receipt['code_commit'])
        live.log_param('synthetic_labels',True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True)
    parser.add_argument('--episode',action='append',default=[])
    args=parser.parse_args()
    if not args.name.replace('_','').isalnum():raise ValueError('invalid artifact name')
    artifact=lab.REPO/'artifacts/client_harness'/(args.name+'.tar.gz')
    if artifact.exists() or artifact.with_suffix('.gz.dvc').exists():raise ValueError('checkpoint already exists')
    paths=[lab.ROOT/'models/archaeology-head-v1',lab.ROOT/'models/archaeology-head-v2']
    names=['artifact_geometry_v1','artifact_geometry_v2','artifact_repair_deployment.json',
           'character_preview_fixed.png','placement_world_ready.png','placement_protocol_tests.xml',
           'client_monitor.json','source_mounts.json','reference','world_packets.jsonl']
    paths.extend(lab.ROOT/'evidence'/name for name in names)
    for name in args.episode:
        if Path(name).name!=name:raise ValueError('episode must be a directory name')
        directory=lab.ROOT/'evidence'/name
        episode=json.loads((directory/'episode.json').read_text())
        if 'finished_at' not in episode:raise ValueError('episode is not closed: '+name)
        paths.append(directory)
    paths.extend([lab.ROOT/'logs/modern_world.jsonl',lab.ROOT/'logs/native_build.log',lab.ROOT/'bin/worldserver'])
    metadata={'schema':'client442_archaeology_checkpoint_v1',
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'closed_episodes':args.episode,'authentication_bodies_and_credentials_excluded':True}
    with tempfile.TemporaryDirectory(dir=lab.ROOT/'run/tmp') as scratch:
        scratch=Path(scratch)
        for model in paths[:2]:training_metrics(model,scratch/model.name/'dvclive')
        (scratch/'checkpoint.json').write_text(json.dumps(metadata,indent=2)+'\n')
        with tarfile.open(artifact,'w:gz',compresslevel=6) as archive:
            for path in paths:
                if path.exists():archive.add(path,arcname=str(path.relative_to(lab.ROOT)))
            for path in scratch.iterdir():archive.add(path,arcname='tracking/'+path.name)
    relative=str(artifact.relative_to(lab.REPO))
    subprocess.run(['dvc','add',relative],cwd=lab.REPO,check=True)
    subprocess.run(['dvc','status',relative+'.dvc'],cwd=lab.REPO,check=True)
    subprocess.run(['dvc','push',relative+'.dvc'],cwd=lab.REPO,check=True)
    print(json.dumps({'artifact':relative,'sha256':lab.sha256(artifact),'bytes':artifact.stat().st_size}))


if __name__=='__main__':main()
