"""Pinned native inspection and trade fixtures, public authority and modern decoding."""
import json
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_public_players import snapshot,PROFILE


def actions(codec,operations,units=None):
    peer=snapshot();peer['public_character']=PROFILE
    return result(codec,op='stateful',character={'guid':1,'map':0},
        snapshot={'guid':1,'kind':4,'map':0,'fields':{}},units=[peer] if units is None else units,gameobjects=[],
        actions=[{'fn':fn,'name':name,'body':body.hex()} for fn,name,body in operations])


def identity():return Writer().guid(2,player_high()).finish()


def inspect_body():
    # Native Player::{BuildPlayerTalentsInfoData,BuildEnchantmentsInfoData}.
    return Writer().pack('QIBBI BIBB H I I H H',2,5,1,0,161,1,42,2,1,123,1,39,1,234)\
        .pack('hB I',-3,0,99).finish()


def test_inspect_translates_native_gear_talent_glyph_and_public_identity(codec):
    native=inspect_body()
    replies=actions(codec,[('inspect_request','CMSG_INSPECT',identity()),
        ('inspect_response','SMSG_INSPECT_TALENT',native),('inspect_response','SMSG_INSPECT_TALENT',native)])
    assert replies[0]==['CMSG_INSPECT',struct.pack('<Q',2).hex()];assert replies[2] is None
    assert replies[1][0]=='SMSG_INSPECT_RESULT';r=Reader(bytes.fromhex(replies[1][1]))
    assert r.guid()==(2,player_high());assert r.unpack('iI')==(161,1)
    length=r.bits(6);assert r.unpack('BBBI')==(0,1,1,0);assert r.raw(length)==b'Harnesstwo'
    assert r.guid()==(0,0);assert r.unpack('BII')==(0,0,0);assert r.unpack('iii')==(39,99,-3)
    assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.align()
    assert r.bits(1)==1 and r.bits(4)==1 and r.bits(2)==0
    assert r.unpack('IB')==(234,0)
    assert r.unpack('IiBHHII3H')==(3,0,0,0,0,0,0,0,0,0)
    assert r.unpack('IBI')==(5,0,1)
    assert r.unpack('BIBIBI')==(1,1,1,1,0,161)
    assert r.unpack('IIH')==(42,2,123);assert r.bits(1)==0;r.align()
    assert r.bits(2)==0;r.align()
    for i in range(9):assert r.unpack('B')==(i,);assert r.unpack('16I')==(0,)*16;assert r.bits(1)==0;r.align()
    r.end()


def test_inspect_requires_requested_visible_native_player(codec):
    native=inspect_body()
    assert actions(codec,[('inspect_response','SMSG_INSPECT_TALENT',native)])[0] is None
    assert actions(codec,[('inspect_request','CMSG_INSPECT',identity())],[])[0] is None
    for n in range(8,len(native)):
        reply=actions(codec,[('inspect_request','CMSG_INSPECT',identity()),
            ('inspect_response','SMSG_INSPECT_TALENT',native[:n])])[1]
        assert 'error' in reply


STATUS={0:2,2:23,3:19,4:14,5:18,6:4,7:20,9:8,10:21,12:1,13:17,16:10,17:6,
    18:5,19:24,20:11,21:0,22:9,23:3,24:25,25:7,26:22,27:15,29:16,31:12}


@pytest.mark.parametrize('native,modern',STATUS.items())
def test_trade_statuses_use_modern_semantics_and_payloads(codec,native,modern):
    w=Writer().bits(0,1).bits(native,5)
    if native==12:
        for i in [2,4,6,0,1,3,7,5]:w.bits(i==0,1)
        w.pack('B',3) # Native player counter 2, shuffled XOR octets.
    elif native==0:w.pack('I',123)
    elif native==31:w.bits(1,1).pack('ii',1,39)
    elif native in [2,26]:w.pack('B',6)
    elif native in [19,24]:w.pack('ii',384,5)
    reply=actions(codec,[('trade_response','SMSG_TRADE_STATUS',w.finish())])[0]
    assert reply[0]=='SMSG_TRADE_STATUS';r=Reader(bytes.fromhex(reply[1]))
    assert r.bits(1)==0 and r.bits(5)==modern
    if native==12:assert r.guid()==(2,player_high());assert r.guid()==(0,0)
    elif native==0:assert r.unpack('I')==(123,)
    elif native==31:assert r.bits(1)==1;assert r.unpack('ii')==(1,39)
    elif native in [2,26]:assert r.unpack('B')==(6,)
    elif native in [19,24]:assert r.unpack('ii')==(384,5)
    r.end()


def test_trade_requests_retain_inventory_mapping_and_visible_authority(codec):
    replies=actions(codec,[('trade_request','CMSG_INITIATE_TRADE',identity()),
        ('trade_request','CMSG_SET_TRADE_ITEM',bytes([0,255,35])),
        ('trade_request','CMSG_SET_TRADE_GOLD',struct.pack('<Q',123)),
        ('trade_request','CMSG_CANCEL_TRADE',b'')])
    assert replies==[['CMSG_INITIATE_TRADE',bytes([128,3]).hex()],
        ['CMSG_SET_TRADE_ITEM',bytes([23,0,255]).hex()],['CMSG_SET_TRADE_GOLD',struct.pack('<Q',123).hex()],['CMSG_CANCEL_TRADE','']]
    assert actions(codec,[('trade_request','CMSG_INITIATE_TRADE',identity())],[])[0] is None
    for name,body in [('CMSG_BEGIN_TRADE',b'x'),('CMSG_SET_TRADE_ITEM',bytes([7,255,35])),
        ('CMSG_ACCEPT_TRADE',b'')]:assert 'error' in actions(codec,[('trade_request',name,body)])[0]


def trade_item(socket=0):
    w=Writer().pack('IiQiIiBI',123,0,10,0,4,0,1,5).bits(1,22)
    # Gift/author GUIDs absent, with native unwrapped item.
    w.bits(0,2).bits(1,1).bits(0,1).bits(0,9).bits(0,5)
    w.pack('i3iIiI4i',234,socket,0,0,0,0,0,-3,0,-1,99)
    return w.pack('iiB',64394,2,0).finish()


def test_trade_item_update_preserves_stack_property_gold_and_enchantment(codec):
    reply=actions(codec,[('trade_response','SMSG_TRADE_UPDATED',trade_item())])[0]
    assert reply[0]=='SMSG_TRADE_UPDATED';r=Reader(bytes.fromhex(reply[1]))
    assert r.unpack('BIIIQiiiI')==(1,123,4,5,10,0,0,0,1)
    assert r.unpack('BI')==(0,2);assert r.guid()==(0,0);assert r.unpack('iii')==(64394,99,-3)
    assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.align();assert r.bits(1)==1;r.align()
    assert r.unpack('ii')==(234,0);assert r.guid()==(0,0);assert r.unpack('iII')==(-1,0,0)
    assert r.bits(2)==0 and r.bits(1)==0;r.end()
    assert actions(codec,[('trade_response','SMSG_TRADE_UPDATED',trade_item(socket=123))])[0] is None
    assert 'error' in actions(codec,[('trade_response','SMSG_TRADE_UPDATED',trade_item()+b'x')])[0]
