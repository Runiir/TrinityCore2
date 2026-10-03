"""Cold-client template bursts drain without disconnecting or flooding native."""
import struct
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


def action(fn,entry):
    return {'fn':fn,'name':'CMSG_QUERY_CREATURE' if fn=='creature_query' else 'SMSG_CREATURE_QUERY_RESPONSE',
        'body':struct.pack('<I',entry if fn=='creature_query' else entry|0x80000000).hex()}


def call(codec,actions):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        units=[],gameobjects=[],actions=actions)


def test_four_hundred_unique_queries_drain_with_sixty_four_native_in_flight(codec):
    requests=[action('creature_query',entry) for entry in range(1,401)]
    replies=call(codec,requests+[action('creature_reply',entry) for entry in range(1,401)])
    assert all(row and row[0]=='CMSG_CREATURE_QUERY' for row in replies[:64])
    assert replies[64:400]==[None]*336
    native=[row for row in replies if row and row[0]=='CMSG_CREATURE_QUERY']
    modern=[row for row in replies if row and row[0]=='SMSG_QUERY_CREATURE_RESPONSE']
    assert [struct.unpack_from('<I',bytes.fromhex(row[1]))[0] for row in native]==list(range(1,401))
    assert [struct.unpack_from('<I',bytes.fromhex(row[1]))[0] for row in modern]==list(range(1,401))


def test_duplicate_and_unrequested_replies_do_not_grow_or_drain_the_queue(codec):
    replies=call(codec,[action('creature_query',entry) for entry in range(1,66)]+[
        action('creature_query',1),action('creature_query',65),action('creature_reply',65),
        action('creature_reply',999),action('creature_reply',1),action('creature_reply',65)])
    assert replies[64:69]==[None]*5
    assert replies[69][0]=='CMSG_CREATURE_QUERY' and struct.unpack('<IQ',bytes.fromhex(replies[69][1]))==(65,0)
    assert [row[0] for row in replies[70:]]==['SMSG_QUERY_CREATURE_RESPONSE','SMSG_QUERY_CREATURE_RESPONSE']


def test_pending_queue_is_bounded_and_can_accept_after_a_reply(codec):
    replies=call(codec,[action('creature_query',entry) for entry in range(1,4097)]+[
        action('creature_query',4000),action('creature_query',4097),action('creature_reply',1),
        action('creature_query',4097)])
    assert replies[4096] is None
    assert 'bounded pending queue' in replies[4097]['error']
    assert replies[4098][0]=='CMSG_CREATURE_QUERY'
    assert replies[4099][0]=='SMSG_QUERY_CREATURE_RESPONSE'
    assert replies[4100] is None
