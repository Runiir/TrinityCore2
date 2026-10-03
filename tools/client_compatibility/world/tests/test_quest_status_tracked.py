"""Captured tracked reads refresh native eligibility without granting visibility."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_quest_status import call,OBJECT_GUID
from tools.client_compatibility.world.tests.test_quest_requests import GUID

NAME='CMSG_QUEST_GIVER_STATUS_TRACKED_QUERY'
REFRESH=['CMSG_QUEST_GIVER_STATUS_MULTIPLE_QUERY','']
CAPTURE=bytes.fromhex('0200000007a36d10014041042003a7c56440f5c6042c')


def tracked(identities):
    w=Writer().pack('I',len(identities))
    for identity in identities:w.guid(*identity)
    return w.finish()


def request(codec,body):
    return call(codec,NAME,body,[],[],fn='quest_request')


def test_actual_two_guid_tracking_toggle_refreshes_native_visible_status(codec):
    r=Reader(CAPTURE);assert r.unpack('I')==(2,)
    identities=[r.guid(),r.guid()];r.end()
    assert identities[0]==modern_guid((0xf13<<52)|(261<<32)|69741,0)
    assert request(codec,CAPTURE)==REFRESH


def test_empty_duplicate_cached_creature_and_gameobject_requests(codec):
    assert request(codec,tracked([]))==['SMSG_QUEST_GIVER_STATUS_MULTIPLE','00000000']
    npc=modern_guid(GUID,0);obj=modern_guid(OBJECT_GUID,0)
    for identities in [[npc],[obj],[npc,obj],[npc,npc],[npc]*1000]:
        assert request(codec,tracked(identities))==REFRESH
    # Tracked reads neither register unseen objects nor unlock NPC interactions.
    requests=[{'fn':'quest_request','name':NAME,'body':tracked([npc]).hex()},
        {'fn':'quest_request','name':'CMSG_QUEST_GIVER_HELLO','body':tracked([npc])[4:].hex()}]
    responses=result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        units=[],gameobjects=[],actions=requests)
    assert responses[0]==REFRESH and 'error' in responses[1]


def test_tracked_reads_reject_truncation_trailing_count_and_foreign_identities(codec):
    for end in range(len(CAPTURE)):assert 'error' in request(codec,CAPTURE[:end])
    for body in [CAPTURE+b'x',struct.pack('<I',1001),tracked([])+b'x']:
        assert 'error' in request(codec,body)
    low,high=modern_guid(GUID,0)
    for invalid in [(0,high),(0x100000000,high),(low,high+(1<<29)),(low,high+(1<<42)),
        (1,7<<58),(low,high|1),(0,0)]:
        assert 'error' in request(codec,tracked([(low,high),invalid]))
