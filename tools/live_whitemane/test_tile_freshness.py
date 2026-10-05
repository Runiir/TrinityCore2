import json
from types import SimpleNamespace
import pytest
from . import runtime,telemetry_tiles


def configured_clock(monkeypatch,tmp_path,refresh_movement):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    (tmp_path/'run').mkdir()
    (tmp_path/'run/observer_calibration.json').write_text(json.dumps({
        'archaeology_x':0,'archaeology_y':0,'archaeology_cell_size':1,'farm_ui':{}}))
    now=SimpleNamespace(value=10.)
    owner={'pid':123}
    clock=telemetry_tiles.GenerationClock({'M':1,'A':1,'F':1})
    clock.seen={'M':9.1,'A':9.9,'F':9.9}
    monkeypatch.setattr(telemetry_tiles,'_clock',clock)
    monkeypatch.setattr(telemetry_tiles,'_clock_owner',owner)
    monkeypatch.setattr(telemetry_tiles,'_last_capture',now.value)
    monkeypatch.setattr(telemetry_tiles,'surface',lambda:(None,owner))
    monkeypatch.setattr(telemetry_tiles,'image_region',lambda *_:None)
    def sleep(interval):now.value+=interval
    monkeypatch.setattr(telemetry_tiles,'time',SimpleNamespace(
        monotonic=lambda:now.value,time=lambda:now.value,sleep=sleep))
    frame=SimpleNamespace(count=0)
    def movement(*_):
        frame.count+=1
        return {'sequence':frame.count if refresh_movement else 1}
    monkeypatch.setattr(telemetry_tiles,'movement',movement)
    monkeypatch.setattr(telemetry_tiles.snapshot,'decode_image',lambda *_,**kwargs:{'sequence':frame.count+1})
    monkeypatch.setattr(telemetry_tiles.farm_ui,'decode_image',lambda *_,**kwargs:{'sequence':frame.count+1})
    return now,frame


def test_a_stale_movement_sample_waits_for_a_fresh_generation(monkeypatch,tmp_path):
    _,frame=configured_clock(monkeypatch,tmp_path,True)
    row=telemetry_tiles.observation(extension=False)
    assert frame.count==2
    assert row['movement']['sequence']==2 and row['channel_ages']['M']==pytest.approx(.075)


def test_a_frozen_movement_channel_remains_unusable(monkeypatch,tmp_path):
    now,_=configured_clock(monkeypatch,tmp_path,False)
    with pytest.raises(ValueError,match='stale local M tile'):
        telemetry_tiles.observation(extension=False)
    assert 13<now.value<13.1
