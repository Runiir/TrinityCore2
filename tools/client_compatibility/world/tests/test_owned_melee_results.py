"""Captured native owner hits against the pinned60895 combat-log wire layout."""
import struct
import pytest
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

VICTIM=17379582294226026881
CAPTURE=bytes.fromhex('020000000105f781c10204ae30f106000000ffffffff01010000000000c04006000000010000000000000000')
# Independent pinned wire vector: absent log data, sized round, modern GUIDs,
# unknown OriginalDamage0, native subdamage, default ContentTuningParams.
MODERN='00420000000200000001a005040807a681c102812b04200600000000000000ffffffff01010000000000c040060000000100000000000000000000000000000000000000000000'


def hits(codec,body=CAPTURE,*,units=None,owner=5,snapshot=5):
    return result(codec,op='stateful',character={'guid':owner,'map':0},
        snapshot={'guid':snapshot},units=units if units is not None else
        [{'guid':VICTIM,'kind':3,'map':0}],gameobjects=[],actions=[
        {'fn':'combat_response','name':'SMSG_ATTACKER_STATE_UPDATE','body':body.hex()}])[0]


def test_exact_captured_hit_gets_complete_pinned_packet(codec):
    assert hits(codec)==['SMSG_ATTACKER_STATE_UPDATE',MODERN]


@pytest.mark.parametrize('case', ['other_owner','wrong_snapshot','invisible','different_map','not_unit'])
def test_hit_does_not_escape_owned_visible_map(codec,case):
    args={'other_owner':{'owner':6},'wrong_snapshot':{'snapshot':6},'invisible':{'units':[]},
        'different_map':{'units':[{'guid':VICTIM,'kind':3,'map':1}]},
        'not_unit':{'units':[{'guid':VICTIM,'kind':5,'map':0}]}}[case]
    assert hits(codec,**args) is None


@pytest.mark.parametrize('flag',[1,0x20,0x80,0x1000,0x2000,0x80000000])
def test_unsupported_optional_layout_is_healthy_explicit_error(codec,flag):
    body=struct.pack('<I',flag)+CAPTURE[4:]
    assert hits(codec,body).get('error')
    assert hits(codec)==['SMSG_ATTACKER_STATE_UPDATE',MODERN]


def test_all_owned_truncations_and_trailing_data_are_rejected(codec):
    for length in range(len(CAPTURE)):
        assert hits(codec,CAPTURE[:length]).get('error')
    assert hits(codec,CAPTURE+b'\0').get('error')


def test_native_rage_extension_preserves_exact_amount(codec):
    body=struct.pack('<I',0x800002)+CAPTURE[4:]+struct.pack('<i',17)
    packet=bytes.fromhex(hits(codec,body)[1])
    assert packet[0]==0 and struct.unpack_from('<I',packet,1)[0]==70
    assert struct.unpack_from('<I',packet,5)[0]==0x800002
    assert struct.unpack_from('<i',packet,len(packet)-18)[0]==17
    assert packet[-14:]==bytes(14)
    assert hits(codec,body[:-4]).get('error')
    assert hits(codec,body[:-4]+struct.pack('<i',-1)).get('error')


@pytest.mark.parametrize('offset,format,value',[(14,'i',-1),(18,'i',-2),(22,'B',2),
    (23,'i',2),(27,'f',float('nan')),(31,'i',7),(35,'B',9),(36,'I',1),(40,'I',3110)])
def test_invalid_physical_damage_or_state_is_rejected(codec,offset,format,value):
    body=bytearray(CAPTURE);struct.pack_into('<'+format,body,offset,value)
    assert hits(codec,body).get('error')
