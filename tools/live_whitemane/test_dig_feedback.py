import copy
import pytest
from . import dig_feedback,action_queue,runtime
from .test_action_queue import frame


@pytest.fixture
def clock(monkeypatch,tmp_path):
    now=[0.0]
    monkeypatch.setattr(dig_feedback.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(dig_feedback.time,'sleep',lambda seconds:now.__setitem__(0,now[0]+seconds))
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    return now


def row(sequence=1,*,casting=False,uptime=0,ends=None,surveys=0,fragments=10):
    r=frame(sequence,casting=casting,uptime=uptime,ends=ends)
    r['archaeology'].update(can_survey=True,flying=False,falling=False,
        successful_surveys=surveys,loot_open=False,races=[{'index':3,'fragments':fragments}])
    r['farm_ui']['frame_rate']=30
    return r


def test_survey_waits_for_actual_cast_then_returns_on_its_telescope(clock,tmp_path):
    sent=[];sequence=[1]
    def observe(_):
        sequence[0]+=1;t=clock[0]
        return row(sequence[0],casting=.1<=t<.6,uptime=t,ends=.6,
            surveys=int(t>=.6))
    result=dig_feedback.survey(tmp_path/'survey',row(),lambda _:sent.append(clock[0]) or {},
        observe,lambda r:{'entry':206590} if r['archaeology']['successful_surveys'] else None)
    assert sent==[0] and result['cast_observed']
    assert .6<=clock[0]<.7


def test_survey_does_not_infer_discovery_before_delayed_create_packet(clock,tmp_path):
    sequence=[1]
    def observe(_):
        sequence[0]+=1
        return row(sequence[0],uptime=clock[0],surveys=int(clock[0]>=.1))
    result=dig_feedback.survey(tmp_path/'survey',row(),lambda _: {},observe,
        lambda _: {'entry':206590} if clock[0]>=.3 else None)
    assert .3<=clock[0]<.4 and result['after']['archaeology']['successful_surveys']==1


def test_gathering_cast_finishes_before_pickup_without_three_second_delay(clock,tmp_path):
    sequence=[1]
    def observe(_):
        sequence[0]+=1;t=clock[0]
        r=row(sequence[0],casting=t<1,uptime=t,ends=1,fragments=15 if t>=1.1 else 10)
        r['farm_ui']['gathering']={'starts':1}
        return r
    result=dig_feedback.pickup(tmp_path,row(),observe)
    assert result['cast_observed'] and result['outcome']=='fragments_increased'
    assert 1.1<=clock[0]<1.2


def test_range_error_returns_immediately_for_same_find_reapproach(clock,tmp_path):
    before=row(uptime=10);after=row(2,uptime=10.1)
    after['farm_ui']['error']={'message':'Out of range.','at':10.05}
    result=dig_feedback.pickup(tmp_path,before,lambda _:copy.deepcopy(after))
    assert result['outcome']=='out_of_range' and clock[0]==0


def test_old_range_error_cannot_end_a_new_gathering_attempt(clock,tmp_path):
    before=row(uptime=10)
    def observe(_):
        r=row(2,uptime=10+clock[0],fragments=15 if clock[0]>=.2 else 10)
        r['farm_ui']['error']={'message':'Out of range.','at':9}
        return r
    result=dig_feedback.pickup(tmp_path,before,observe)
    assert result['outcome']=='fragments_increased' and clock[0]>=.2
