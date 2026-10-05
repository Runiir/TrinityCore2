import copy
import pytest
from types import SimpleNamespace
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


def test_laya_can_use_a_discovered_mouseover_with_the_existing_input_lock(monkeypatch,tmp_path):
    from tools.client_compatibility import native_input_adapter
    from . import laya_ui
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    (tmp_path/'run').mkdir()
    before=named_frame();before['farm_ui'].update(tooltip=None,soft_interact={},bindings={'INTERACTTARGET':[]})
    fresh=named_frame(2);fresh.update(movement={'in_combat':False},archaeology={'casting':False})
    frames=iter([fresh,named_frame(3)])
    monkeypatch.setattr(interact,'observe',lambda _:next(frames))
    monkeypatch.setattr(interact,'stationary',lambda *_:None)
    monkeypatch.setattr(interact.inputs,'focus',lambda _:{'owned':True})
    monkeypatch.setattr(interact.inputs,'execute',lambda *_:pytest.fail('input lock must not be reacquired'))
    events=[]
    sender=SimpleNamespace(X=SimpleNamespace(ButtonPress='down',ButtonRelease='up'),
        initialization={'owned':True},move=lambda *p:events.append(('move',p)),
        _send=lambda *p:events.append(p),close=lambda:events.append(('close',)))
    monkeypatch.setattr(native_input_adapter,'Input',lambda:sender)
    def choose(state,_,options):
        assert state['artifact_name']=='Night Elf Archaeology Find'
        assert state['combat'] is False and state['casting'] is False
        assert 'mouseover_interact' in options
        return 'mouseover_interact',{},{}
    monkeypatch.setattr(laya_ui,'choose',choose)
    result=interact.use(tmp_path/'search',before,{'Night Elf Archaeology Find'},maximum=1)
    assert events==[('move',(640,260)),('down',9),('up',9),('close',)]
    assert result['input']['completed']
