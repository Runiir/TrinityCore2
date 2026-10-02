import json
import multiprocessing
import time
import pytest
from tools.client_compatibility import lab_runtime as lab,cohort,owned_input


def test_actor_client_roots_do_not_change_shared_services(tmp_path,monkeypatch):
    monkeypatch.setattr(lab,'ROOT',tmp_path)
    monkeypatch.setenv('CLIENT442_ACTOR','scout')
    assert lab.client_root()==tmp_path/'actors/scout'
    assert lab.ROOT==tmp_path
    monkeypatch.setattr(lab,'proc_start',lambda pid:str(pid))
    for root,pid in [(tmp_path,11),(lab.client_root(),22)]:
        (root/'run').mkdir(parents=True,exist_ok=True)
        (root/'run/client.json').write_text(json.dumps({'pid':pid,'start_ticks':str(pid)}))
    (tmp_path/'run/worldserver.json').write_text(json.dumps({'pid':33,'start_ticks':'33'}))
    assert lab.owned_process('client')['pid']==22
    assert lab.owned_process('worldserver')['pid']==33
    monkeypatch.setenv('CLIENT442_ACTOR','primary')
    assert lab.owned_process('client')['pid']==11


@pytest.mark.parametrize('name',['../primary','scout/primary','ScOuT',''])
def test_actor_path_cannot_escape_its_private_root(monkeypatch,name):
    monkeypatch.setenv('CLIENT442_ACTOR',name)
    with pytest.raises(ValueError):lab.client_root()


def lease_worker(root,name,queue):
    lab.ROOT=root
    with owned_input.lease():
        with owned_input.lease():
            queue.put((name,'enter'));time.sleep(.1);queue.put((name,'leave'))


def test_focus_input_lease_serializes_two_processes(tmp_path):
    context=multiprocessing.get_context('fork');queue=context.Queue()
    workers=[context.Process(target=lease_worker,args=(tmp_path,name,queue)) for name in ['one','two']]
    for worker in workers:worker.start()
    events=[queue.get(timeout=5) for _ in range(4)]
    for worker in workers:worker.join(5);assert worker.exitcode==0
    assert events[0][1]=='enter' and events[1]==(events[0][0],'leave')
    assert events[2][1]=='enter' and events[3]==(events[2][0],'leave')
    assert events[0][0]!=events[2][0]


def test_owned_input_refuses_to_send_when_monitor_verification_fails(monkeypatch):
    from tools.second_client import ctl
    calls=[]
    class Raw:
        def key(self,*a,**kw):calls.append(a)
    monkeypatch.setattr(ctl,'Input',Raw)
    def fail():raise RuntimeError('wrong monitor')
    monkeypatch.setattr(owned_input,'focus',fail)
    with pytest.raises(RuntimeError,match='wrong monitor'):owned_input.Inputs().key('w',hold=.1)
    assert calls==[]


def test_unknown_task_and_uncommitted_travel_plan_are_not_launched(tmp_path):
    with pytest.raises(ValueError,match='unsupported'):cohort.command({'task':'unimplemented_quest_bot'},tmp_path)
    plan=tmp_path/'route.json';plan.write_text('{}')
    with pytest.raises(ValueError,match='committed'):cohort.command({'task':'travel','plan':str(plan)},tmp_path)
    command=cohort.command({'task':'probe','mode':'movement'},tmp_path)
    assert 'tools.client_compatibility.actor_probe' in command


def test_retired_model_is_not_called_by_new_cohorts(tmp_path):
    with pytest.raises(ValueError,match='retired'):cohort.command({'task':'archaeology'},tmp_path)
