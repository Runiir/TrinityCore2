import copy
from types import SimpleNamespace
from . import camera_zoom,controller_updates,runtime
from .test_farm_loop import row


def clock(monkeypatch):
    now=[0]
    monkeypatch.setattr(camera_zoom,'time',SimpleNamespace(monotonic=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s)))
    return now


def test_zoom_calibrates_wheel_notches_without_text_or_saved_view_commands(monkeypatch,tmp_path):
    before=row();before['farm_ui'].update(camera_zoom=5.55,frame_rate=30,sequence=0)
    current=copy.deepcopy(before);calls=[];clock(monkeypatch)
    def execute(title,action,args):
        assert action=='scroll';calls.append(args)
        current['farm_ui']['camera_zoom']+=1.5*args['steps']
        return {'completed':True}
    def observe(_):
        current['farm_ui']['sequence']+=1;return copy.deepcopy(current)
    monkeypatch.setattr(camera_zoom.inputs,'execute',execute)
    monkeypatch.setattr(camera_zoom,'observe',observe)
    result=camera_zoom.restore(tmp_path/'zoom',before,20,save_preset=2)
    assert result['confirmed'] and abs(result['after_zoom']-20)<=1
    assert calls[0]['steps']==1 and calls[1]['steps']==8
    assert result['measured_yards_per_notch']==1.5


def test_camera_collision_stops_wheel_retries_without_claiming_wide_zoom(monkeypatch,tmp_path):
    before=row();before['farm_ui']['camera_zoom']=5.55
    clock(monkeypatch);calls=[]
    monkeypatch.setattr(camera_zoom.inputs,'execute',lambda *args:calls.append(args) or {'completed':True})
    monkeypatch.setattr(camera_zoom,'observe',lambda _:before)
    result=camera_zoom.restore(tmp_path/'zoom',before,20)
    assert not result['confirmed'] and result['after_zoom']==5.55
    assert len(calls)==1 and 'no zoom progress' in result['reason']


def test_zoom_rechecks_combat_before_sending_any_wheel_input(monkeypatch,tmp_path):
    before=row();before['farm_ui']['camera_zoom']=5.55
    fresh=copy.deepcopy(before);fresh['movement']['in_combat']=True
    monkeypatch.setattr(camera_zoom.inputs,'execute',lambda *_:(_ for _ in ()).throw(AssertionError('combat changed')))
    monkeypatch.setattr(camera_zoom,'observe',lambda _:fresh)
    result=camera_zoom.restore(tmp_path/'zoom',before,20)
    assert result['interrupted'] and not result['inputs']


def test_wide_view_request_offers_native_zoom_and_confirms_from_facts(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before=row();before['farm_ui']['camera_zoom']=5.55
    path=tmp_path/'run/camera_zoom_request.json';receipt=tmp_path/'receipt.json'
    runtime.write(path,{'runtime':before['runtime'],'zoom':20,'receipt':str(receipt)})
    calls=[]
    monkeypatch.setattr(camera_zoom,'choose_restore',lambda folder,row,zoom:calls.append(zoom) or {'executed':True,'choice':'zoom'})
    assert controller_updates.apply_camera_request(tmp_path/'step',before)
    assert calls==[20]
    before['farm_ui']['camera_zoom']=20
    assert not controller_updates.apply_camera_request(tmp_path/'next',before)
    assert not path.exists()
