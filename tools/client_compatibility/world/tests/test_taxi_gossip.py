"""Native menu ownership, taxi mask units and multi-hop forwarding."""
from types import SimpleNamespace
import pytest
from tools.client_compatibility.world import taxi,gossip,gameobjects,creature_queries
from tools.client_compatibility.world.buffer import Reader,Writer


def owner():
    guid=(0xF13<<52)|(2409<<32)|123
    return SimpleNamespace(visible_units={guid:{'guid':guid,'map':0}}),guid


def test_native_taxi_menu_mask_and_known_multihop_route(monkeypatch):
    o,guid=owner();name,body=taxi.response(o,'SMSG_SHOWTAXINODES',Writer().pack('IQII',1,guid,1,2).raw(bytes([7,0])).finish())
    assert name=='SMSG_SHOW_TAXI_NODES'
    r=Reader(body);assert r.bits(1)==1 and r.unpack('II')==(1,1)
    assert r.guid()==gameobjects.modern_guid(guid,0) and r.unpack('I')==(1,)
    assert r.raw(8)==bytes([7,0,0,0,0,0,0,0]) and r.raw(8)==bytes([7,0,0,0,0,0,0,0]);r.end()
    monkeypatch.setattr(taxi,'paths',lambda:[{'source':1,'destination':2,'cost':5},{'source':2,'destination':3,'cost':6}])
    request=Writer().guid(*gameobjects.modern_guid(guid,0)).pack('III',3,0,0).finish()
    name,body=taxi.request(o,'CMSG_ACTIVATE_TAXI',request)
    assert name=='CMSG_ACTIVATETAXIEXPRESS' and Reader(body).unpack('QI3I')==(guid,3,1,2,3)
    with pytest.raises(ValueError):taxi.route(1,3,{1,3})


def test_gossip_choice_is_owned_and_preserves_native_option_index():
    o,guid=owner()
    native=Writer().pack('QIIIiBBI',guid,10,68,1,3,2,0,0).raw(b'Flight route\0\0').pack('I',0).finish()
    name,body=gossip.response(o,'SMSG_GOSSIP_MESSAGE',native)
    assert name=='SMSG_GOSSIP_MESSAGE' and body
    request=Writer().guid(*gameobjects.modern_guid(guid,0)).pack('Ii',10,3).bits(0,8).finish()
    assert gossip.request(o,'CMSG_GOSSIP_SELECT_OPTION',request)==('CMSG_GOSSIP_SELECT_OPTION',Writer().pack('QII',guid,10,3).raw(b'\0').finish())
    bad=Writer().guid(*gameobjects.modern_guid(guid,0)).pack('Ii',10,4).bits(0,8).finish()
    with pytest.raises(ValueError):gossip.request(o,'CMSG_GOSSIP_SELECT_OPTION',bad)


def test_creature_query_uses_visible_entry_and_returns_no_data_for_native_rejection():
    o,guid=owner()
    assert creature_queries.request(o,Writer().pack('I',2409).finish())==Writer().pack('IQ',2409,guid).finish()
    r=Reader(creature_queries.response(o,Writer().pack('I',2409|0x80000000).finish()))
    assert r.unpack('I')==(2409,) and r.bits(1)==0;r.end()
    assert creature_queries.request(o,Writer().pack('I',999).finish()) is None


def test_stale_creature_query_dispatch_keeps_session_open():
    import asyncio
    from tools.client_compatibility.world.service import Session
    session=Session.__new__(Session);session.owner=session;session.created=True
    session.world=session;session.visible_units={};sent=[]
    session.send=lambda name,body:sent.append((name,body))
    asyncio.run(session.handle('CMSG_QUERY_CREATURE',Writer().pack('I',999).finish()))
    assert sent==[('SMSG_QUERY_CREATURE_RESPONSE',Writer().pack('I',999).bits(0,1).finish())]
