import base64
import copy
import json
import struct
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.observation.telemetry import PACKET, checksum
from . import addon_relay as relay, snapshot, observe, runtime


def targeted(text, *, prefix=relay.PREFIX, name=b'Runiir\0', recipient=(0,0), logged=0):
    return (Writer().bits(len(prefix),5).bits(len(text),8).bits(logged,1).pack('i',7)
        .raw(prefix).raw(text).guid().guid(*recipient).pack('I',0)
        .bits(len(name),7).bits(0,7).raw(name).finish())


def movement(uptime=1000):
    body=PACKET.pack(b'TCM1',1,uptime,1449,100,200,300,0,100,3,0)[:-2]
    body+=checksum(body).to_bytes(2,'big')
    body+=relay.LIVE.pack(b'W1',64|256,1,10000100,10000200,10000000,0)[:-2]
    return body+checksum(body).to_bytes(2,'big')


def archaeology(uptime=1000):
    body=snapshot.HEADER.pack(b'TCA1',snapshot.HEADER.size+2,1,uptime,32,1,
        10000000,10000000,0,0,0,331,0,0,0,0)
    return body+checksum(body).to_bytes(2,'big')


def fragments(kind,sequence,body):
    encoded=base64.b64encode(body).decode();parts=[encoded[i:i+200] for i in range(0,len(encoded),200)]
    return [f'{kind}|{sequence}|{i+1}|{len(parts)}|{value}' for i,value in enumerate(parts)]


def test_only_own_unlogged_addon_prefix_and_recipient_are_decoded():
    assert relay.targeted(targeted(b'M|1|1|1|a'))=='M|1|1|1|a'
    assert relay.targeted(targeted(b'ignored',prefix=b'Other')) is None
    assert relay.targeted(targeted(b'own',recipient=(7,8)),(7,8))=='own'
    for changes in ({'name':b'Other\0'},{'recipient':(9,10)},{'logged':1}):
        with pytest.raises(ValueError):relay.targeted(targeted(b'own',**changes),(7,8))


def test_out_of_order_ui_fragments_are_atomic_and_old_or_duplicate_generations_do_not_refresh_age():
    assembler=relay.Assembler();parts=fragments('U',2,json.dumps({'text':'x'*800}).encode())
    for part in reversed(parts[1:]):assert not assembler.packet(part,1)
    assert 'U' not in assembler.channels
    assert assembler.packet(parts[0],2)
    assert assembler.channels['U']['observed_at']==1
    for sequence in (1,2):
        for part in fragments('U',sequence,b'{}'):assert not assembler.packet(part,3)
    assert assembler.channels['U']['observed_at']==1


def test_bad_checksum_conflicting_fragments_and_invalid_base64_are_rejected():
    assembler=relay.Assembler();body=bytearray(movement());body[-1]^=1
    with pytest.raises(ValueError,match='checksum'):assembler.packet(fragments('M',1,body)[0],1)
    assembler.packet('U|3|1|2|abcd',1)
    with pytest.raises(ValueError,match='disagree'):assembler.packet('U|3|1|2|efgh',2)
    with pytest.raises(ValueError):assembler.packet('U|4|1|1|!!!',2)
    for i in range(20):assembler.packet(f'U|{10+i}|1|2|e30=',3)
    assert len(assembler.pending)==8


def fixture(monkeypatch,tmp_path):
    owner={'pid':1,'start_ticks':'a'};assembler=relay.Assembler()
    for kind,seq,data in [('M',1,movement()),('A',2,archaeology(1100)),
        ('U',3,b'{"route":{"kind":"dig"}}'),('F',4,b'{"ui_version":3}')]:
        for part in fragments(kind,seq,data):assembler.packet(part,10)
    (tmp_path/'run').mkdir()
    runtime.write(tmp_path/'run/addon_state.json',assembler.state(owner,{'pid':2,'start_ticks':'b'}))
    runtime.write(tmp_path/'run/bearing_reader.json',{'status':'ready','pid':2,'start_ticks':'b'})
    monkeypatch.setattr(runtime,'proc_start',lambda _:'b')
    return owner,assembler


def test_current_reader_freshness_ui_generation_and_fast_world_mode(monkeypatch,tmp_path):
    owner,assembler=fixture(monkeypatch,tmp_path)
    row=relay.observation(owner,tmp_path,10.1)
    assert row['archaeology']['world']=={'instance':1,'north':1,'west':2}
    assert row['archaeology']['can_survey'] and row['farm_ui']['route']['kind']=='dig'
    assert row['frame'] is None
    with pytest.raises(ValueError,match='stale M'):relay.observation(owner,tmp_path,11)
    monkeypatch.setattr(runtime,'proc_start',lambda _:'different')
    with pytest.raises(ValueError,match='owned reader'):relay.observation(owner,tmp_path,10.1)
    monkeypatch.setattr(runtime,'proc_start',lambda _:'b')
    assembler.packet(fragments('F',5,b'{"ui_version":99}')[0],10)
    runtime.write(tmp_path/'run/addon_state.json',assembler.state(owner,{'pid':2,'start_ticks':'b'}))
    assert relay.observation(owner,tmp_path,10.1)['farm_ui'] is None


def test_required_direct_transport_never_requests_a_screenshot_even_when_stale(monkeypatch,tmp_path):
    owner,_=fixture(monkeypatch,tmp_path)
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(runtime,'owned_process',lambda:owner)
    monkeypatch.setattr(runtime,'screenshot',lambda _:pytest.fail('must not request a screenshot'))
    runtime.write(tmp_path/'run/observation_mode.json',{'transport':'addon_relay'})
    monkeypatch.setattr(relay,'observation',lambda *_: {'archaeology':{},'owned_pose':None,'frame':None})
    assert observe.observe(tmp_path/'output.png')['frame'] is None
    def unavailable(*_):raise ValueError('stale')
    monkeypatch.setattr(relay,'observation',unavailable)
    with pytest.raises(RuntimeError,match='stale'):observe.observe(tmp_path/'output.png')


def test_new_reader_without_a_height_sample_keeps_public_observation_available(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    assert observe.attach_pose({'archaeology':{}})['owned_pose'] is None
