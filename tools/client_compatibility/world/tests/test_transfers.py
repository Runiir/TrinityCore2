"""Transfer order and GUID/counter guards against pinned native wire fixtures."""
from types import SimpleNamespace
import struct
import asyncio
import pytest
from tools.client_compatibility.world import transfers
from tools.client_compatibility.world.buffer import Reader,Writer,player_high


def owner():
    return SimpleNamespace(character={'guid':1,'map':0},created=True,
        self_snapshot={'movement':{'position':(10,20,30,1)}})


def test_native_near_teleport_and_client_ack():
    # Native: only GUID byte zero exists; its XOR value is zero.
    o=owner();native=bytes([0x40,0])+struct.pack('<IfffBf',7,100,2,300,0,200)
    name,data=transfers.response(o,'MSG_MOVE_TELEPORT',native)
    r=Reader(data);assert name=='SMSG_MOVE_TELEPORT'
    assert r.guid()==(1,player_high())
    assert r.unpack('I4fB')==(7,100,200,300,2,0) and r.bits(2)==0;r.end()
    ack=Writer().guid(1,player_high()).pack('II',7,1234).finish()
    name,data=transfers.request(o,'CMSG_MOVE_TELEPORT_ACK',ack)
    assert name=='MSG_MOVE_TELEPORT_ACK'
    assert data==struct.pack('<II',7,1234)+bytes([0x40,0])
    assert o.latest_movement==(100,200,300,2)
    with pytest.raises(ValueError):transfers.request(o,'CMSG_MOVE_TELEPORT_ACK',ack)


def test_far_transfer_requires_acknowledgements_in_order_and_60895_world_size():
    o=owner()
    name,data=transfers.response(o,'SMSG_TRANSFER_PENDING',Writer().bits(0,2).pack('i',530).finish())
    assert data==struct.pack('<i3fB',530,10,20,30,0)
    token=Writer().pack('I',1).bits(1,1).finish()
    assert transfers.response(o,'SMSG_SUSPEND_TOKEN',token)[1]==struct.pack('<IB',1,64)
    with pytest.raises(ValueError):transfers.request(o,'CMSG_WORLD_PORT_RESPONSE',b'')
    with pytest.raises(ValueError):transfers.request(o,'CMSG_SUSPEND_TOKEN_RESPONSE',struct.pack('<I',2))
    assert transfers.request(o,'CMSG_SUSPEND_TOKEN_RESPONSE',struct.pack('<I',1))[0]=='CMSG_SUSPEND_TOKEN_RESPONSE'
    _,data=transfers.response(o,'SMSG_NEW_WORLD',struct.pack('<fffif',100,2,300,530,200))
    assert len(data)==40 and struct.unpack('<i4fI3fi',data)==(530,100,200,300,2,16,0,0,0,1)
    assert not o.created and o.character['map']==530
    assert transfers.request(o,'CMSG_WORLD_PORT_RESPONSE',b'')==('MSG_MOVE_WORLDPORT_ACK',b'')


def test_captured_world_port_on_owned_realm_connection_and_duplicate_rejection():
    from tools.client_compatibility.world.service import Session
    sent=[];o=owner();o.owner=o;o.world=object();o.crypt=SimpleNamespace(key=b'test')
    o.native=SimpleNamespace(send=lambda *v:sent.append(v))
    o.pending_far={'map':530,'sequence':1,'reason':1,'stage':'new_world'};o.created=False
    asyncio.run(Session.handle(o,'CMSG_WORLD_PORT_RESPONSE',b''))
    assert sent==[('MSG_MOVE_WORLDPORT_ACK',b'')] and o.pending_far['stage']=='entering'
    with pytest.raises(ValueError):asyncio.run(Session.handle(o,'CMSG_WORLD_PORT_RESPONSE',b''))
    with pytest.raises(ValueError):asyncio.run(Session.handle(o,'CMSG_SUSPEND_TOKEN_RESPONSE',struct.pack('<I',1)))
