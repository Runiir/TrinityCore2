"""Attributed decisions using every option in the requested retained Laya head."""
import json
import urllib.request
from tools.client_compatibility import archaeology_policy, travel_policy
from . import guidance_policy
from .laya_ui import read_json

ENDPOINT='http://127.0.0.1:8004'


def choose(state, which='archaeology', physical_state=None):
    health=read_json(ENDPOINT+'/health',timeout=5)
    model=health['heads'][which]
    policy={'archaeology':archaeology_policy,'travel':travel_policy,'guidance':guidance_policy}[which]
    request={'model':model['model'],'policy':which,'state':state}
    req=urllib.request.Request(ENDPOINT+'/v1/systemone',data=json.dumps(request).encode(),
                               headers={'Content-Type':'application/json'})
    result=read_json(req,timeout=10)
    action=result['answers']['action']['choice']
    if (result['revision']!=model['revision'] or action not in policy.ACTIONS
            or any(v['truncated_fields'] for v in result['token_budget'].values())):
        raise RuntimeError('Laya identity or complete input check failed')
    return action,model,request,result
