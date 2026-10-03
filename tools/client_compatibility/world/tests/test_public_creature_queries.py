"""Unseen quest template reads reach native authority; malformed and excess reads fail."""
import struct
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_merchant_packets import GUID,UNIT


def run(codec,actions,units=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        gameobjects=[],units=units or [],actions=actions)


def query(entry):
    return {'fn':'creature_query','name':'CMSG_QUERY_CREATURE','body':struct.pack('<I',entry).hex()}


def denied(entry):
    return {'fn':'creature_reply','name':'SMSG_CREATURE_QUERY_RESPONSE','body':struct.pack('<I',entry|0x80000000).hex()}


def test_captured_unseen_bear_query_reaches_native_instead_of_fabricated_negative(codec):
    # UI23: CMSG_QUERY_CREATURE 36030000 for quest 52's Young Forest Bear.
    # The bridge formerly answered 3603000000 without querying the worldserver.
    rows=run(codec,[query(822),query((GUID>>32)&0xfffff),denied(822),denied(822)],[UNIT])
    assert rows[0]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',822,0).hex()]
    assert rows[1]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',(GUID>>32)&0xfffff,GUID).hex()]
    assert rows[2]==['SMSG_QUERY_CREATURE_RESPONSE','3603000000']
    assert rows[3] is None


def test_public_template_reads_reject_invalid_ids_and_nonexact_bodies(codec):
    action=query(822);body=bytes.fromhex(action['body'])
    actions=[{**action,'body':body[:i].hex()} for i in range(len(body))]
    actions+=[{**action,'body':(body+b'x').hex()},query(0),query(0x80000000),query(0xffffffff)]
    assert all('error' in row for row in run(codec,actions))


def test_outstanding_public_templates_are_bounded_and_native_reply_releases_capacity(codec):
    actions=[query(i) for i in range(1,258)]+[denied(1),query(257)]
    rows=run(codec,actions)
    assert all(row[0]=='CMSG_QUERY_CREATURE' for row in rows[:256])
    assert 'error' in rows[256]
    assert rows[257]==['SMSG_QUERY_CREATURE_RESPONSE','0100000000']
    assert rows[258]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',257,0).hex()]
