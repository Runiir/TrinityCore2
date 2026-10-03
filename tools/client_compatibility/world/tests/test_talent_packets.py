"""Player talent groups preserve native allocation across incompatible count widths."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


def call(codec,name,body,fn='talent_response'):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        units=[],gameobjects=[],actions=[{'fn':fn,'name':name,'body':body.hex()}])[0]


def native(groups=1,active=0):
    data=struct.pack('<BIBB',0,39,groups,active)
    for i in range(groups):
        data+=struct.pack('<IBIBIBB9H',161+i,2,122,2,124,0,9,*range(100,109))
    return data


@pytest.mark.parametrize('groups,active',[(0,0),(1,0),(2,0),(2,1)])
def test_player_talents_preserve_points_tree_ranks_glyphs_and_active_group(codec,groups,active):
    packet=call(codec,'SMSG_TALENTS_INFO',native(groups,active))
    assert packet[0]=='SMSG_UPDATE_TALENT_DATA';r=Reader(bytes.fromhex(packet[1]))
    assert r.unpack('IBI')==(39,active,groups)
    for i in range(groups):
        assert r.unpack('BIBIBI')==(2,2,9,9,0 if groups==1 else i+1,161+i)
        assert r.unpack('4I')==(122,2,124,0)
        assert r.unpack('9H')==tuple(range(100,109))
    assert r.bits(1)==0;r.end()


def test_talent_update_rejects_all_prefixes_trailing_duplicate_and_invalid_fields(codec):
    body=native(2,1)
    for n in range(len(body)):assert 'error' in call(codec,'SMSG_TALENTS_INFO',body[:n])
    for bad in [body+b'x',b'\x02'+body[1:],b'\x01'+body[1:],
                body[:5]+b'\x03'+body[6:],body[:6]+b'\x02'+body[7:],
                struct.pack('<BIBB',0,101,1,0),body[:16]+b'\x05'+body[17:],
                body[:17]+struct.pack('<I',122)+body[21:],body[:22]+b'\x08'+body[23:]]:
        assert 'error' in call(codec,'SMSG_TALENTS_INFO',bad)


def test_modern_talent_learning_widens_rank_without_adding_a_spec_or_allocation(codec):
    for rank in range(5):
        body=struct.pack('<IH',122,rank)
        assert call(codec,'CMSG_LEARN_TALENT',body,'talent_request')==['CMSG_LEARN_TALENT',struct.pack('<II',122,rank).hex()]
    for body in [b'',struct.pack('<IH',0,0),struct.pack('<IH',122,5),struct.pack('<IH',122,0)+b'x']:
        assert 'error' in call(codec,'CMSG_LEARN_TALENT',body,'talent_request')
    for tree in range(3):
        body=struct.pack('<i',tree)
        assert call(codec,'CMSG_SET_PRIMARY_TALENT_TREE',body,'talent_request')==['CMSG_SET_PRIMARY_TALENT_TREE',body.hex()]
    for tree in [-1,3]:assert 'error' in call(codec,'CMSG_SET_PRIMARY_TALENT_TREE',struct.pack('<i',tree),'talent_request')
