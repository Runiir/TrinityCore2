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
    print(json.dumps(checkpoint(parser.parse_args().label)))
