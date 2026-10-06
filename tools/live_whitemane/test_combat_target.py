import copy
import pytest
from . import combat_target
from .test_farm_loop import row


def enemy():
    r=row();r['movement']['in_combat']=True;r['farm_ui']['uptime']=10
    r['archaeology'].update(falling=False)
    r['farm_ui']['combat']={'target_exists':True,'hostile':True,'target_dead':False,
        'attack_in_range':False,'target_guid':'enemy','target_name':'Hyena','click_to_move':'1'}
    r['farm_ui']['bindings']['TARGETNEARESTENEMY']=['Tab']
    return r


def test_one_laya_approach_is_retained_until_range_changes_without_input_spam(monkeypatch,tmp_path):
    r=enemy();now=[0];monkeypatch.setattr(combat_target.time,'monotonic',lambda:now[0])
    choices=[];inputs=[]
    def choose(state,_,options):
        assert not state['in_melee_range'] and 'approach' in options
        choices.append(state);return 'approach',{'selected':True},{'choice':'approach'}
    monkeypatch.setattr(combat_target.laya_ui,'choose',choose)
    monkeypatch.setattr(combat_target,'observe',lambda _:copy.deepcopy(r))
    monkeypatch.setattr(combat_target.inputs,'execute',lambda *args:inputs.append(args) or {})
    approach=combat_target.TargetApproach();result={}
    assert approach.tick(tmp_path,r,result)
    for i in range(1,40):
        now[0]=i*.1;r['archaeology']['world']['north']=i*.1
        assert approach.tick(tmp_path,r,result)
    assert len(choices)==len(inputs)==1 and inputs[0][2]['key']=='9'
    r['farm_ui']['combat']['attack_in_range']=True
    assert not approach.tick(tmp_path,r,result)
    assert result['approaches'][0]['reached_melee_range']


@pytest.mark.parametrize('change',['target','combat','mounted'])
def test_target_approach_rechecks_facts_before_dispatch(monkeypatch,tmp_path,change):
    r=enemy();fresh=copy.deepcopy(r)
    if change=='target':fresh['farm_ui']['combat']['target_guid']='other'
    elif change=='combat':fresh['movement']['in_combat']=False
    else:fresh['archaeology']['mounted']=True
    monkeypatch.setattr(combat_target.laya_ui,'choose',lambda *_:('approach',{},{}))
    monkeypatch.setattr(combat_target,'observe',lambda _:fresh)
    monkeypatch.setattr(combat_target.inputs,'execute',lambda *_:pytest.fail('facts changed before dispatch'))
    assert combat_target.TargetApproach().tick(tmp_path,r,{})


def test_laya_can_select_a_hostile_target_when_aggro_has_no_target(monkeypatch,tmp_path):
    r=enemy();r['farm_ui']['combat'].update(target_exists=False,hostile=False,target_guid=None)
    monkeypatch.setattr(combat_target.laya_ui,'choose',lambda *_:('target_enemy',{},{}))
    monkeypatch.setattr(combat_target,'observe',lambda _:r)
    calls=[];monkeypatch.setattr(combat_target.inputs,'execute',lambda *args:calls.append(args) or {})
    assert combat_target.TargetApproach().tick(tmp_path,r,{})
    assert calls[0][2]['key']=='Tab'
