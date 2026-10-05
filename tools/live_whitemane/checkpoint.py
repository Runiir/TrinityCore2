"""Checkpoint closed public live evidence and rejected training with DVCLive/DVC.

Launcher/account logs, raw packets, process memory and credentials are excluded.
Only the explicit public evidence directory and partial synthetic head are read.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import time
from dvclive import Live
from . import runtime


def checkpoint_trial(label, trial, include=()):
    """Archive one closed live trial using observed, rather than preset, metrics."""
    if not re.fullmatch(r'[a-zA-Z0-9_]+',label):raise ValueError('invalid batch label')
    if not (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('close the input trial before checkpointing')
    trial=trial.resolve()
    if not trial.is_relative_to(runtime.ROOT/'evidence'):raise ValueError('trial is outside public evidence')
    session=json.loads((trial/'session.json').read_text())
    output=runtime.ROOT/'evidence'/('checkpoint_'+label)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    completed=[s for s in session['steps'] if s.get('completed')]
    aligned_turns=0
    for step in completed:
        if not step['action'].startswith('turn_') or not step.get('guide'):continue
        import math
        target=step['guide']['world'];after=step['after']
        world=after['archaeology']['world']
        error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-
               after['movement']['facing_radians']+math.pi)%math.tau-math.pi
        aligned_turns+=int(abs(error)<=.18)
    metrics={'live/completed_model_decisions':len(completed),
        'live/confirmed_loot':sum(bool(s.get('confirmed_looted_find')) for s in completed),
        'live/turns_aligned_after_one_hold':aligned_turns,
        'live/digsite_complete':int(session.get('finished',False)),
        'live/calculated_ascent_completed':sum(bool(p.get('smooth_ascent')) for s in completed
            for p in s.get('travel_decisions',[])),
        'live/recipe_found':int(any(s.get('after',{}).get('archaeology',{}).get('recipe_items_in_bags',0)
                                   for s in completed))}
    runtime.write(output/'receipt.json',{'schema':'whitemane_closed_trial_batch_v1','label':label,
        'closed_at':time.time(),'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'trial':str(trial.relative_to(runtime.ROOT)),'source_runs':session.get('runs',[]),
        'metrics':metrics,'failure':session.get('failure'),'stop_reason':session.get('stop_reason'),
        'public_evidence_only':True,'raw_packets':False,'account_logs':False,
        'calculated_ascent_live_qualified':False,'retained_head_weights_changed':False})
    with Live(dir=str(output/'dvclive'),save_dvc_exp=False,dvcyaml=False,report=None) as live:
        for key,value in metrics.items():live.log_metric(key,value)
        live.next_step()
    archive=runtime.REPO/'artifacts/client_harness'/f'whitemane_live_{label}.tar.gz'
    if archive.exists():raise RuntimeError('immutable checkpoint already exists')
    files={p for root in (trial,output) for p in root.rglob('*')
           if p.is_file() and p.suffix in ('.json','.jsonl','.png','.tsv')}
    for root in include:
        root=root.resolve()
        if not root.is_relative_to(runtime.ROOT/'evidence'):raise ValueError('included file is outside public evidence')
        paths=[root] if root.is_file() else root.rglob('*')
        files.update(p for p in paths if p.is_file() and p.suffix in ('.json','.jsonl','.png','.tsv'))
    files=sorted(files)
    with tarfile.open(archive,'w:gz') as handle:
        for path in files:handle.add(path,arcname=str(path.relative_to(runtime.ROOT)),recursive=False)
    return {'archive':str(archive),'public_evidence_files':len(files),'bytes':archive.stat().st_size,'metrics':metrics}


def checkpoint(label):
    if not re.fullmatch(r'[a-zA-Z0-9_]+',label):raise ValueError('invalid batch label')
    if not (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('close the input trial before checkpointing')
    output=runtime.ROOT/'evidence'/('checkpoint_'+label)
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    partial=runtime.ROOT/'models/guidance-head-v1'
    training={'status':'interrupted','accepted':False,'served':False,
              'last_reported_validation_epoch':10,'last_reported_validation_accuracy':0.728571}
    if (partial/'adapter.safetensors').exists():
        training['partial_checkpoint_sha256']=hashlib.sha256((partial/'adapter.safetensors').read_bytes()).hexdigest()
    runtime.write(output/'training_interrupted.json',training)
    code=[p for p in (runtime.REPO/'tools/live_whitemane').rglob('*') if p.is_file()
          and not {'.pixi','__pycache__','.pytest_cache'}&set(p.parts)]
    runtime.write(output/'receipt.json',{'schema':'whitemane_closed_live_batch_v1','label':label,
        'closed_at':time.time(),'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'code_sha256':{str(p.relative_to(runtime.REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code},
        'public_evidence_only':True,'raw_packets':False,'account_logs':False,
        'partial_training_accepted':False,'digsite_complete':False,'recipe_found':False,
        'retained_head_weights_changed':False})
    with Live(dir=str(output/'dvclive'),save_dvc_exp=False,dvcyaml=False,report=None) as live:
        for key,value in {'context/original_correct':14,'context/distance_correct':14,
            'context/source_correct':11,'context/full_block_correct':4,'context/total':14,
            'context/distance_edges_correct':26,'context/distance_edges_total':27,
            'guidance/renamed_schema_correct':3,'guidance/renamed_schema_total':22,
            'training/interrupted':1,'training/accepted':0,'tests/python_passed':8,'tests/boundary_passed':4,
            'live/verified_loot':1,'live/held_descent_verified':1,'live/digsite_complete':0}.items():
            live.log_metric(key,value)
        live.next_step()
    archive=runtime.REPO/'artifacts/client_harness'/f'whitemane_live_{label}.tar.gz'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if archive.exists():raise RuntimeError('immutable checkpoint already exists')
    files=sorted(p for p in (runtime.ROOT/'evidence').rglob('*') if p.is_file() and p.suffix in ('.json','.jsonl','.png','.lua'))
    with tarfile.open(archive,'w:gz') as handle:
        for path in files:handle.add(path,arcname=str(path.relative_to(runtime.ROOT)),recursive=False)
        for path in sorted(partial.glob('*')):
            if path.is_file() and path.suffix in ('.json','.safetensors'):handle.add(path,arcname=str(path.relative_to(runtime.ROOT)),recursive=False)
    return {'archive':str(archive),'public_evidence_files':len(files),'bytes':archive.stat().st_size}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--label',required=True)
    parser.add_argument('--trial',type=Path)
    parser.add_argument('--include',type=Path,action='append',default=[])
    args=parser.parse_args()
    print(json.dumps(checkpoint_trial(args.label,args.trial,args.include) if args.trial else checkpoint(args.label)))
