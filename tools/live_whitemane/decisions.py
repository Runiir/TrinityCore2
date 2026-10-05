"""Attributed decisions using every option in the requested retained Laya head."""
import json
import urllib.request
from tools.client_compatibility import archaeology_policy, travel_policy
from . import guidance_policy

ENDPOINT='http://127.0.0.1:8004'


def choose(state, which='archaeology', physical_state=None):
    with urllib.request.urlopen(ENDPOINT+'/health',timeout=5) as response:
        health=json.load(response)
    model=health['heads'][which]
    policy={'archaeology':archaeology_policy,'travel':travel_policy,'guidance':guidance_policy}[which]
    request={'model':model['model'],'policy':which,'state':state}
    req=urllib.request.Request(ENDPOINT+'/v1/systemone',data=json.dumps(request).encode(),
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as response: result=json.load(response)
    action=result['answers']['action']['choice']
    if (result['revision']!=model['revision'] or action not in policy.ACTIONS
            or any(v['truncated_fields'] for v in result['token_budget'].values())):
        raise RuntimeError('Laya identity or complete input check failed')
    return action,model,request,result
