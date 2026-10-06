import copy
from types import SimpleNamespace
from . import camera_zoom,camera_navigation,controller_updates,runtime,farm_actions
from .test_farm_loop import row


def test_zoom_delta_uses_the_measured_distance_and_confirms_before_saving(monkeypatch,tmp_path):
    before=row();before['farm_ui'].update(camera_zoom=5.55,frame_rate=30)
    after=copy.deepcopy(before);after['farm_ui']['camera_zoom']=20
    calls=[]
    monkeypatch.setattr(camera_zoom.inputs,'execute',lambda *args:calls.append(args[-1]) or {'completed':True})
    monkeypatch.setattr(camera_zoom,'observe',lambda _:after)
    result=camera_zoom.restore(tmp_path/'zoom',before,20,save_preset=2)
    assert result['confirmed'] and result['after_zoom']==20
    assert calls[0]['text']=='/run CameraZoomOut(14.45)'
    assert calls[1]['text']=='/run if SaveView then SaveView(2) end'


def test_camera_collision_does_not_claim_wide_zoom_or_save_a_failed_view(monkeypatch,tmp_path):
    before=row();before['farm_ui']['camera_zoom']=5.55
    clock=[0];calls=[]
    monkeypatch.setattr(camera_zoom,'time',SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+s)))
    monkeypatch.setattr(camera_zoom.inputs,'execute',lambda *args:calls.append(args[-1]) or {'completed':True})
    monkeypatch.setattr(camera_zoom,'observe',lambda _:before)
    result=camera_zoom.restore(tmp_path/'zoom',before,20,save_preset=2)
    assert not result['confirmed'] and result['after_zoom']==5.55
    assert len(calls)==1


def test_wide_view_request_is_selected_by_laya_and_confirmed_from_facts(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before=row();before['farm_ui']['camera_zoom']=5.55
    path=tmp_path/'run/camera_zoom_request.json';receipt=tmp_path/'receipt.json'
    runtime.write(path,{'runtime':before['runtime'],'zoom':20,'receipt':str(receipt)})
    calls=[]
    def choose(folder,row,command,goal,label):
        calls.append(command);return {'executed':True,'choice':'command','selected_by':'Laya'}
    monkeypatch.setattr(farm_actions,'command_choice',choose)
    assert controller_updates.apply_camera_request(tmp_path/'step',before)
    assert calls==['/run CameraZoomOut(14.45)']
    before['farm_ui']['camera_zoom']=20
    assert not controller_updates.apply_camera_request(tmp_path/'next',before)
    assert not path.exists()
