"""Independent owned clients must retain both validated completion records."""
import json,time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from tools.client_compatibility import interaction_offline_bridge_deploy as module


def test_concurrent_closures_do_not_lose_an_actor_record(tmp_path,monkeypatch):
    p=tmp_path/'deployment.json';p.write_text(json.dumps({'reconnected':{}}))
    def close(t,directory,review):
        e=json.loads(p.read_text());time.sleep(.1)
        e['reconnected'][t.name]={'completed':True,'parked':True}
        p.write_text(json.dumps(e))
    monkeypatch.setattr(module,'finish_locked',close)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(module.finish,SimpleNamespace(name=n),tmp_path,None) for n in ('primary','scout')]
        for f in futures:f.result(timeout=3)
    assert json.loads(p.read_text())['reconnected']=={
        'primary':{'completed':True,'parked':True},'scout':{'completed':True,'parked':True}}
