"""Captured Solve requests and independent readers for canonical native history."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,stateful,action
from tools.client_compatibility.world.tests.test_inventory_packets import mask

CAPTURE=bytes.fromhex('018703c2da58bc00000000000000006b6301006604060000000000000000000000000000000000000000000000002100000000000000000000408e0100002d000000')


def modern(weights,moving=False):
    w=Writer().guid(3,13546827679136275138).pack('iiiIff',0,0,90987,394342,0.,0.)
    w.guid(0,0).pack('IIIB',0,0,0,0).bits(4,5).bits(moving,1).bits(len(weights),2).bits(0,1).flush()
    w.bits(0,28).bits(0,4).bits(0,7).guid(0,0).guid(0,0)
    for type,id,quantity in weights:w.bits(type,2).pack('iI',id,quantity)
    return w.finish()


def cast(codec,body):
    return stateful(codec,dict(guid=1,map=0),[action('cast_request','CMSG_CAST_SPELL',body)])[0]


def test_actual_solve_click_adds_native_weight_flag_and_preserves_currency_cost(codec):
    assert modern([(1,398,45)])==CAPTURE
    expected=struct.pack('<BiiBII',1,90987,0,12,0,1)+struct.pack('<BiI',1,398,45)
    assert cast(codec,CAPTURE)==['CMSG_CAST_SPELL',expected.hex()]


@pytest.mark.parametrize('weights',[[(1,398,33),(2,64394,1)],[(2,64394,1),(1,398,33)]])
def test_fragment_and_optional_keystone_weights_keep_native_widths_order_and_amounts(codec,weights):
    reply=cast(codec,modern(weights));r=Reader(bytes.fromhex(reply[1]))
    assert reply[0]=='CMSG_CAST_SPELL' and r.unpack('BiiBII')==(1,90987,0,12,0,2)
    assert [r.unpack('BiI') for _ in weights]==weights;r.end()


@pytest.mark.parametrize('weights',[
    [(0,398,45)],[(3,398,45)],[(1,398,0)],[(1,398,201)],[(1,1901,45)],
    [(1,-1,45)],[(2,64394,1)],[(1,398,33),(2,64394,0)],
    [(1,398,33),(2,64394,4)],[(1,398,33),(2,6948,1)],
    [(1,398,33),(1,398,12)],[(1,398,21),(2,64394,1),(2,64394,1)]])
def test_invalid_duplicate_or_non_native_weights_are_not_forwarded(codec,weights):
    assert 'error' in cast(codec,modern(weights))


def test_solve_rejects_every_truncation_extra_bytes_and_unverified_moving_variant(codec):
    for size in range(len(CAPTURE)):assert 'error' in cast(codec,CAPTURE[:size])
    assert 'error' in cast(codec,CAPTURE+b'x')
    assert 'error' in cast(codec,modern([(1,398,45)],moving=True))


def history(rows):
    w=Writer().bits(len(rows),22).flush()
    for row in rows:w.pack('iiI',*row)
    return w.finish()


def decode_history(body):
    r=Reader(body);assert r.unpack('HI')==(0,1) and r.bits(1)==1 and r.bits(1)==0;r.align()
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos and r.unpack('BBBI')==(1,0,3,1<<7)
    assert mask(r,46,first32=True)=={102,122};r.align()
    assert r.bits(1)==0 # Required optional PetStable presence for gate 102.
    assert r.bits(2)==3
    count=r.bits(32);assert [r.bits(1) for _ in range(count)]==[1]*count;r.align()
    rows=[]
    for _ in range(count):
        assert r.bits(4)==15;r.align();rows.append(r.unpack('IqI'))
    r.end();return rows


@pytest.mark.parametrize('count',[0,1,33,144])
def test_native_canonical_history_maps_to_owned_player_fields_with_complete_masks(codec,count):
    rows=[(i+1,i+2,1700000000+i) for i in range(count)]
    name,body=stateful(codec,dict(guid=1,map=0),[action('research_history','SMSG_SETUP_RESEARCH_HISTORY',history(rows))])[0]
    assert name=='SMSG_UPDATE_OBJECT'
    assert decode_history(bytes.fromhex(body))==[(id,time,times) for id,times,time in rows]


@pytest.mark.parametrize('body',[
    history([(260,1,1700000000)])[:-1],history([(260,1,1700000000)])+b'x',
    history([(260,1,1700000000),(260,2,1700000001)]),history([(0,1,1700000000)]),
    history([(260,0,1700000000)]),history([(260,1,0)]),history([(65536,1,1700000000)]),
    Writer().bits(145,22).flush().finish()])
def test_noncanonical_or_incomplete_history_is_rejected(codec,body):
    assert 'error' in stateful(codec,dict(guid=1,map=0),[action('research_history','SMSG_SETUP_RESEARCH_HISTORY',body)])[0]


def test_completion_notification_is_validated_before_requesting_canonical_repeat_counts(codec):
    assert stateful(codec,dict(guid=1,map=0),[action('research_complete','SMSG_RESEARCH_COMPLETE',
        struct.pack('<3I',1700000000,1,260))])==[None]
    for body in [b'',struct.pack('<3I',0,1,260),struct.pack('<3I',1700000000,0,260),
        struct.pack('<3I',1700000000,1,0),struct.pack('<3I',1700000000,1,260)+b'x']:
        assert 'error' in stateful(codec,dict(guid=1,map=0),[action('research_complete','SMSG_RESEARCH_COMPLETE',body)])[0]
