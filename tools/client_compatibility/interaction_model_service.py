"""Pinned generic Laya service for the user's explicitly requested UI trial."""
import argparse
import json
import os
import subprocess
import threading
import time
import urllib.request
from . import lab_runtime as lab
from .archaeology_controller import MODEL,REVISION
from .archaeology_model_service import MANIFEST

KIND='laya_interactions'
PORT=8000


def serve():
    os.environ.setdefault('USE_TF','0');os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
    from fastapi import FastAPI,HTTPException
    from laya.common import build_sequence,render_options,serialize_state
    from .archaeology_policy import base_agent
    import uvicorn
    agent=base_agent();lock=threading.Lock();app=FastAPI()
    @app.get('/health')
    def health():
        return {'status':'ready','model':MODEL,'revision':REVISION,'device':str(agent.device),
            'controller_scope':'user_requested_client_interactions','fine_tuned_for_interactions':False,
            'action_authority':False,'max_tokens':agent.cfg['max_len'],'head_max_tokens':agent.cfg['head_max_len']}
    @app.post('/v1/systemone')
    def decide(payload:dict):
        questions=payload.get('questions');state=payload.get('state')
        if payload.get('model')!=MODEL or not isinstance(state,dict) or not isinstance(questions,dict) or len(questions)!=1:
            raise HTTPException(422,'one complete typed interaction question is required')
        budgets={}
        for key,definition in questions.items():
            q=agent._to_internal(definition)
            encode=lambda s:agent.tok(s,add_special_tokens=False)['input_ids']
            head=encode(q['t']+' question: '+q['ins'])
            options=[[agent.tok.mask_token_id]+encode(' '+text) for text in render_options(q)]
            expected=len(head)+sum(map(len,options))+len(encode(serialize_state(state)))+4
            if any(len(row)>49 for row in options) or len(head)+sum(map(len,options))>agent.cfg['head_max_len'] or expected>agent.cfg['max_len']:
                raise HTTPException(422,'complete question/state exceeds token budget')
            sequence,markers=build_sequence(agent.tok,state,q,agent.cfg['max_len'],agent.cfg['head_max_len'])
            if len(sequence)!=expected or len(markers)!=len(options):raise HTTPException(422,'truncated interaction input')
            budgets[key]={'input_tokens':len(sequence),'truncated_fields':[]}
        started=time.perf_counter()
        with lock:result=agent.predict(state,questions)
        result.update(model=MODEL,revision=REVISION,elapsed_sec=time.perf_counter()-started,
            token_budget=budgets,action_authority=False)
        return result
    uvicorn.run(app,host='127.0.0.1',port=PORT,log_level='warning')


def start():
    if lab.owned_process(KIND):raise RuntimeError('owned interaction model already running')
    lab.free_port(PORT)
    command=['nice','-n','10','pixi','run','--manifest-path',str(MANIFEST),'python','-m',__spec__.name,'serve']
    with (lab.ROOT/'logs/laya_interactions.log').open('ab') as log:
        os.chmod(log.name,0o600)
        process=subprocess.Popen(command,cwd=lab.REPO,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    lab.private_write(lab.ROOT/'run/laya_interactions.json',json.dumps({'pid':process.pid,
        'start_ticks':lab.proc_start(process.pid),'command':command})+'\n')
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        if not lab.owned_process(KIND):raise RuntimeError('interaction model exited during startup')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health',timeout=.5) as r:
                identity=json.load(r)
            if identity['model']==MODEL and identity['revision']==REVISION:print(json.dumps(identity));return
        except OSError:time.sleep(.25)
    lab.stop(KIND);raise RuntimeError('interaction model startup readiness timed out')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['start','serve','stop','status'])
    action=p.parse_args().action
    if action=='start':start()
    elif action=='serve':serve()
    elif action=='stop':lab.stop(KIND)
    else:print(json.dumps(lab.owned_process(KIND)))


if __name__=='__main__':main()
