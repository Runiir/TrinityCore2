import struct
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_interaction_packets import call,HIGH


def test_ready_started_uses_pinned_signed_64_bit_milliseconds(codec):
    name,body=call(codec,'party_response','MSG_RAID_READY_CHECK',struct.pack('<Q',1))
    assert name=='SMSG_READY_CHECK_STARTED'
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,);assert r.guid()==(0,0)
    assert r.guid()==(1,HIGH)
    # PacketUtilities::Duration<Milliseconds> defaults to int64. An independent
    # decoder consumes all eight bytes; a uint32 serializer must fail this test.
    assert r.unpack('q')==(30000,);r.end()


def test_native_confirmation_excludes_foreign_and_duplicate_answers(codec):
    actions=[{'fn':'start','starter':1,'members':[1,2,3]},
        {'fn':'answer','member':99},{'fn':'answer','member':1},
        {'fn':'answer','member':2},{'fn':'answer','member':2},
        {'fn':'answer','member':3},{'fn':'finish'},{'fn':'answer','member':3},
        {'fn':'finish'}]
    rows=result(codec,op='ready_check',actions=actions)
    assert [r['accepted'] for r in rows]==[True,False,False,True,False,True,True,False,False]
    assert [r['pending'] for r in rows]==[2,2,2,1,1,0,0,0,0]
    assert rows[5]['complete'] and not rows[6]['active']


def test_timeout_finish_and_restart_do_not_reuse_previous_answers(codec):
    rows=result(codec,op='ready_check',actions=[{'fn':'start','starter':1,'members':[1,2]},
        {'fn':'finish'},{'fn':'start','starter':2,'members':[1,2]}])
    assert rows[1]['accepted'] and not rows[1]['active']
    assert rows[2]['active'] and rows[2]['pending']==1
    assert 'error' in codec(op='ready_check',actions=[{'fn':'start','starter':3,'members':[1,2]}])


def test_confirmation_and_completion_packet_identity(codec):
    name,body=call(codec,'party_response','MSG_RAID_READY_CHECK_CONFIRM',struct.pack('<QB',2,0))
    assert name=='SMSG_READY_CHECK_RESPONSE'
    r=Reader(bytes.fromhex(body));assert r.guid()==(0,0);assert r.guid()==(2,HIGH)
    assert r.bits(1)==0;r.end()
    assert call(codec,'party_response','MSG_RAID_READY_CHECK_FINISHED',b'')==['SMSG_READY_CHECK_COMPLETED','000000']
