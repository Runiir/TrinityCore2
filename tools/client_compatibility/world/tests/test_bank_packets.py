"""Native-authorized character bank opening, slot translation and close revocation."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import hint

GUID=(0xf13<<52)|(2455<<32)|314007
UNIT={'guid':GUID,'kind':3,'map':0,'fields':{str(INDEX['UNIT_NPC_FLAGS']):131073}}
NATIVE=struct.pack('<Q',GUID)
IDENTITY=Writer().guid(*modern_guid(GUID,0)).finish()


def actions(codec,rows,units=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
        units=[UNIT] if units is None else units,gameobjects=[],
        actions=[{'fn':fn,'name':name,'body':body.hex()} for fn,name,body in rows])


def opened():return ('bank_response','SMSG_SHOW_BANK',NATIVE)


def test_native_bank_response_uses_modern_npc_interaction_and_visible_identity(codec):
    reply=actions(codec,[opened()])[0];assert reply[0]=='SMSG_NPC_INTERACTION_OPEN_RESULT'
    r=Reader(bytes.fromhex(reply[1]));assert r.guid()==modern_guid(GUID,0)
    assert r.unpack('i')==(8,);assert r.bits(1)==1;r.end()
    assert actions(codec,[opened()],[])[0] is None
    for kind,flags in [(4,131073),(3,1)]:
        unit={**UNIT,'kind':kind,'fields':{str(INDEX['UNIT_NPC_FLAGS']):flags}}
        assert actions(codec,[opened()],[unit])[0] is None


def test_bank_activation_preserves_native_guid_and_rejects_other_interactions(codec):
    body=IDENTITY+struct.pack('<i',8)
    assert actions(codec,[('bank_request','CMSG_BANKER_ACTIVATE',body)])[0]==['CMSG_BANKER_ACTIVATE',NATIVE.hex()]
    assert 'error' in actions(codec,[('bank_request','CMSG_BANKER_ACTIVATE',body)],[])[0]
    for kind in [0,10,67,68]:
        assert 'error' in actions(codec,[('bank_request','CMSG_BANKER_ACTIVATE',IDENTITY+struct.pack('<i',kind))])[0]


def test_auto_bank_requires_native_grant_and_close_revokes_it(codec):
    move=('inventory_request','CMSG_AUTOBANK_ITEM',hint((255,35)).pack('3B',0,255,35).finish())
    replies=actions(codec,[move,opened(),move,('bank_close','CMSG_CLOSE_INTERACTION',IDENTITY),move])
    assert 'error' in replies[0];assert replies[2]==['CMSG_AUTOBANK_ITEM','ff17']
    assert replies[3] is None and 'error' in replies[4]


@pytest.mark.parametrize('bag,slot,native',[(255,59,'ff27'),(87,15,'430f'),(30,2,'1302')])
def test_auto_store_preserves_bank_or_inventory_source_mapping(codec,bag,slot,native):
    body=hint().pack('2B',bag,slot).finish()
    assert actions(codec,[opened(),('inventory_request','CMSG_AUTOSTORE_BANK_ITEM',body)])[1]==['CMSG_AUTOSTORE_BANK_ITEM',native]


def test_account_guild_bank_and_invalid_inventory_hints_are_rejected(codec):
    for bank_type in [1,2,255]:
        body=hint().pack('3B',bank_type,255,35).finish()
        assert 'error' in actions(codec,[opened(),('inventory_request','CMSG_AUTOBANK_ITEM',body)])[1]
    body=hint((255,58)).pack('3B',0,255,35).finish()
    assert 'error' in actions(codec,[opened(),('inventory_request','CMSG_AUTOBANK_ITEM',body)])[1]


def test_bank_parsers_reject_truncation_and_trailing_data(codec):
    cases=[opened(),('bank_request','CMSG_BANKER_ACTIVATE',IDENTITY+struct.pack('<i',8)),
        ('bank_close','CMSG_CLOSE_INTERACTION',IDENTITY)]
    for fn,name,body in cases:
        for bad in [body[:-1],body+b'x']:
            assert 'error' in actions(codec,[(fn,name,bad)])[0]


def test_late_close_after_logout_grants_no_bank_authority(codec):
    replies=actions(codec,[opened(),('logout_complete','SMSG_LOGOUT_COMPLETE',b''),
        ('bank_close','CMSG_CLOSE_INTERACTION',IDENTITY),
        ('inventory_request','CMSG_AUTOBANK_ITEM',hint().pack('3B',0,255,35).finish())])
    assert replies[1:3]==[None,None];assert 'error' in replies[3]
