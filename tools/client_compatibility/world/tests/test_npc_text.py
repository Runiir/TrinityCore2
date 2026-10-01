from types import SimpleNamespace
import pytest
from tools.client_compatibility.world import npc_text,gameobjects
from tools.client_compatibility.world.buffer import Reader,Writer


def test_native_text_query_ownership_and_broadcast_response(monkeypatch):
    guid=(0xF13<<52)|(2409<<32)|123
    owner=SimpleNamespace(visible_units={guid:{'map':0}},gossip_menu={'guid':guid,'text_id':7778})
    body=Writer().pack('I',7778).guid(*gameobjects.modern_guid(guid,0)).finish()
    assert npc_text.request(owner,body)==Writer().pack('IQ',7778,guid).finish()
    native=Writer().pack('I',7778)
    for i in range(8):native.pack('f',1 if i==0 else 0).raw(b'Greeting\0Greeting\0').pack('7I',*([0]*7))
    monkeypatch.setattr(npc_text,'broadcasts',lambda _: [10753]+[0]*7)
    r=Reader(npc_text.response(owner,native.finish()))
    assert r.unpack('I')==(7778,) and r.bits(1)==1 and r.unpack('I')==(64,)
    assert r.unpack('8f8I')==(1,*([0]*7),10753,*([0]*7));r.end()
    assert npc_text.response(owner,native.finish()) is None
    with pytest.raises(ValueError):npc_text.request(owner,Writer().pack('I',999).guid(*gameobjects.modern_guid(guid,0)).finish())
