"""Stock visibility requests and sparse player flags follow pinned wire readers."""
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,stateful,action
from tools.client_compatibility.world.tests.test_interaction_packets import call
from tools.client_compatibility.world.tests.test_inventory_packets import mask


@pytest.mark.parametrize('name',['CMSG_SHOWING_HELM','CMSG_SHOWING_CLOAK'])
@pytest.mark.parametrize('encoded,expected',[(0,0),(1,1),(0x80,1)])
def test_stock_visibility_request_normalizes_native_byte_boolean(codec,name,encoded,expected):
    # Actual 60895 ShowHelm(true) is 0x80. Native ByteBuffer reads signed char
    # >0, so forwarding the high-bit byte falsely hides the helm again.
    assert call(codec,'appearance_request',name,bytes([encoded]))==[name,bytes([expected]).hex()]


@pytest.mark.parametrize('body',[b'',b'\x00\x00',b'\x01\xff'])
def test_visibility_request_requires_exactly_one_byte(codec,body):
    assert 'error' in call(codec,'appearance_request','CMSG_SHOWING_HELM',body)


@pytest.mark.parametrize('visibility',[0,1])
@pytest.mark.parametrize('hidden,extended',[(0,0),(0x400,0x80),(0x800,0x100),(0xc00,0x180)])
def test_sparse_player_flags_move_classic_visibility_to_extended_flags(codec,visibility,hidden,extended):
    # HermesProxy 841a26f PlayerDefines/UpdateHandler: Classic visibility is
    # PlayerFlagsEx; the old 0x400/0x800 bits mean warmode in PlayerFlags.
    flags=hidden|2|0x10000000
    fields={INDEX['PLAYER_FLAGS']:flags}
    body=result(codec,op='guild_update',snapshot={'guid':1,'fields':fields},character={},changed=fields,visibility=visibility)
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,);assert r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('BBBI')==(visibility,0,3,1<<6)
    assert mask(r,5)=={0,9,10};assert r.bits(1)==0;r.align()
    assert r.unpack('II')==(2|0x10000000,extended);r.end()


@pytest.mark.parametrize('hidden,extended',[(0,0),(0x400,0x80),(0x800,0x100),(0xc00,0x180)])
def test_created_player_uses_the_same_classic_visibility_mapping(codec,hidden,extended):
    fields={INDEX['PLAYER_FLAGS']:hidden|4}
    player=result(codec,op='object_values',snapshot={'fields':fields},character={})['PlayerData']
    assert player['PlayerFlags']==4 and player['PlayerFlagsEx']==extended


def test_native_flag_dispatch_emits_one_public_block_with_extended_visibility(codec):
    index=INDEX['PLAYER_FLAGS'];words=[0]*(index//32+1);words[index//32]=1<<(index%32)
    body=Writer().pack('HI',0,1).pack('B',0).raw(bytes([1,1])).pack('B',len(words))
    body.pack('I'*len(words),*words).pack('I',0xc02)
    reply=stateful(codec,{'guid':1,'map':0},[action('object_updates','SMSG_UPDATE_OBJECT',body.finish())],
        snapshot={'guid':1,'map':0,'fields':{}})[0]
    assert reply[0]=='SMSG_UPDATE_OBJECT';r=Reader(bytes.fromhex(reply[1]))
    assert r.unpack('HI')==(0,1);assert r.bits(1)==1 and r.bits(1)==0
    block=Reader(r.raw(r.unpack('I')[0]));r.end()
    assert block.unpack('B')==(0,) and block.guid()==(1,player_high())
    assert block.unpack('I')[0]==len(block.data)-block.pos
    assert block.unpack('BBBI')==(1,0,3,1<<6)
    assert mask(block,5)=={0,9,10};assert block.bits(1)==0;block.align()
    assert block.unpack('II')==(2,0x180);block.end()


def test_unrelated_delta_does_not_repeat_player_flags(codec):
    fields={INDEX['PLAYER_FLAGS']:0x400}
    assert result(codec,op='guild_update',snapshot={'guid':1,'fields':fields},character={},changed={},visibility=1)==''


def test_appearance_handler_does_not_claim_other_requests(codec):
    assert call(codec,'appearance_request','CMSG_LOGOUT_REQUEST',b'') is None


def test_inventory_does_not_duplicate_the_public_player_flag_block(codec):
    fields={INDEX['PLAYER_FLAGS']:0x400,INDEX['PLAYER_VISIBLE_ITEM_1_ENTRYID']:78688}
    body=result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=fields,visibility=1)
    r=Reader(bytes.fromhex(body));r.unpack('B');r.guid();r.unpack('IBBBI')
    assert mask(r,5)=={68,69};assert r.bits(1)==0;r.align()
    assert r.bits(4)==3;r.align();assert r.unpack('i')==(78688,);r.end()
