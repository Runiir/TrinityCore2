"""Native visible-player movement preserves positions and fall data, with no owner writes."""
from copy import deepcopy
import math
import pytest
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.movement import encode,parse
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_public_players import snapshot


def state(**updates):
    return {'flags':2,'flags2':0,'time':1234,'position':[-8900,-100,82,2.3],
        'pitch':0,'fall':False,'fall_direction':False,'fall_time':0,
        'zspeed':0,'sin':0,'cos':0,'xyspeed':0,**updates}


def run(codec,body,units=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},
        snapshot={'guid':1,'kind':4,'map':0,'fields':{}},
        units=[snapshot()] if units is None else units,gameobjects=[],
        actions=[{'fn':'public_player_movement','name':'SMSG_MOVE_UPDATE','body':body.hex()}])[0]


@pytest.mark.parametrize('movement',[
    state(),state(flags=0,position=[-8901,-110,83,0]),
    state(flags=0x1000000|2,flags2=0x410,pitch=.4),
    state(flags=0x800|2,fall=True,fall_direction=True,fall_time=500,zspeed=3.1,sin=.5,cos=.866,xyspeed=7),
    state(flags=0,fall=True,fall_time=1,zspeed=-2),
])
def test_public_movement_preserves_native_kinematics(codec,movement):
    _,native=encode('SMSG_MOVE_UPDATE',2,movement,acknowledgement=True)
    reply=run(codec,native);assert reply[0]=='SMSG_MOVE_UPDATE'
    wire=bytes.fromhex(reply[1]);r=Reader(wire)
    assert r.guid()==(2,player_high())
    decoded=parse(wire,2)
    assert decoded.pop('standing_gameobject') is None
    assert decoded.pop('position')==pytest.approx(movement['position'])
    assert decoded==pytest.approx({k:v for k,v in movement.items() if k!='position'})


def test_public_movement_requires_current_player_visibility(codec):
    _,native=encode('SMSG_MOVE_UPDATE',2,state(),acknowledgement=True)
    assert run(codec,native,[]) is None
    creature=deepcopy(snapshot());creature['kind']=3
    assert run(codec,native,[creature]) is None
    _,own=encode('SMSG_MOVE_UPDATE',1,state(),acknowledgement=True)
    visible_owner=deepcopy(snapshot());visible_owner['guid']=1
    assert run(codec,own,[visible_owner]) is None


@pytest.mark.parametrize('position',[[math.nan,0,0,0],[0,math.inf,0,0],[17068,0,0,0]])
def test_public_movement_rejects_bad_coordinates(codec,position):
    _,native=encode('SMSG_MOVE_UPDATE',2,state(position=position),acknowledgement=True)
    assert 'coordinates' in run(codec,native)['error']


def test_public_movement_rejects_truncation_extra_bytes_and_nonplayer_guid(codec):
    _,native=encode('SMSG_MOVE_UPDATE',2,state(),acknowledgement=True)
    assert all('error' in run(codec,native[:n]) for n in range(len(native)))
    assert 'error' in run(codec,native+b'\0')
    _,bad=encode('SMSG_MOVE_UPDATE',0x123400000002,state(),acknowledgement=True)
    assert 'identity' in run(codec,bad)['error']
