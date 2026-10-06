"""Small UI questions using the original pinned Laya head on localhost."""
import json
import urllib.request
import urllib.error
import time
from .ui_choice import MODEL, REVISION
ENDPOINT='http://127.0.0.1:8004'


def read_json(request,*,timeout):
    """Keep the actor alive during a short, owned decision-service reload."""
    from . import runtime
    deadline=time.monotonic()+45;delay=.2
    while True:
        if (runtime.ROOT/'run/stop_dig').exists():
            raise RuntimeError('supervisor stop requested')
        try:
            with urllib.request.urlopen(request,timeout=timeout) as reply:return json.load(reply)
        except urllib.error.HTTPError as error:
            if error.code not in (502,503,504):raise
        except (urllib.error.URLError,OSError):pass
        if time.monotonic()>=deadline:raise RuntimeError('owned Laya decision service remained unavailable')
        time.sleep(delay);delay=min(2,delay*2)


def choose(state,instructions,candidates):
    if len(candidates)<2:raise ValueError('Laya UI choices require at least two candidates')
    request={'model':MODEL,'state':state,'questions':{'action':{
        'type':'choice','instructions':instructions,'criteria':candidates}}}
    req=urllib.request.Request(ENDPOINT+'/v1/ui',data=json.dumps(request).encode(),
                               headers={'Content-Type':'application/json'})
    response=read_json(req,timeout=15)
    action=response['answers']['action']['choice']
    if (response.get('model')!=MODEL or response.get('revision')!=REVISION
            or response.get('adapter') is not None or action not in candidates
            or any(v['truncated_fields'] for v in response['token_budget'].values())):
        raise RuntimeError('UI model identity, candidates, or complete context changed')
    return action,request,response
