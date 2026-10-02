"""Own independent client task processes without rebuilding or restarting servers."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from . import lab_runtime as lab,actors,owned_input

MANIFEST=lab.REPO/'tools/client_compatibility/auth/pixi.toml'


def command(job,out):
    common=['pixi','exec','--spec','pillow','--spec','python-xlib','--spec','pymysql','python','-m']
    if job['task']=='archaeology':
        raise ValueError('historical Laya controller retired by AGENTS.md; connect a current controller adapter')
    if job['task']=='travel':
        plan=Path(job['plan']).resolve()
        if not plan.is_relative_to(lab.REPO/'experiments/configs/client_harness') or not plan.is_file():
            raise ValueError('travel plan must be a committed client-harness config')
        raise ValueError('historical Laya controller retired by AGENTS.md; connect a current controller adapter')
    if job['task']=='probe' and job.get('mode') in ['observe','movement']:
        return [*common,'tools.client_compatibility.actor_probe','--output',str(out),'--mode',job['mode']]
    raise ValueError('unsupported client cohort task; implement its adapter and oracle first')


def select_actor(name):
    os.environ['CLIENT442_ACTOR']=name
    lab.actor_name()


def start(path,out):
    if subprocess.check_output(['git','status','--porcelain'],cwd=lab.REPO,text=True):
        raise RuntimeError('commit experiment code/configs before starting a client cohort')
    if out.exists():raise ValueError('cohort output exists; use a fresh directory')
    config=json.loads(path.read_text());jobs=config['jobs']
    if config.get('schema')!='client442_cohort_v1' or not jobs:raise ValueError('invalid client cohort config')
    names=[j['actor'] for j in jobs]
    if len(names)!=len(set(names)):raise ValueError('only one running task may own an actor')
    if len(jobs)>config.get('maximum_clients',2):raise ValueError('cohort exceeds its declared client budget')
    original=os.environ.get('CLIENT442_ACTOR');prepared=[]
    try:
        # Complete every actor preflight before launching any worker.
        for job in jobs:
            select_actor(job['actor']);fixture=actors.load();verified=actors.register(fixture['guid'])
            if verified['account_id']!=fixture['account_id']:raise ValueError('actor account identity changed')
            if lab.owned_process('cohort_'+job['actor']):raise RuntimeError('actor already has an owned task')
            monitor=owned_input.focus()
            entry=actors.session_entry(fixture)
            environment=os.environ.copy();environment['CLIENT442_CHARACTER_GUID']=str(fixture['guid'])
            environment['CLIENT442_SESSION']=entry['session']
            environment.pop('WM_WEB_TOKEN',None)
            prepared.append((job,fixture,monitor,environment,command(job,out/job['actor'])))
        if len({fixture['guid'] for _,fixture,_,_,_ in prepared})!=len(prepared):
            raise ValueError('cohort actors cannot share a character')
        if len({monitor['pid'] for _,_,monitor,_,_ in prepared})!=len(prepared):
            raise ValueError('cohort actors cannot share an owned client process')
        out.mkdir(parents=True,mode=0o700)
        receipt={'schema':'client442_cohort_run_v1','started_at':time.time(),
            'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
            'config':config,'jobs':[],'native_worldserver_rebuilt':False,'native_worldserver_restarted':False}
        try:
            for job,fixture,monitor,environment,args in prepared:
                log=out/(job['actor']+'.console.log')
                with log.open('ab') as handle:
                    log.chmod(0o600)
                    process=subprocess.Popen(args,cwd=lab.REPO,env=environment,stdin=subprocess.DEVNULL,
                        stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                info={'pid':process.pid,'start_ticks':lab.proc_start(process.pid),'actor':fixture,
                    'command':args,'monitor':monitor,'output':str(out/job['actor'])}
                lab.private_write(lab.ROOT/f'run/cohort_{job["actor"]}.json',json.dumps(info,indent=2)+'\n')
                receipt['jobs'].append(info)
                lab.private_write(out/'cohort.json',json.dumps(receipt,indent=2)+'\n')
        except BaseException:
            for info in receipt['jobs']:
                if lab.proc_start(info['pid'])==info['start_ticks']:os.killpg(info['pid'],signal.SIGINT)
            raise
        print(json.dumps({'output':str(out),'actors':names}))
    finally:
        if original is None:os.environ.pop('CLIENT442_ACTOR',None)
        else:os.environ['CLIENT442_ACTOR']=original


def status(out,stop=False):
    receipt=json.loads((out/'cohort.json').read_text());result=[]
    for info in receipt['jobs']:
        owned=lab.owned_process('cohort_'+info['actor']['actor'])
        running=bool(owned and owned['pid']==info['pid'] and owned['start_ticks']==info['start_ticks'])
        if stop and running:os.killpg(info['pid'],signal.SIGINT)
        episode=Path(info['output'])/'episode.json'
        closed=json.loads(episode.read_text()) if episode.exists() else {}
        result.append({'actor':info['actor']['actor'],'running':running,
            'completed':closed.get('completed',False),'finished_at':closed.get('finished_at'),
            'failure':closed.get('failure'),'steps':len(closed.get('steps',[]))})
    if not any(r['running'] for r in result):
        receipt.update(finished_at=time.time(),completed=all(r['completed'] for r in result),results=result)
        lab.private_write(out/'cohort.json',json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(result,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['start','status','stop'])
    p.add_argument('--config',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.action=='start':
        if not a.config:p.error('start requires --config')
        start(a.config.resolve(),a.output.resolve())
    else:status(a.output.resolve(),a.action=='stop')


if __name__=='__main__':main()
