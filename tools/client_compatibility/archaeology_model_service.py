"""Loopback-only service for the separately checkpointed Laya archaeology head."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request
from . import archaeology_policy as policy, lab_runtime as lab

PORT=8002
KIND='laya_archaeology'
ENDPOINT=f'http://127.0.0.1:{PORT}/v1/systemone'
MANIFEST=Path.home()/'.local/share/trinity-laya/pixi.toml'


def serve(directory):
    from fastapi import FastAPI,HTTPException
    import uvicorn
    from laya.common import build_sequence,render_options,serialize_state
    agent,metadata=policy.load_adapter(directory)
    if not metadata['shadow_accepted']:raise ValueError('candidate has not passed shadow acceptance')
    app=FastAPI();lock=threading.Lock()
    @app.get('/health')
    def health():
        return {'status':'ready','model':metadata['model'],'revision':metadata['adapter_sha256'],
            'parent_revision':metadata['parent_revision'],'device':str(agent.device),'action_authority':False}
    @app.post('/v1/systemone')
    def decide(payload:dict):
        state=payload.get('state')
        if payload.get('model')!=metadata['model'] or not isinstance(state,dict):raise HTTPException(422,'invalid model/state')
        definition=policy.question();q=agent._to_internal(definition)
        encode=lambda s:agent.tok(s,add_special_tokens=False)['input_ids']
        head=encode('choice question: '+q['ins'])
        options=[[agent.tok.mask_token_id]+encode(' '+text) for text in render_options(q)]
        state_tokens=encode(serialize_state(state))
        if any(len(o)>49 for o in options) or len(head)+sum(map(len,options))>agent.cfg['head_max_len']:
            raise HTTPException(422,'question exceeds complete head budget')
        expected=len(head)+sum(map(len,options))+len(state_tokens)+4
        if expected>agent.cfg['max_len']:raise HTTPException(422,'state exceeds complete input budget')
        sequence,markers=build_sequence(agent.tok,state,q,agent.cfg['max_len'],agent.cfg['head_max_len'])
        if len(sequence)!=expected or len(markers)!=len(policy.ACTIONS):raise HTTPException(422,'input was truncated')
        started=time.perf_counter()
        with lock:result=agent.predict(state,{'action':definition})
        result.update(model=metadata['model'],revision=metadata['adapter_sha256'],parent_revision=metadata['parent_revision'],
            elapsed_sec=time.perf_counter()-started,action_authority=False,
            token_budget={'action':{'input_tokens':len(sequence),'truncated_fields':[]}})
        return result
    uvicorn.run(app,host='127.0.0.1',port=PORT,log_level='warning')


def start(directory):
    if lab.owned_process(KIND):raise RuntimeError('owned archaeology model is already running')
    lab.free_port(PORT)
    command=['pixi','run','--manifest-path',str(MANIFEST),'python','-m',__spec__.name,'serve','--adapter',str(directory)]
    with (lab.ROOT/'logs/laya_archaeology.log').open('ab') as log:
        os.chmod(log.name,0o600)
        process=subprocess.Popen(command,cwd=lab.REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    lab.private_write(lab.ROOT/f'run/{KIND}.json',json.dumps({'pid':process.pid,'start_ticks':lab.proc_start(process.pid),'command':command})+'\n')
    for _ in range(200):
        if not lab.owned_process(KIND):raise RuntimeError('archaeology model exited during startup')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health',timeout=.3) as response:
                print(json.dumps(json.load(response)));return
        except OSError:time.sleep(.1)
    lab.stop(KIND);raise RuntimeError('model startup failed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['start','serve','stop','status'])
    p.add_argument('--adapter',type=Path,default=lab.ROOT/'models/archaeology-head-v1');args=p.parse_args()
    if args.action=='serve':serve(args.adapter)
    elif args.action=='start':start(args.adapter)
    elif args.action=='stop':lab.stop(KIND)
    else:print(bool(lab.owned_process(KIND)))


if __name__=='__main__':main()
