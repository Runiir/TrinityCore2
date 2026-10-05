"""Two retained Laya decision heads sharing one frozen encoder on the live port."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time


def serve(args):
    from fastapi import FastAPI, HTTPException
    import uvicorn
    from safetensors.torch import load_file
    from laya.common import build_sequence, render_options, serialize_state
    from tools.client_compatibility import archaeology_policy, travel_policy
    agent, _ = archaeology_policy.load_adapter(args.adapter)
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
    app=FastAPI(); lock=threading.Lock(); active='archaeology'
    def identity(name):
        metadata=heads[name]['metadata']
        return {'model':metadata['model'],'revision':metadata['adapter_sha256'],
                'parent_revision':metadata['parent_revision'],'policy':name}
    @app.get('/health')
    def health():
        return {'status':'ready',**identity('archaeology'),'heads':{n:identity(n) for n in heads},
                'device':str(agent.device),'action_authority':False,'shared_frozen_encoder':True}
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
            if active!=name:
                result=agent.model.load_state_dict(head['weights'],strict=False)
                if result.unexpected_keys or any(not k.startswith('encoder.') for k in result.missing_keys):
                    raise RuntimeError('incomplete Laya decision head')
                active=name
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
