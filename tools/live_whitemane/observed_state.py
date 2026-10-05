"""Keep observed world state current without selecting or sending any input."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from . import runtime,world_facts
from .observe import observe


def atomic(path,value):
    temp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    runtime.write(temp,value);temp.replace(path)


def sample():
    row=observe(runtime.ROOT/'run/observation_latest.png')
    state=world_facts.reduce(row,world_facts.pending(row))
    state.update(runtime=row['runtime'],source=row['source'],channel_ages=row.get('channel_ages'),
        action_dependency=False,telemetry_server_messages=0)
    atomic(runtime.ROOT/'run/world_state.json',state)
    target=runtime.ROOT/'run/farm_state_target.json'
    if target.exists():
        value=json.loads(target.read_text());path=Path(value['path']).resolve()
        if not path.is_relative_to(runtime.ROOT/'evidence'):raise RuntimeError('invalid owned graph target')
        if value['runtime']==row['runtime'] and path.exists():
            from .farm_graph import refresh
            refresh(path,row,latch=world_facts.pending(row))
    return state


def ensure(graph):
    owner=runtime.owned_process()
    atomic(runtime.ROOT/'run/farm_state_target.json',{'path':str(graph.resolve()),'runtime':owner})
    path=runtime.ROOT/'run/state_observer.json'
    if path.exists():
        previous=json.loads(path.read_text())
        try:
            if (previous.get('runtime')==owner and previous.get('status')=='running' and
                    runtime.proc_start(previous['pid'])==previous['start_ticks'] and
                    b'tools.live_whitemane.observed_state' in Path(f"/proc/{previous['pid']}/cmdline").read_bytes().split(b'\0')):
                return previous
        except (OSError,KeyError):pass
    process=subprocess.Popen([sys.executable,'-m','tools.live_whitemane.observed_state','serve'],
        cwd=runtime.REPO,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    return {'pid':process.pid,'runtime':owner,'starting':True}


def serve():
    path=runtime.ROOT/'run/state_observer.json';owner=runtime.owned_process()
    with (runtime.ROOT/'run/state_observer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        status={'pid':os.getpid(),'start_ticks':runtime.proc_start(os.getpid()),'runtime':owner,
            'status':'running','started_at':time.time(),'poll_seconds':.2,'inputs_sent':0}
        try:
            while owner and runtime.owned_process()==owner:
                start=time.monotonic()
                try:
                    sample();status.update(last_success_at=time.time(),failure=None)
                except Exception as error:
                    status['failure']=f'{type(error).__name__}: {error}'
                    atomic(runtime.ROOT/'run/world_state.json',{'runtime':owner,'valid':False,
                        'facts':None,'activity':'unknown','reason':status['failure'],
                        'action_dependency':False,'observed_at':time.time()})
                status['heartbeat_at']=time.time();atomic(path,status)
                time.sleep(max(.01,.2-(time.monotonic()-start)))
        finally:
            status['status']='owned_client_absent';atomic(path,status)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['serve'])
    parser.parse_args();serve()
