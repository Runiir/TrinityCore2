"""Small UI questions using the original pinned Laya head on localhost."""
import json
import urllib.request
from .ui_choice import MODEL, REVISION
ENDPOINT='http://127.0.0.1:8004'


def choose(state,instructions,candidates):
    request={'model':MODEL,'state':state,'questions':{'action':{
        'type':'choice','instructions':instructions,'criteria':candidates}}}
    req=urllib.request.Request(ENDPOINT+'/v1/ui',data=json.dumps(request).encode(),
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=15) as reply:response=json.load(reply)
    action=response['answers']['action']['choice']
    if (response.get('model')!=MODEL or response.get('revision')!=REVISION
            or response.get('adapter') is not None or action not in candidates
            or any(v['truncated_fields'] for v in response['token_budget'].values())):
        raise RuntimeError('UI model identity, candidates, or complete context changed')
    return action,request,response
