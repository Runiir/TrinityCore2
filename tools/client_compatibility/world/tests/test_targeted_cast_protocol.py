"""Replay an ordinary captured enemy-target cast through native visibility authority."""
import json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world import movement
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

CAPTURE=json.loads((Path(__file__).parent/'fixtures/heroic_throw_60895.json').read_text())


def translate(codec,units):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1},
        units=units,gameobjects=[],actions=[{'fn':'cast_request','name':'CMSG_CAST_SPELL','body':CAPTURE['body']}])


def test_captured_heroic_throw_reaches_exact_native_visible_target(codec):
    target=CAPTURE['target'];body=translate(codec,[target])
    octets=target['guid'].to_bytes(8,'little')
    packed=bytes([sum(bool(v)<<i for i,v in enumerate(octets))])+bytes(v for v in octets if v)
    expected=struct.pack('<BiiBI',1,CAPTURE['spell'],CAPTURE['native_misc'],CAPTURE['native_flags'],2)+packed
    state=movement.parse(bytes.fromhex(CAPTURE['movement_body']),1)
    name,encoded=movement.encode('CMSG_MOVE_HEARTBEAT',1,state)
    assert body==[[name,encoded.hex()],['CMSG_CAST_SPELL',expected.hex()]]


@pytest.mark.parametrize('target',[None,{'guid':9,'map':0,'kind':4},
    {**CAPTURE['target'],'map':1}])
def test_absent_different_or_other_map_target_stays_rejected(codec,target):
    body=translate(codec,[] if target is None else [target])
    assert len(body)==1 and isinstance(body[0],dict) and body[0].get('error')
