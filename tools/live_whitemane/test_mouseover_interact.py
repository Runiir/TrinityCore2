import copy
import pytest
from . import interact,runtime,dig_decisions


def named_frame(sequence=1):
    return {'farm_ui':{'sequence':sequence,'tooltip':'Night Elf Archaeology Find',
        'cursor':{'x':.5,'y':.55}}}


def test_mouseover_interaction_uses_button_five_without_repositioning(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(interact,'observe',lambda _:named_frame(2))
    monkeypatch.setattr(interact,'stationary',lambda *_:None)
    events=[]
    def execute(title,action,arguments):
        events.append((title,action,arguments));return {'completed':True}
    monkeypatch.setattr(interact.inputs,'execute',execute)
    result=interact.mouseover(tmp_path/'interact',named_frame(),{'Night Elf Archaeology Find'})
    assert events==[('World of Warcraft','button',{'button':9})]
    assert result['binding']=='Mouse Button 5'


def test_changed_mouseover_is_returned_to_observation_without_clicking(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    fresh=named_frame(2);fresh['farm_ui']['cursor']['x']=.6
    monkeypatch.setattr(interact,'observe',lambda _:copy.deepcopy(fresh))
    monkeypatch.setattr(interact,'stationary',lambda *_:None)
    monkeypatch.setattr(interact.inputs,'execute',lambda *_:pytest.fail('wrong mouseover must not be clicked'))
    with pytest.raises(RuntimeError,match='mouseover changed'):
        interact.mouseover(tmp_path/'interact',named_frame(),{'Night Elf Archaeology Find'})


def test_laya_is_offered_the_user_mouseover_binding(monkeypatch):
    state={'available':True,'casting':False,'artifact_visible':True,'mouseover_artifact':'Night Elf Archaeology Find'}
    def choose(_,instructions,options):
        assert 'Mouse Button 5' in options['mouseover_interact']
        return 'mouseover_interact',{},{}
    monkeypatch.setattr(dig_decisions.laya_ui,'choose',choose)
    assert dig_decisions.choose(state)[0]=='mouseover_interact'
