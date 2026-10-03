"""No-watch sentinel and stock faction indexes survive creation and owner deltas."""
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import mask

FIELD=INDEX['PLAYER_FIELD_WATCHED_FACTION_INDEX']


@pytest.mark.parametrize('native,modern',[(0xffffffff,-1),(0,0),(19,19),(255,255)])
def test_create_and_sparse_delta_preserve_native_watch_state(codec,native,modern):
    snapshot={'guid':1,'fields':{FIELD:native}}
    assert result(codec,op='object_values',snapshot=snapshot,character={})['ActivePlayerData']['WatchedFactionIndex']==modern
    body=bytes.fromhex(result(codec,op='watched_faction_update',snapshot=snapshot,changed={FIELD:native}))
    r=Reader(body);assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos and r.unpack('BBBI')==(1,0,3,1<<7)
    # UpdateFields.cpp at 6426c2b, ActivePlayerData::WriteUpdate: watched
    # scalar 97 is nested under gate 70. Bit 96 is LastWeekRank, not a gate.
    assert mask(r,46,first32=True)=={70,97};r.align();assert r.unpack('i')==(modern,);r.end()


def test_unrelated_delta_is_silent_and_invalid_native_indexes_are_rejected(codec):
    for native in [256,0x80000000,0xfffffffe]:
        snapshot={'guid':1,'fields':{FIELD:native}}
        assert 'error' in codec(op='object_values',snapshot=snapshot,character={})
        assert 'error' in codec(op='watched_faction_update',snapshot=snapshot,changed={FIELD:native})
    assert result(codec,op='watched_faction_update',snapshot={'guid':1,'fields':{}},changed={})==''
    assert result(codec,op='watched_faction_update',snapshot={'guid':1,'fields':{}},changed={INDEX['PLAYER_XP']:200})==''


def native_update(guid,value):
    w=Writer().pack('HI',0,1).pack('B',0).raw(bytes([1,guid]))
    masks=[0]*(FIELD//32+1);masks[FIELD//32]=1<<(FIELD%32)
    return w.pack('B',len(masks)).pack('I'*len(masks),*masks).pack('I',value).finish()


def test_live_update_dispatch_keeps_watch_changes_owner_only(codec):
    replies=result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'fields':{FIELD:0xffffffff}},gameobjects=[],
        units=[{'guid':2,'kind':4,'map':0,'fields':{},'public_character':{'name':'Harnesstwo','gender':0}}],
        actions=[{'fn':'object_updates','name':'SMSG_UPDATE_OBJECT','body':native_update(guid,value).hex()}
            for guid,value in [(1,19),(1,0xffffffff),(2,19)]])
    for reply,expected in zip(replies[:2],[19,-1]):
        assert reply[0]=='SMSG_UPDATE_OBJECT'
        r=Reader(bytes.fromhex(reply[1]));assert r.unpack('HI')==(0,1)
        assert r.bits(1)==1 and r.bits(1)==0
        assert r.unpack('I')[0]==len(r.data)-r.pos
        assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
        assert r.unpack('I')[0]==len(r.data)-r.pos and r.unpack('BBBI')==(1,0,3,1<<7)
        assert mask(r,46,first32=True)=={70,97};r.align();assert r.unpack('i')==(expected,);r.end()
    assert replies[2] is None
