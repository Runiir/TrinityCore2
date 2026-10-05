"""Two retained Laya decision heads sharing one frozen encoder on the live port."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time
import copy


def serve(args):
    import os
    from .resources import register_model
    register_model(os.getpid())
    from fastapi import FastAPI, HTTPException
    import uvicorn
    from safetensors.torch import load_file
    from laya.common import build_sequence, render_options, serialize_state
    from tools.client_compatibility import archaeology_policy, travel_policy
    agent = archaeology_policy.base_agent()
    base_weights={k:v.detach().cpu().clone() for k,v in agent.model.state_dict().items() if not k.startswith('encoder.')}
    base_temperature=copy.deepcopy(agent.temperature)
    base_options=copy.deepcopy(agent.temperature_by_options)
    heads = {}
    for name, path, policy in [('archaeology',args.adapter,archaeology_policy),
                               ('travel',args.travel_adapter,travel_policy)]:
        metadata=json.loads((path/'receipt.json').read_text())
        weights=load_file(str(path/'adapter.safetensors'))
        if (metadata['parent_revision']!=archaeology_policy.REVISION or not metadata['shadow_accepted']
                or hashlib.sha256((path/'adapter.safetensors').read_bytes()).hexdigest()!=metadata['adapter_sha256']
                or any(k.startswith('encoder.') for k in weights)):
            raise RuntimeError('unverified or encoder-changing Laya head')
        heads[name]={'metadata':metadata,'weights':weights,'policy':policy}
    app=FastAPI(); lock=threading.Lock(); active='base_ui'
    def activate(name):
        nonlocal active
        if active!=name:
            weights=base_weights if name=='base_ui' else heads[name]['weights']
            loaded=agent.model.load_state_dict(weights,strict=False)
            if loaded.unexpected_keys or any(not k.startswith('encoder.') for k in loaded.missing_keys):
                raise RuntimeError('incomplete Laya decision head')
            active=name
        agent.temperature=base_temperature if name=='base_ui' else [1.,1.,1.]
        agent.temperature_by_options=base_options if name=='base_ui' else {}
    def identity(name):
        metadata=heads[name]['metadata']
        return {'model':metadata['model'],'revision':metadata['adapter_sha256'],
                'parent_revision':metadata['parent_revision'],'policy':name,
                'question_sha256':hashlib.sha256(json.dumps(heads[name]['policy'].question(),sort_keys=True).encode()).hexdigest()}
    # Initialize CUDA kernels before readiness, rather than charging the first
    # live decision for startup. This grants no input authority.
    started=time.perf_counter()
    for name in ('archaeology','travel','base_ui'):
        activate(name)
        definition=({'type':'choice','instructions':'Choose wait during service warm-up.',
            'criteria':{'wait':'Wait without input','continue':'Continue'}} if name=='base_ui'
            else heads[name]['policy'].question())
        agent.predict({'warmup':True},{'action':definition})
    warmup_seconds=time.perf_counter()-started
    @app.get('/health')
    def health():
        return {'status':'ready',**identity('archaeology'),'heads':{n:identity(n) for n in heads},
                'device':str(agent.device),'action_authority':False,'shared_frozen_encoder':True,
                'warmup_seconds':warmup_seconds,
                'base_ui':{'model':archaeology_policy.MODEL,'revision':archaeology_policy.REVISION,'adapter':None}}
    @app.post('/v1/ui')
    def ui_decide(payload:dict):
        from .ui_choice import token_budget, validate_ui_request
        try:
            questions=validate_ui_request(payload,allowed_questions=('action','camera'))
        except ValueError as error:
            raise HTTPException(422,str(error)) from error
        started=time.perf_counter()
        with lock:
            activate('base_ui')
            budget=token_budget(agent,payload['state'],questions)
            if any(value['truncated_fields'] for value in budget.values()):
                raise HTTPException(422,{'error':'truncation','token_budget':budget})
            result=agent.predict(payload['state'],questions)
        result.update(model=archaeology_policy.MODEL,revision=archaeology_policy.REVISION,adapter=None,
            device=str(agent.device),action_authority=False,shared_frozen_encoder=True,
            token_budget=budget,elapsed_sec=time.perf_counter()-started)
        return result
    @app.post('/v1/systemone')
    def decide(payload:dict):
        nonlocal active
        name=payload.get('policy','archaeology')
        if name not in heads: raise HTTPException(422,'unknown live decision head')
        head=heads[name]; metadata=head['metadata']; state=payload.get('state')
        if payload.get('model')!=metadata['model'] or not isinstance(state,dict):
            raise HTTPException(422,'invalid model or state')
        policy=head['policy']; definition=policy.question(); q=agent._to_internal(definition)
        encode=lambda s:agent.tok(s,add_special_tokens=False)['input_ids']
        instructions=encode('choice question: '+q['ins'])
        options=[[agent.tok.mask_token_id]+encode(' '+text) for text in render_options(q)]
        expected=len(instructions)+sum(map(len,options))+len(encode(serialize_state(state)))+4
        if (any(len(o)>49 for o in options) or len(instructions)+sum(map(len,options))>agent.cfg['head_max_len']
                or expected>agent.cfg['max_len']):
            raise HTTPException(422,'live observations exceed complete input budget')
        sequence,markers=build_sequence(agent.tok,state,q,agent.cfg['max_len'],agent.cfg['head_max_len'])
        if len(sequence)!=expected or len(markers)!=len(policy.ACTIONS):
            raise HTTPException(422,'input truncation')
        started=time.perf_counter()
        with lock:
            activate(name)
            result=agent.predict(state,{'action':definition})
        result.update(**identity(name),elapsed_sec=time.perf_counter()-started,action_authority=False,
            token_budget={'action':{'input_tokens':len(sequence),'truncated_fields':[]}})
        return result
    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8004)
    parser.add_argument('--adapter',type=Path,required=True)
    parser.add_argument('--travel-adapter',type=Path,required=True)
    args=parser.parse_args()
    if not 1024<=args.port<=65535: raise ValueError('invalid loopback port')
    serve(args)


if __name__=='__main__': main()
