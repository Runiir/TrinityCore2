"""Partial captures are quarantined; retrying observation never repeats input."""
from types import SimpleNamespace
import hashlib
import pytest
from PIL import Image
from tools.second_client import ctl
from tools.client_compatibility import interaction_capture as capture
from tools.client_compatibility import interaction_observation as observation
from tools.client_compatibility import interaction_control_target as targets
from tools.client_compatibility import interaction_operations as operations
from tools.client_compatibility import interaction_trial as trials
from tools.client_compatibility.observation import interactions


def fixture(monkeypatch,tmp_path,guid='owned'):
    t=SimpleNamespace(out=tmp_path,guid='owned',receipt={},persist=lambda:None,
        combat_observation_deadline=None)
    state={'guid':guid,'build':60895,'mode':'controls','sequence':2,'panels':[],
        'control_count':1,'page':1,'page_size':18,'control_snapshot':123,
        'controls':[{'name':'owned_button'}]}
    movement={'in_world':True,'dead':False,'in_combat':False,'on_taxi':False,'health_percent':100}
    samples=[]
    def shot(path):
        from pathlib import Path
        path=Path(path);samples.append(path)
        if len(samples)==1:path.write_bytes(b'partial screenshot')
        else:Image.new('RGB',(1280,720)).save(path)
        return {'file':path.name,'monitor':{'second_monitor_verified':True}}
    monkeypatch.setattr(observation,'shot',shot)
    monkeypatch.setattr(ctl,'shot',shot)
    monkeypatch.setattr(capture.owned_input,'focus',lambda:{'second_monitor_verified':True})
    monkeypatch.setattr(observation,'decode_image',lambda _:state)
    monkeypatch.setattr(targets,'decode_image',lambda _:state)
    monkeypatch.setattr(interactions,'decode_image',lambda _:state)
    monkeypatch.setattr(trials,'decode_image',lambda _:state)
    monkeypatch.setattr(trials,'decode_movement',lambda *a,**k:movement)
    monkeypatch.setattr(observation.time,'sleep',lambda _:None)
    def retain(path,target,decoded,loaded=None):
        assert loaded is not None and loaded.size==(1280,720) and decoded==state
        loaded.save(target);path.unlink()
        return {'file':target.name}
    monkeypatch.setattr(targets,'retain_control_pixels',retain)
    monkeypatch.setattr(operations,'retain_control_pixels',retain)
    return t,samples


def read(t,reader):
    if reader=='page':return observation.read_current_page(t,'retry','controls')
    if reader=='target':return targets.target(t,'retry',lambda c:c['name']=='owned_button')
    if reader=='catalog':return operations.controls(t)
    return trials.Trial.observe(t,'retry',mode='controls')


@pytest.mark.parametrize('reader',['page','target','catalog','state'])
def test_partial_png_then_valid_capture_keeps_only_attributable_images(monkeypatch,tmp_path,reader):
    t,samples=fixture(monkeypatch,tmp_path)
    assert read(t,reader)
    assert len(samples)==2
    row=t.receipt['capture_failures'][0]
    assert row['input_replayed'] is False and row['accepted_as_image'] is False
    assert (tmp_path/row['capture_file']).read_bytes()==b'partial screenshot'
    assert row['sha256']==hashlib.sha256(b'partial screenshot').hexdigest()
    for path in tmp_path.glob('*.png'):
        with Image.open(path) as image:image.verify()


@pytest.mark.parametrize('reader',['page','target','catalog','state'])
def test_capture_retry_does_not_admit_a_foreign_actor(monkeypatch,tmp_path,reader):
    t,samples=fixture(monkeypatch,tmp_path,guid='foreign')
    with pytest.raises(RuntimeError,match='another actor|identity mismatch|owned active character'):
        read(t,reader)
    assert len(samples)==2 and not t.receipt.get('control_frames')


@pytest.mark.parametrize('reader',['page','target','catalog','state'])
def test_unreadable_capture_deadline_never_qualifies_or_keeps_a_malformed_png(monkeypatch,tmp_path,reader):
    t,samples=fixture(monkeypatch,tmp_path)
    ticks=iter([0,1,60] if reader in ('target','catalog') else [0,60])
    monkeypatch.setattr(observation.time,'monotonic',lambda:next(ticks))
    with pytest.raises(RuntimeError,match='decodable|not observed|deadline exceeded'):
        read(t,reader)
    assert len(samples)==1 and not list(tmp_path.glob('*.png'))
    assert not t.receipt.get('completed') and not t.receipt.get('control_frames')


def test_repeated_identical_capture_error_retains_first_bytes_only(monkeypatch,tmp_path):
    t,_=fixture(monkeypatch,tmp_path);path=tmp_path/'scratch.png'
    for data in (b'first',b'second'):
        path.write_bytes(data);capture.retain_capture_failure(t,'same',path,OSError('partial'))
    assert t.receipt['capture_failures'][0]['count']==2
    assert (tmp_path/'capture_failure_0.bin').read_bytes()==b'first'


def test_capture_quarantine_refuses_foreign_files(monkeypatch,tmp_path):
    out=tmp_path/'owned';out.mkdir();t,_=fixture(monkeypatch,out)
    foreign=tmp_path/'foreign.png';foreign.write_bytes(b'keep')
    with pytest.raises(ValueError,match='belong to this trial'):
        capture.retain_capture_failure(t,'foreign',foreign,OSError('partial'))
    assert foreign.read_bytes()==b'keep' and not t.receipt
