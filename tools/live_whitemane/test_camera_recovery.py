import copy
import json
import pytest
from . import camera_recovery,inputs,runtime,farm_actions
from .test_farm_loop import row


def setup(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    r=row();r['farm_ui']['macro']={'schema':'stock_macro_ui_v1','visible':False,
        'installed':{'index':0,'character':False},'controls':[]}
    path=tmp_path/'run/camera_macro_request.json'
    runtime.write(path,{'runtime':r['runtime'],'receipt':str(tmp_path/'receipt.json')})
    return r,path


def test_macro_creation_uses_m_then_visible_controls_and_confirms_saved_body(monkeypatch,tmp_path):
    r,path=setup(monkeypatch,tmp_path);ui=r['farm_ui']['macro'];events=[]
    def command(folder,row,text,*_):
        events.append(text)
        if text=='/m':ui['visible']=True
        return {'executed':True}
    monkeypatch.setattr(camera_recovery,'command_choice',command)
    def click(folder,row,collection,goal,expected=None):
        kind=expected['kind'];events.append(kind)
        if kind=='character':ui['character_tab']=True
        elif kind=='new':
            ui.update(popup_visible=True,name={'value':'','focused':True})
        elif kind=='accept':
            ui.update(popup_visible=False,selected_name=camera_recovery.NAME,
                installed={'name':camera_recovery.NAME,'index':121,'character':True,'body':''},
                body={'value':'','focused':True})
        elif kind=='close':
            ui['installed']['body']=ui['body']['value'];ui['visible']=False
        return {'executed':True}
    monkeypatch.setattr(camera_recovery,'click_choice',click)
    def edit(folder,row,field,value):
        events.append(('type',field,value));ui[field]['value']=value;return {'executed':True}
    monkeypatch.setattr(camera_recovery,'edit_choice',edit)
    monkeypatch.setattr(camera_recovery,'observe',lambda _:r)
    monkeypatch.setattr(camera_recovery.camera_zoom,'restore',lambda *args:{'confirmed':True})
    for i in range(8):
        assert camera_recovery.apply_request(tmp_path/str(i),r)
        if path.exists():
            request=json.loads(path.read_text());request['last_attempt']=0;runtime.write(path,request)
    assert events==['/m','character','new',('type','name',camera_recovery.NAME),'accept',
        ('type','body',camera_recovery.BODY),'close',camera_recovery.BODY.split('\n')[0]]
    assert not path.exists() and json.loads((tmp_path/'receipt.json').read_text())['completed']
    assert not any('CreateMacro(' in str(event) or 'EditMacro(' in str(event) for event in events)
    assert len(camera_recovery.BODY)<=255 and 'MouselookStop()' in camera_recovery.BODY
    assert 'SetView(2)' not in camera_recovery.BODY


@pytest.mark.parametrize('changed',['focus','selection','text'])
def test_macro_typing_rechecks_exact_selected_field_before_input(monkeypatch,tmp_path,changed):
    r,path=setup(monkeypatch,tmp_path)
    r['farm_ui']['macro'].update(selected_name=camera_recovery.NAME,
        body={'label':'Macro commands','value':'old','focused':True})
    fresh=copy.deepcopy(r);ui=fresh['farm_ui']['macro']
    if changed=='focus':ui['body']['focused']=False
    elif changed=='selection':ui['selected_name']='Other macro'
    else:ui['body']['value']='manual change'
    monkeypatch.setattr(camera_recovery.laya_ui,'choose',lambda *args:('type',{},{}))
    monkeypatch.setattr(camera_recovery,'observe',lambda _:fresh)
    monkeypatch.setattr(inputs,'execute',lambda *_:pytest.fail('changed macro must not be overwritten'))
    with pytest.raises(RuntimeError,match='macro .*changed'):
        camera_recovery.edit_choice(tmp_path/'edit',r,'body',camera_recovery.BODY)


@pytest.mark.parametrize('busy',['casting','moving','combat','flying'])
def test_macro_setup_waits_for_readiness_without_primary_input(monkeypatch,tmp_path,busy):
    r,path=setup(monkeypatch,tmp_path)
    if busy=='moving':r['movement']['speed']=7
    elif busy=='combat':r['movement']['in_combat']=True
    else:r['archaeology'][busy]=True
    monkeypatch.setattr(camera_recovery,'command_choice',lambda *_:pytest.fail('busy client cannot install'))
    assert not camera_recovery.apply_request(tmp_path,r) and path.exists()


@pytest.mark.parametrize('signal',['right_down','mouselooking'])
def test_ui_handoff_uses_camera_facts_before_clicking(monkeypatch,tmp_path,signal):
    r=row();r['farm_ui']['camera_input']={signal:True}
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    with pytest.raises(RuntimeError,match='camera mouse-look is still active'):
        farm_actions.stationary(r,r)
