"""Independent owned clients must retain both validated completion records."""
import copy,json,time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from tools.client_compatibility import interaction_offline_bridge_deploy as module


def test_concurrent_closures_do_not_lose_an_actor_record(tmp_path,monkeypatch):
    p=tmp_path/'deployment.json';initial={'reconnected':{},'completed':False,'native':{'pid':1}}
    p.write_text(json.dumps(initial))
    def current(t,directory):
        e=json.loads(p.read_text());time.sleep(.1);return e
    monkeypatch.setattr(module,'current',current)
    tasks=[]
    for n in ('primary','scout'):
        out=tmp_path/n;out.mkdir()
        e={'completed':True,'failure':None,'finished_at':1,'actor':{'actor':n},'session':n}
        (out/'episode.json').write_text(json.dumps(e));tasks.append((SimpleNamespace(out=out),(copy.deepcopy(initial),n,n)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(module.join_completion,t,tmp_path,result) for t,result in tasks]
        for f in futures:f.result(timeout=3)
    e=json.loads(p.read_text())
    assert e['reconnected']=={'primary':{'completed':True,'parked':True,'session':'primary'},
        'scout':{'completed':True,'parked':True,'session':'scout'}}
    assert e['completed'] and e['finished_at']
    assert all(row['sha256']==module.lab.sha256(__import__('pathlib').Path(row['episode']))
        for row in e['parked_reconnect_attempt'].values())
