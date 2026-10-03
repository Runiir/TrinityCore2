"""Trace only reviewed item-use packets needed for the ordinary glyph trial."""
import json
import struct
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,action
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import Reader,Writer,player_high

CAPTURED=bytes.fromhex('ff2501a032040c018302c278bc0000000000000000e3010000439c030000000000000000000000000000000000000000000000000000000000000000000000')
ITEM=(0x4000<<48)|50
ITEM_HIGH=(3<<58)|(1<<42)


def fixture(bag=255,slot=25,owner=1):
    start=INDEX['PLAYER_FIELD_INV_SLOT_HEAD']
    item={'guid':ITEM,'fields':{INDEX['ITEM_FIELD_OWNER']:owner,INDEX['ITEM_FIELD_STACK_COUNT']:1}}
    items=[item]
    if bag==255:values={start+slot*2:50,start+slot*2+1:ITEM>>32}
    else:
        container=(0x4000<<48)|11
        values={start+bag*2:11,start+bag*2+1:container>>32}
        items.append({'guid':container,'fields':{INDEX['ITEM_FIELD_OWNER']:owner,INDEX['CONTAINER_FIELD_NUM_SLOTS']:16,
            INDEX['CONTAINER_FIELD_SLOT_1']+slot*2:50,INDEX['CONTAINER_FIELD_SLOT_1']+slot*2+1:ITEM>>32}})
    return {'character':{'guid':1,'map':0},'snapshot':{'guid':1,'fields':values},'gameobjects':[],
            'units':[],'inventory_items':items}


def run(codec,actions,**kw):return result(codec,op='stateful',actions=actions,**fixture(**kw))


def test_item_use_is_captured_without_authentication_or_launcher_payloads(codec,tmp_path):
    (tmp_path/'evidence').mkdir()
    for name in ['CMSG_USE_ITEM','CMSG_AUTH_SESSION','SMSG_CONNECT_TO','SMSG_ENTER_ENCRYPTED_MODE']:
        result(codec,op='packet_diagnostic',root=str(tmp_path),name=name,body='ff230000')
    rows=[json.loads(line) for line in (tmp_path/'evidence/world_packets.jsonl').read_text().splitlines()]
    assert [(r['name'],r['body']) for r in rows]==[('CMSG_USE_ITEM','ff230000')]


def test_captured_glyph_book_use_matches_native_owned_position_and_cast_order(codec):
    # UI27 glyph_learn_06: ordinary right-click, before native translation.
    out=run(codec,[action('item_use','CMSG_USE_ITEM',CAPTURED)])
    expected=struct.pack('<BBBiQiBI',255,25,1,483,ITEM,0,0,0)
    assert out==[['CMSG_USE_ITEM',expected.hex()]]
    moved=bytes([30,2])+CAPTURED[2:]
    assert run(codec,[action('item_use','CMSG_USE_ITEM',moved)],bag=19,slot=2)==[
        ['CMSG_USE_ITEM',struct.pack('<BBBiQiBI',19,2,1,483,ITEM,0,0,0).hex()]]


def test_item_use_rejects_unowned_moved_banked_or_malformed_inventory(codec):
    for body,kw in [(CAPTURED,{'owner':2}),(CAPTURED,{'slot':24}),
        (bytes([255,59])+CAPTURED[2:],{}),(bytes([87,2])+CAPTURED[2:],{}),
        (CAPTURED[:-1],{}),(CAPTURED+b'x',{}),
        (CAPTURED[:2]+Writer().guid(51,ITEM_HIGH).finish()+CAPTURED[7:],{})]:
        assert 'error' in run(codec,[action('item_use','CMSG_USE_ITEM',body)],**kw)[0]


def start(caster=ITEM,unit=1):
    # Legacy packed GUIDs and the pinned SpellCastData scalar/target layout.
    item=Writer().pack('B',0x81).pack('BB',caster&255,0x40).finish()
    return item+Writer().pack('BB',1,unit).pack('BiIIII',1,483,0,0,0,0).finish()


def test_item_spell_prepare_start_and_go_keep_item_caster_and_player_unit(codec):
    go=start()[:-4]+struct.pack('<BQB',1,1,0)+struct.pack('<I',0)
    actions=[action('item_use','CMSG_USE_ITEM',CAPTURED),action('cast_prepare','SMSG_SPELL_START',start()),
        action('cast_response','SMSG_SPELL_START',start()),action('cast_response','SMSG_SPELL_GO',go),
        action('cast_response','SMSG_SPELL_START',start(caster=ITEM+1)),
        action('cast_response','SMSG_SPELL_START',start(unit=2))]
    out=run(codec,actions)
    assert out[1][0]=='SMSG_SPELL_PREPARE'
    for packet in out[2:4]:
        r=Reader(bytes.fromhex(packet[1]));assert r.guid()==(50,ITEM_HIGH)
        assert r.guid()==(1,player_high()) and r.guid()[1]>>58==47
    assert out[4:]==[None,None]


def test_rejected_item_use_returns_the_original_public_cast_identity(codec):
    out=run(codec,[action('item_use_rejected','CMSG_USE_ITEM',CAPTURED)])
    r=Reader(bytes.fromhex(out[0][1]));cast=Reader(CAPTURED[7:]).guid()
    assert out[0][0]=='SMSG_CAST_FAILED' and r.guid()==cast
    assert r.unpack('iI')[0]==483
