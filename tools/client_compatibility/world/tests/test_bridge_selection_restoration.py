"""Reconnect restoration preserves current user selection and verifies reselection."""
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_bridge_restoration as bridge


@pytest.mark.parametrize('current,wrong_lookup',[(10,False),(0,False),(20,False),(0,True)])
def test_reconnect_does_not_replace_a_different_user_selection(monkeypatch,current,wrong_lookup):
    wanted={'exists':True,'guid':'Creature-owned-10','name':'Parched Buzzard'}
    def public():return wanted.copy() if native.selected==10 else {
        'exists':bool(native.selected),'guid':'Creature-other' if native.selected else None,
        'name':'Other target' if native.selected else None}
    native=SimpleNamespace(selected=current,poll=lambda:native,pair=lambda *_:native.selected)
    monkeypatch.setattr(bridge,'oracle',lambda _:native)
    for name,value in [('resources',{}),('native_state',{}),('known',[]),('saved_actions',[]),
        ('pose',{'stand':0,'sheath':1}),('afk',False),('position',[1,2,3,4,0])]:
        monkeypatch.setattr(bridge,name,lambda *_,value=value:value)
    monkeypatch.setattr(bridge,'restored_native_state',lambda *_:True)
    inputs=[]
    def execute(action):inputs.append(action);native.selected=20 if wrong_lookup else 10
    t=SimpleNamespace(fixture={'guid':1},receipt={},persist=lambda:None,execute=execute,
        observe=lambda _:({'target':public(),'lua_errors':[],'blocked_actions':[]},{}))
    baseline={'resources':{},'stats':{},'spells':[],'actions':[],'pose':{'stand':0,'sheath':1},
        'afk':False,'position':[1,2,3,4,0],'selection':{'native_guid':10,'public':wanted}}
    if current==20 or wrong_lookup:
        with pytest.raises(RuntimeError,match='selected target differs'):bridge.restore(t,baseline)
    else:
        bridge.restore(t,baseline)
        assert all(t.receipt['bridge_selection_restoration']['checks'].values())
    assert inputs==([{'kind':'chat','value':'/targetexact Parched Buzzard'}] if current==0 else [])
    if current==20:assert native.selected==20
