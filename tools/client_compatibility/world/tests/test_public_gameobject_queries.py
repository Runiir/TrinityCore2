"""Cached static templates do not grant interaction with unseen objects."""
import struct
from tools.client_compatibility.world.buffer import Writer, Reader
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec, result, action, stateful


def query(entry=2040, counter=17122, map_id=0):
    guid=(0xf11<<52)|(entry<<32)|counter
    return Writer().pack('I',entry).guid(*modern_guid(guid,map_id)).finish()


def test_captured_precreate_cached_query_reads_native_template_without_visibility(codec):
    # UI26 c1cfdda6: sent 31 ms after continued authentication, before create.
    captured=bytes.fromhex('f807000003a6e242fe01042c')
    assert captured==query()
    out=stateful(codec,{'guid':1},[
        action('gameobject_query','CMSG_QUERY_GAME_OBJECT',captured),
        action('gameobject_reply','SMSG_GAMEOBJECT_QUERY_RESPONSE',struct.pack('<I',2040|0x80000000))])
    assert out[0]==['CMSG_GAMEOBJECT_QUERY',struct.pack('<IQ',2040,0).hex()]
    r=Reader(bytes.fromhex(out[1][1]));assert r.unpack('I')==(2040,)
    assert r.guid()==modern_guid((0xf11<<52)|(2040<<32)|17122,0)
    assert r.bits(1)==0 and r.unpack('I')==(0,);r.end()
    assert 'not visible' in stateful(codec,{'guid':1},[
        action('loot_request','CMSG_GAME_OBJ_USE',captured[4:])])[0]['error']


def test_visible_template_keeps_native_guid_and_other_map_cache_uses_zero(codec):
    guid=(0xf11<<52)|(2040<<32)|17122
    visible={'guid':guid,'map':0}
    out=stateful(codec,{'guid':1},[
        action('gameobject_query','CMSG_QUERY_GAME_OBJECT',query()),
        action('gameobject_query','CMSG_QUERY_GAME_OBJECT',query(map_id=530))],gameobjects=[visible])
    assert [x[1] for x in out]==[struct.pack('<IQ',2040,guid).hex(),struct.pack('<IQ',2040,0).hex()]


def test_static_query_rejects_wrong_type_entry_realm_and_malformed_body(codec):
    good=query();low,high=modern_guid((0xf11<<52)|(2040<<32)|17122,0)
    bad=[good[:-1],good+b'\0',struct.pack('<I',0)+good[4:],
         struct.pack('<I',2041)+good[4:],Writer().pack('I',2040).guid(low,high^(1<<42)).finish(),
         Writer().pack('I',2040).guid(low,high^(3<<58)).finish(),
         Writer().pack('I',2040).guid(0,high).finish()]
    for body in bad:
        assert 'error' in stateful(codec,{'guid':1},[
            action('gameobject_query','CMSG_QUERY_GAME_OBJECT',body)])[0]


def deferred(entry=2040, name='CMSG_GAMEOBJECT_QUERY', guid=0):
    return dict(fn='template',name=name,body=struct.pack('<IQ',entry,guid).hex())


def test_early_templates_are_coalesced_released_once_and_independent_of_mail_quests(codec):
    actions=[{'fn':'begin'},deferred(),deferred(),deferred(822,'CMSG_CREATURE_QUERY'),
             {'fn':'read','name':'CMSG_QUERY_QUEST_INFO','body':struct.pack('<I',52).hex()},
             {'fn':'mail','name':'MSG_QUERY_NEXT_MAIL_TIME','body':''},{'fn':'release'},{'fn':'release'}]
    rows=result(codec,op='login_quest_reads',actions=actions)
    assert [r['queued'] for r in rows]==[0,1,1,2,3,4,0,0]
    assert rows[-2]['packets']==[['CMSG_QUERY_QUEST_INFO',struct.pack('<I',52).hex()],
        ['CMSG_GAMEOBJECT_QUERY',deferred()['body']],
        ['CMSG_CREATURE_QUERY',deferred(822,'CMSG_CREATURE_QUERY')['body']],['MSG_QUERY_NEXT_MAIL_TIME','']]
    assert rows[-1]['packets']==[]


def test_early_template_reads_reject_mutations_invalid_identity_and_queue_overflow(codec):
    for request in [deferred(0),deferred(0x80000001),deferred(0x100000),
        deferred(name='CMSG_GAMEOBJ_USE'),deferred(guid=(0xf11<<52)|(2041<<32)|17122),
        {**deferred(),'body':'01'}]:
        assert 'error' in codec(op='login_quest_reads',actions=[{'fn':'begin'},request])
    assert 'error' in codec(op='login_quest_reads',actions=[{'fn':'begin'},*[deferred(i) for i in range(1,514)]])
