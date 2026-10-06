"""Close an open parked-scout deployment only from both bound successful restorations."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_bridge_deploy import identity


def validate(report,episodes,current):
    if (report.get('completed') or report.get('finished_at') or not report.get('parked_scout') or
        not report.get('native_unchanged') or set(report.get('reconnected',{}))!={'primary','scout'} or
        not all(v.get('completed') for v in report['reconnected'].values()) or
        report['reconnected']['scout'].get('parked') is not True):
        raise RuntimeError('deployment is not the incomplete successful parked-scout case')
    for name,count,key,guid in [('primary',9,'bridge_native_restoration',1),('scout',5,'restoration_checks',2)]:
        e=episodes[name]
        checks=e.get(key,{}) if name=='scout' else e.get(key,{}).get('checks',{})
        if (e.get('completed') is not True or e.get('failure') is not None or not e.get('finished_at') or
            e.get('actor',{}).get('actor')!=name or e['actor'].get('guid')!=guid or
            e.get('runtime')!=current[name] or current[name]['worldserver']!=report.get('native') or
            current[name]['modern_world']!=report.get('after') or len(checks)!=count or not all(checks.values())):
            raise RuntimeError('deployment restoration receipt or current lifetime differs')


def close(directory):
    directory=directory.resolve();path=directory/'deployment.json'
    if not directory.is_relative_to(lab.ROOT/'evidence'):raise ValueError('requires an owned private deployment')
    report=json.loads(path.read_text());before_sha=lab.sha256(path);episodes={};current={};sources=[]
    attempts={**report.get('parked_reconnect_attempt',{}),**report.get('reconnect_attempts',{})}
    for name,suffix in [('primary','primary_after'),('scout','scout_parked_after')]:
        p=directory/suffix/'episode.json';attempt=attempts.get(name,{})
        if attempt.get('episode')!=str(p) or attempt.get('sha256')!=lab.sha256(p) or not attempt.get('completed'):
            raise RuntimeError('deployment attempt does not bind its closed restoration')
        episodes[name]=json.loads(p.read_text())
        with actor(name):current[name]={k:identity(k) for k in ['worldserver','modern_world','client']}
        sources.append({'path':str(p),'sha256':lab.sha256(p)})
    validate(report,episodes,current)
    report.update(completed=True,finished_at=time.time(),closure={
        'method':'Both closed restoration receipts and current owned lifetimes verified; no game input.',
        'prior_report_sha256':before_sha,'sources':sources})
    lab.private_write(path,json.dumps(report,indent=2)+'\n')
    print(json.dumps({'completed':True,'input_sent':False,'restoration_sources':sources}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    close(p.parse_args().directory)
