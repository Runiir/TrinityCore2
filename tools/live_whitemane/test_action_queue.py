import copy
import json
import pytest
from . import action_queue,runtime


@pytest.fixture
def clock(monkeypatch,tmp_path):
    now=[0.0]
    monkeypatch.setattr(action_queue.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(action_queue.time,'sleep',lambda duration:now.__setitem__(0,now[0]+duration))
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    return now


def frame(sequence=1,*,mounted=False,casting=False,uptime=0,ends=None):
    return {'observed_at':sequence,'runtime':{'pid':123},
        'movement':{'sequence':sequence,'in_world':True,'dead':False,'on_taxi':False},
        'archaeology':{'sequence':sequence,'mounted':mounted,'casting':casting},
        'farm_ui':{'sequence':sequence,'uptime':uptime,
            'casting':{'name':'Mount' if casting else None,'ends':ends}}}


@pytest.mark.parametrize('cast_seconds',[1.5,4.0])
def test_mount_waits_for_the_observed_cast_and_never_repeats_the_toggle(clock,tmp_path,cast_seconds):
    calls=[];sequence=[1]
    def observe(_):
        sequence[0]+=1;t=clock[0];casting=.2<=t<.2+cast_seconds
        return frame(sequence[0],mounted=t>=.2+cast_seconds,casting=casting,uptime=t,
            ends=.2+cast_seconds if casting else None)
    result=action_queue.run(tmp_path/'queue',frame(),'mount',lambda row:calls.append(clock[0]) or {},
        lambda row:row['archaeology']['mounted'],observe)
    assert calls==[0] and result['cast_observed'] and result['completed']
    assert clock[0]>=.2+cast_seconds
    assert json.loads((tmp_path/'queue/queue.json').read_text())['status']=='completed'


def test_existing_cast_and_gcd_finish_before_an_input_is_dispatched(clock,tmp_path):
    calls=[];sequence=[1]
    before=frame(casting=True,ends=1.5);before['farm_ui']['gcd']={'ends':2}
    def observe(_):
        sequence[0]+=1;t=clock[0]
        row=frame(sequence[0],mounted=t>=2.2,casting=t<1.5,uptime=t,ends=1.5)
        row['farm_ui']['gcd']={'ends':2}
        return row
    result=action_queue.run(tmp_path/'queue',before,'mount',lambda row:calls.append(clock[0]) or {},
        lambda row:row['archaeology']['mounted'],observe)
    assert len(calls)==1 and calls[0]>=2 and result['completed']


def test_old_displayed_generations_cannot_confirm_a_successful_toggle(clock,tmp_path):
    calls=[];count=[0]
    def observe(_):
        count[0]+=1
        return frame(2,mounted=count[0]>1)
    with pytest.raises(RuntimeError,match='mount input did not confirm'):
        action_queue.run(tmp_path/'queue',frame(),'mount',lambda row:calls.append('toggle') or {},
            lambda row:row['archaeology']['mounted'],observe)
    assert calls==['toggle']
    assert not json.loads((tmp_path/'queue/queue.json').read_text())['completed']


def test_an_action_already_completed_while_queued_does_not_toggle_it_back(clock,tmp_path):
    result=action_queue.run(tmp_path/'queue',frame(),'mount',lambda row:pytest.fail('no second toggle'),
        lambda row:row['archaeology']['mounted'],lambda _:frame(2,mounted=True))
    assert result['already_completed'] and result['inputs']==[]


def test_conflicting_command_cannot_enter_while_another_is_pending(clock,tmp_path):
    calls=[];count=[1]
    def send(row):
        calls.append('mount')
        with pytest.raises(RuntimeError,match='already pending'):
            action_queue.run(tmp_path/'other',row,'dismount',lambda _:pytest.fail('conflicting input'),
                lambda _:False,lambda _:row)
        return {}
    def observe(_):
        count[0]+=1;return frame(count[0],mounted=bool(calls))
    result=action_queue.run(tmp_path/'queue',frame(),'mount',send,
        lambda row:row['archaeology']['mounted'],observe)
    assert calls==['mount'] and result['completed']


def test_client_change_cancels_a_queued_command_before_input(clock,tmp_path):
    row=frame(2);row['runtime']={'pid':456}
    with pytest.raises(RuntimeError,match='owned client changed'):
        action_queue.run(tmp_path/'queue',frame(),'mount',lambda _:pytest.fail('stale queued input'),
            lambda _:False,lambda _:copy.deepcopy(row))
