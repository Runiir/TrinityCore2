import hashlib
import json
import subprocess
from types import SimpleNamespace
import pytest
from . import resources, runtime


def test_trimming_preserves_monotonic_indices_and_pending_resume(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    state={'steps':[{'index':i,'completed':i<999} for i in range(1000)],'runs':[{}]*100}
    resources.trim_session(state,'dig')
    assert len(state['steps'])==40 and len(state['runs'])==8
    assert state['next_step_index']==1000 and not state['steps'][-1]['completed']
    state['steps'].append({'index':1000});resources.trim_session(state,'dig')
    assert state['next_step_index']==1001 and state['steps'][0]['index']==961


def test_disk_failure_is_never_hidden_by_poll_cache(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    runtime.write(tmp_path/'run/resource_limits.json',{})
    monkeypatch.setattr(resources,'snapshot',lambda _:{'failures':['disk limit']})
    with pytest.raises(resources.ResourceLimit,match='disk limit'):resources.check(force=True)
    # A failed sample must remain fatal on subsequent input checks.
    with pytest.raises(resources.ResourceLimit,match='disk limit'):resources.check()


def test_rotating_actions_preserves_closed_receipts(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    runtime.write(tmp_path/'run/resource_limits.json',{'action_log_mib':.00001})
    resources.append_action({'action':'first','padding':'x'*100})
    resources.append_action({'action':'second'})
    closed=list((tmp_path/'evidence').glob('actions_closed_*.jsonl'))
    assert len(closed)==1 and json.loads(closed[0].read_text())['action']=='first'
    assert json.loads((tmp_path/'evidence/actions.jsonl').read_text())['action']=='second'


def test_remote_failure_keeps_every_unsynced_file(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    evidence=tmp_path/'evidence/closed/decision.json';runtime.write(evidence,{'completed':True})
    def failed(*_,**__):raise subprocess.CalledProcessError(1,['pixi'],stderr='remote unavailable')
    monkeypatch.setattr(resources.subprocess,'run',failed)
    with pytest.raises(subprocess.CalledProcessError):resources.offload([evidence.parent])
    assert json.loads(evidence.read_text())=={'completed':True}


def test_verified_prune_never_deletes_new_or_changed_evidence(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    old=tmp_path/'evidence/old.png';old.parent.mkdir();old.write_bytes(b'old')
    changed=old.with_name('changed.png');changed.write_bytes(b'first')
    def item(p):return {'path':str(p.relative_to(tmp_path)),'bytes':p.stat().st_size,
        'mtime_ns':p.stat().st_mtime_ns,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    manifest=[item(old),item(changed)]
    changed.write_bytes(b'new data');new=old.with_name('new.png');new.write_bytes(b'new')
    archive=tmp_path/'batch.tar.gz';archive.write_bytes(b'archive')
    cache=tmp_path/'cache';obj=cache/'files/md5/12/3456';obj.parent.mkdir(parents=True);obj.write_bytes(b'cache')
    monkeypatch.setattr(resources.subprocess,'check_output',lambda *_,**__:str(cache))
    result=resources.prune_verified({'manifest':manifest,'archive':str(archive)},{'md5':'123456'})
    assert not old.exists() and not archive.exists() and not obj.exists()
    assert changed.read_bytes()==b'new data' and new.read_bytes()==b'new'
    assert result['changed_files_preserved']==['evidence/changed.png']
