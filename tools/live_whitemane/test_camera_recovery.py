import copy
import json
import pytest
from . import camera_recovery,inputs,runtime,farm_actions
from .test_farm_loop import row


def setup(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    r=row();r['farm_ui']['macro']={'schema':'stock_macro_ui_v2','visible':False,
        'installed':{'index':0,'character':False},'controls':[]}
    path=tmp_path/'run/camera_macro_request.json'
    runtime.write(path,{'runtime':r['runtime'],'receipt':str(tmp_path/'receipt.json')})
    return r,path


def install(r):
    r['farm_ui']['macro']['installed']={'name':camera_recovery.NAME,'body':camera_recovery.BODY,'index':121}
    r['farm_ui']['camera_macros']=[{'enabled':True,'label':camera_recovery.NAME,'id':121,'slot':72,'x':.4,'y':.9}]


def test_camera_request_activates_only_the_existing_macro(monkeypatch,tmp_path):
    r,path=setup(monkeypatch,tmp_path);install(r);calls=[]
    monkeypatch.setattr(camera_recovery,'click_choice',lambda *args,**kw:calls.append((args,kw)) or {'executed':True})
    monkeypatch.setattr(camera_recovery,'observe',lambda _:r)
    monkeypatch.setattr(camera_recovery.camera_zoom,'restore',lambda *_:{'confirmed':True})
    assert camera_recovery.apply_request(tmp_path/'step',r)
    assert len(calls)==1 and calls[0][0][2]==('camera_macros',)
    assert calls[0][1]['matching_only']
    assert not path.exists() and json.loads((tmp_path/'receipt.json').read_text())['completed']


@pytest.mark.parametrize('changed',['body','name','bar'])
def test_missing_or_changed_macro_does_not_open_chat_or_edit_any_text(monkeypatch,tmp_path,changed):
    r,path=setup(monkeypatch,tmp_path);install(r)
    if changed=='bar':r['farm_ui']['camera_macros']=[]
    else:r['farm_ui']['macro']['installed'][changed]='changed'
    monkeypatch.setattr(inputs,'execute',lambda *_:pytest.fail('text input is disabled'))
    monkeypatch.setattr(camera_recovery,'click_choice',lambda *_:pytest.fail('changed macro must not be clicked'))
    assert not camera_recovery.apply_request(tmp_path/'step',r)
    assert 'text-box input is disabled' in json.loads(path.read_text())['reason']


@pytest.mark.parametrize('busy',['casting','moving','combat','flying'])
def test_macro_setup_waits_for_readiness_without_primary_input(monkeypatch,tmp_path,busy):
    r,path=setup(monkeypatch,tmp_path)
    if busy=='moving':r['movement']['speed']=7
    elif busy=='combat':r['movement']['in_combat']=True
    else:r['archaeology'][busy]=True
    monkeypatch.setattr(camera_recovery,'click_choice',lambda *_:pytest.fail('busy client cannot reset the camera'))
    assert not camera_recovery.apply_request(tmp_path,r) and path.exists()


@pytest.mark.parametrize('signal',['right_down','mouselooking'])
def test_ui_handoff_uses_camera_facts_before_clicking(monkeypatch,tmp_path,signal):
    r=row();r['farm_ui']['camera_input']={signal:True}
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    with pytest.raises(RuntimeError,match='camera mouse-look is still active'):
        farm_actions.stationary(r,r)


def test_visible_macro_is_a_choice_and_does_not_change_airborne_flight_actions():
    from . import farm_policy
    from .dig_policy import SolveBatches
    r=row();r['archaeology']['can_survey']=True;r['archaeology']['falling']=False
    r['farm_ui']['camera_macros']=[{'slot':6,'label':camera_recovery.NAME}]
    options=farm_policy.legal_actions(r,SolveBatches())
    assert 'camera_macro' in options and 'dig' in options
    r['archaeology'].update(flying=True,mounted=True)
    options=farm_policy.legal_actions(r,SolveBatches())
    assert 'camera_macro' not in options and 'land' in options
