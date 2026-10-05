"""Attributed decisions using every option in the requested retained Laya head."""
import json
import copy
import urllib.request
from tools.client_compatibility import archaeology_policy, travel_policy
from . import guidance_policy

ENDPOINT='http://127.0.0.1:8004'


def choose(state, which='archaeology', physical_state=None):
    with urllib.request.urlopen(ENDPOINT+'/health',timeout=5) as response:
        health=json.load(response)
    model=health['heads'][which]
    policy={'archaeology':archaeology_policy,'travel':travel_policy,'guidance':guidance_policy}[which]
    candidates=[state]
    if which=='archaeology' and state.get('telescope') and 'distance_yards' in state['telescope']:
        compact=copy.deepcopy(state)
        compact['telescope'].pop('distance_yards')
        candidates.append(compact)
    rejected=[]
    for candidate in candidates:
        request={'model':model['model'],'policy':which,'state':candidate}
        req=urllib.request.Request(ENDPOINT+'/v1/systemone',data=json.dumps(request).encode(),
                                   headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as response: result=json.load(response)
        action=result['answers']['action']['choice']
        if (result['revision']!=model['revision'] or action not in policy.ACTIONS
                or any(v['truncated_fields'] for v in result['token_budget'].values())):
            raise RuntimeError('Laya identity or complete input check failed')
        if action==policy.label(physical_state if physical_state is not None else state):
            result['rejected_context_attempts']=rejected
            return action,model,request,result
        rejected.append({'request':request,'response':result,'executed':False,
                         'reason':'choice disagreed with declared public guidance policy'})
    raise RuntimeError('Laya disagreed with declared policy in both context forms')
