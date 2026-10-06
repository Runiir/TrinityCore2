"""Typed UI choices using the selected pinned local decision model."""
import json
import urllib.request
import urllib.error
import time
from .ui_choice import MODEL, REVISION
ENDPOINT='http://127.0.0.1:8004'
RELOAD_RETRY_SECONDS=45


def identity(response):
    from . import decision_backend
    return decision_backend.identity(response)


def read_json(request,*,timeout):
    """Keep the actor alive during a short, owned decision-service reload."""
    from . import runtime
    deadline=time.monotonic()+RELOAD_RETRY_SECONDS;delay=.2
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
    from . import decision_backend
    if len(candidates)<2:raise ValueError('Laya UI choices require at least two candidates')
    expected=decision_backend.selected()
    request={'model':expected['model'],'state':state,'questions':{'action':{
        'type':'choice','instructions':instructions,'criteria':candidates}}}
    req=urllib.request.Request(ENDPOINT+'/v1/ui',data=json.dumps(request).encode(),
                               headers={'Content-Type':'application/json'})
    response=read_json(req,timeout=15)
    action=response['answers']['action']['choice']
    decision_backend.validate(response,expected)
    if (action not in candidates
            or any(v['truncated_fields'] for v in response['token_budget'].values())):
        raise RuntimeError('UI model identity, candidates, or complete context changed')
    return action,request,response
