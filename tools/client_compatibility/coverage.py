"""Inventory compatibility work without mistaking observations for qualified passes."""
import argparse
import ast
import re
from collections import Counter
import json
from pathlib import Path
import subprocess
from . import lab_runtime as lab

MANIFEST=lab.REPO/'experiments/configs/client_harness/442_coverage_manifest_v1.json'


def load_manifest(path=MANIFEST):
    data=json.loads(path.read_text())
    if data.get('schema')!='client442_coverage_manifest_v1':raise ValueError('unknown coverage manifest schema')
    features=data['features'];ids=[row['id'] for row in features]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate coverage feature ID')
    for row in features:
        if not all(row.get(k) for k in ['id','domain','scenario','oracle']) or row['phase'] not in range(5):
            raise ValueError('incomplete compatibility scenario')
        if any(k in row for k in ['passed','coverage_percent','status']):
            raise ValueError('scenario planning cannot admit a live pass')
    return data


def opcode_inventory():
    directory=lab.REPO/'tools/client_compatibility/world'
    table=json.loads((directory/'opcodes.json').read_text())
    referenced=set()
    for path in directory.glob('*.py'):
        if path.name.startswith('generate_'):continue
        tree=ast.parse(path.read_text())
        referenced.update(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and
            isinstance(n.value,str) and n.value.startswith(('CMSG_','SMSG_','MSG_')))
    for path in (lab.REPO/'tools/client_compatibility/native_bridge').glob('*.cpp'):
        if path.name=='codec_main.cpp':continue
        referenced.update(re.findall(r'"((?:CMSG|SMSG|MSG)_[A-Z0-9_]+)"',path.read_text()))
    modern=table['modern']
    return {'source_revision':table['source_revision'],'source_hashes':table['source_hashes'],
        'modern_names':len(modern),'legacy_names':len(table['legacy']),
        'modern_client_names':sum(n.startswith('CMSG_') for n in modern),
        'modern_server_names':sum(n.startswith('SMSG_') for n in modern),
        'modern_names_referenced_by_bridge':len(set(modern)&referenced),
        'modern_names_without_bridge_reference':sorted(set(modern)-referenced),
        'limits':'A source reference is not a handler, correct payload translation, live pass, or required-gameplay classification. Never report this ratio as protocol compatibility.'}


def event_inventory(path):
    from .observation.journal import entries
    unmapped=Counter();observed=Counter();errors=Counter()
    for event in entries(path):
        if event.get('event')=='unmapped_client_packet':unmapped[event['name']]+=1
        if event.get('event')=='modern_packet':observed[event['name']]+=1
        if event.get('event') in ['world_connection_error','cast_translation_rejected','native_stream_closed',
            'packet_send_rejected','native_send_rejected']:
            errors[event['event']]+=1
    return {'unmapped_client_names':dict(sorted(unmapped.items())),
        'observed_modern_names':dict(sorted(observed.items())),'translation_errors':dict(errors),
        'limits':'Observation counts describe this trace only. No body, ticket, credential or model judgment is admitted as a compatibility pass.'}


def report(manifest):
    features=manifest['features']
    return {'schema':'client442_coverage_plan_report_v1','target':manifest['target'],
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'planned_feature_scenarios':len(features),'current_qualified_feature_passes':0,
        'historical_documents_linked':sum('history' in row for row in features),
        'planned_by_domain':dict(sorted(Counter(row['domain'] for row in features).items())),
        'features':[dict(row,qualification='pending_current_live_qualification') for row in features],
        'protocol_inventory':opcode_inventory(),
        'limits':['The manifest is an initial inventory, not proof that all game features have been enumerated.',
            'Evidence admission and multi-client execution are not implemented by this planning command.',
            'Existing archaeological and protocol checkpoints remain separate historical evidence.',
            'Individual content records need per-ID variants and reviewed correctness contracts.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['report','next','protocol'])
    p.add_argument('--manifest',type=Path,default=MANIFEST);p.add_argument('--output',type=Path)
    p.add_argument('--events',type=Path,help='Explicit sanitized bridge event journal; packet bodies are not used')
    p.add_argument('--limit',type=int,default=8);a=p.parse_args()
    manifest=load_manifest(a.manifest)
    if a.action=='next':result=sorted(manifest['features'],key=lambda row:row['phase'])[:a.limit]
    elif a.action=='protocol':result=opcode_inventory()
    else:result=report(manifest)
    if a.events:
        if not isinstance(result,dict):p.error('--events requires report or protocol')
        result['trace_inventory']=event_inventory(a.events)
    text=json.dumps(result,indent=2)+'\n'
    if a.output:lab.private_write(a.output,text)
    else:print(text,end='')


if __name__=='__main__':main()
