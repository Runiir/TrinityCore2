"""Stock visibility requests and sparse player flags follow pinned wire readers."""
import pytest
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_interaction_packets import call
from tools.client_compatibility.world.tests.test_inventory_packets import mask


@pytest.mark.parametrize('name',['CMSG_SHOWING_HELM','CMSG_SHOWING_CLOAK'])
@pytest.mark.parametrize('shown',[0,1])
def test_stock_visibility_request_preserves_native_byte_boolean(codec,name,shown):
    assert call(codec,'appearance_request',name,bytes([shown]))==[name,bytes([shown]).hex()]


@pytest.mark.parametrize('body',[b'',b'\x00\x00',b'\x01\xff'])
def test_visibility_request_requires_exactly_one_byte(codec,body):
    assert 'error' in call(codec,'appearance_request','CMSG_SHOWING_HELM',body)


@pytest.mark.parametrize('visibility',[0,1])
def test_sparse_player_flags_include_visibility_and_preserve_other_flags(codec,visibility):
    flags=0x400|0x800|2
    fields={INDEX['PLAYER_FLAGS']:flags}
    body=result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=fields,visibility=visibility)
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,);assert r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('BBBI')==(visibility,0,3,1<<6)
    assert mask(r,5)=={0,9};assert r.bits(1)==0;r.align()
    assert r.unpack('I')==(flags,);r.end()


def test_unrelated_delta_does_not_repeat_player_flags(codec):
    fields={INDEX['PLAYER_FLAGS']:0x400}
    assert result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed={},visibility=1)==''


def test_appearance_handler_does_not_claim_other_requests(codec):
    assert call(codec,'appearance_request','CMSG_LOGOUT_REQUEST',b'') is None


def test_player_flags_precede_sparse_visible_item_data(codec):
    fields={INDEX['PLAYER_FLAGS']:0x400,INDEX['PLAYER_VISIBLE_ITEM_1_ENTRYID']:78688}
    body=result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=fields,visibility=1)
    r=Reader(bytes.fromhex(body));r.unpack('B');r.guid();r.unpack('IBBBI')
    assert mask(r,5)=={0,9,68,69};assert r.bits(1)==0;r.align()
    assert r.unpack('I')==(0x400,)
    assert r.bits(4)==3;r.align();assert r.unpack('i')==(78688,);r.end()
