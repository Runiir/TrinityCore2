"""Right-button turning must retain its button and release it after sender errors."""
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_trial as trial_module,owned_input
from tools.client_compatibility.interaction_mouse_turn import settled_checks


@pytest.mark.parametrize('extra,button,duration',[({},1,.5),({'button':3,'duration':1.0},3,1.0)])
def test_selected_drag_button_and_duration_reach_owned_input(monkeypatch,extra,button,duration):
    t=trial_module.Trial.__new__(trial_module.Trial);events=[]
    t.io=SimpleNamespace(drag=lambda *args,**kw:events.append((args,kw)))
    monkeypatch.setattr(trial_module.owned_input,'lease',nullcontext)
    monkeypatch.setattr(trial_module.time,'sleep',lambda _:None)
    assert t.execute({'kind':'drag','start':[900,420],'end':[980,420],**extra})==[]
    assert events==[(([900,420],[980,420]),{'button':button,'duration':duration})]


@pytest.mark.parametrize('extra',[{'button':2},{'button':True},{'duration':True},{'duration':.1},
    {'duration':2.1},{'duration':float('nan')},{'duration':float('inf')}])
def test_invalid_drag_never_initializes_input(extra):
    io=owned_input.Inputs.__new__(owned_input.Inputs)
    with pytest.raises(ValueError,match='owned client input bounds'):io.drag([900,420],[980,420],**extra)


def test_right_button_is_released_if_motion_fails(monkeypatch):
    io=owned_input.Inputs.__new__(owned_input.Inputs);events=[];moves=[]
    def move(*point):
        moves.append(point)
        if len(moves)==2:raise RuntimeError('sender lost its device')
    io.raw=SimpleNamespace(move=move,X=SimpleNamespace(ButtonPress=4,ButtonRelease=5),
        _send=lambda kind,button:events.append((kind,button)))
    io.prepare=lambda:None
    monkeypatch.setattr(owned_input,'lease',nullcontext);monkeypatch.setattr(owned_input.time,'sleep',lambda _:None)
    with pytest.raises(RuntimeError,match='sender lost'):io.drag([900,420],[980,420],button=3,duration=1)
    assert events==[(4,3),(5,3)]


@pytest.mark.parametrize('broken',[None,'missing_native','stale_public','stale_peer_position','stale_broadcast','moving'])
def test_turn_requires_native_and_peer_orientation_and_released_idle(broken):
    before=[0,0,0,0,0];after=[0,0,0,.4,0];public=[0,0];facing=.4;seen=[0,0,0,0]
    pairs=[{'native':{'body':'attributed'},'movement':{'position':after[:4]}}]
    broadcast=[{'movement':{'position':after[:4]}}];speed=0
    if broken=='missing_native':pairs[0]['native']=None
    elif broken=='stale_public':facing=0
    elif broken=='stale_peer_position':seen[0]=8
    elif broken=='stale_broadcast':broadcast[0]['movement']['position']=[0,0,0,0]
    elif broken=='moving':speed=7
    checks=settled_checks(before,after,public,facing,seen,pairs,broadcast,speed)
    assert all(checks.values())==(broken is None)
