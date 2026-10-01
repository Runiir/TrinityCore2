"""Archive closed travel/archaeology episodes and sync their DVC checkpoint."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from dvclive import Live
from . import lab_runtime as lab
from .checkpoint_archaeology import training_metrics


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',required=True)
    p.add_argument('--episode',action='append',default=[]);a=p.parse_args()
    if not a.name.replace('_','').isalnum():raise ValueError('invalid checkpoint name')
    target=lab.REPO/'artifacts/client_harness'/(a.name+'.tar.gz')
    if target.exists() or Path(str(target)+'.dvc').exists():raise ValueError('checkpoint exists')
    paths=[lab.ROOT/'models/travel-head-v1',lab.ROOT/'models/travel-head-v2',lab.ROOT/'models/travel-head-v3',lab.ROOT/'models/travel-head-startup-failure']
    paths.extend(lab.ROOT/'evidence'/name for name in ['world_packets.jsonl','client_monitor.json',
        'pretravel_world_packets.jsonl.gz','pretravel_modern_world.jsonl.gz','travel_ready.png','travel_start.png',
        'travel_protocol_tests.xml','travel_live_validation.json','travel_serving_preflight.json',
        'taxi_stall.png','taxi_relogin.png','taxi_retry_ready.png','taxi_query_login.png',
        'taxi_hotfix_login.png','taxi_hotfix_ready.png','travel_live_ready.png'])
    paths.append(lab.ROOT/'logs/modern_world.jsonl')
    paths.append(lab.ROOT/'bin/navmesh_probe')
    episodes=[]
    for name in a.episode:
        if Path(name).name!=name:raise ValueError('invalid episode name')
        path=lab.ROOT/'evidence'/name
        receipt=json.loads((path/'episode.json').read_text())
        if not receipt.get('finished_at'):raise ValueError('episode still open')
        paths.append(path);episodes.append(receipt)
    with tempfile.TemporaryDirectory(dir=lab.ROOT/'run/tmp') as scratch:
        scratch=Path(scratch)
        training_metrics(lab.ROOT/'models/travel-head-v3',scratch/'training')
        with Live(dir=str(scratch/'live'),save_dvc_exp=False,dvcyaml=False,report=None) as live:
            for name,r in zip(a.episode,episodes):
                live.log_param('episode',name)
                live.log_metric('completed',int(r.get('completed',False)))
                live.log_metric('actions',len(r['steps']))
                live.log_metric('collected_finds',len(r.get('finds',[])))
                live.log_metric('travel_legs',len(r.get('legs_completed',[])))
                live.log_metric('sites_completed',len(r.get('sites_completed',[])))
                live.log_metric('duration_seconds',r['finished_at']-r['started_at']);live.next_step()
        metadata={'schema':'client442_travel_checkpoint_v1','code_commit':subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),'closed_episodes':a.episode,
            'preceding_archaeology_checkpoint':'442_archaeology_boundaries_20261001.tar.gz.dvc',
            'authentication_and_credentials_excluded':True}
        (scratch/'checkpoint.json').write_text(json.dumps(metadata,indent=2)+'\n')
        with tarfile.open(target,'w:gz',compresslevel=6) as archive:
            for path in paths:
                if path.exists():archive.add(path,arcname=str(path.relative_to(lab.ROOT)))
            archive.add(scratch,arcname='tracking')
    relative=str(target.relative_to(lab.REPO))
    for command in [['dvc','add',relative],['dvc','status',relative+'.dvc'],['dvc','push',relative+'.dvc']]:
        subprocess.run(command,cwd=lab.REPO,check=True)
    print(json.dumps({'file':relative,'sha256':lab.sha256(target),'bytes':target.stat().st_size}))


if __name__=='__main__':main()
