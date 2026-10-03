"""Modern reward identity maps only to the last authoritative native offer."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

NPC=(0xf13<<52)|(261<<32)|500
UNIT={'guid':NPC,'kind':3,'map':0,'fields':{str(INDEX['UNIT_NPC_FLAGS']):2}}


def native_rewards(choices):
    ids=[x[0] for x in choices]+[0]*(6-len(choices));qty=[x[1] for x in choices]+[0]*(6-len(choices))
    return (struct.pack('<I18I',len(choices),*ids,*qty,*([0]*6))+struct.pack('<I12I',0,*([0]*12))+
        struct.pack('<4If3I',12345,350,0,0,0,0,0,0)+bytes(5*3*4)+bytes((2+4+4+2)*4))


def offer(choices=[(39,1),(40,2)]):
    return (struct.pack('<QI',NPC,52)+b'Protect the Frontier\0Well done.\0\0\0\0\0'+
        struct.pack('<2IB3I2I',0,0,1,8,0,1,10,6)+native_rewards(choices))


def stateful(codec,actions,units=None,active=True):
    fields={str(INDEX['PLAYER_QUEST_LOG_1_1']):52} if active else {}
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':fields},
        units=[UNIT] if units is None else units,gameobjects=[],actions=actions)


def action(fn,name,body):return {'fn':fn,'name':name,'body':body.hex()}


def choice(item=40,quantity=2):
    return Writer().guid(*modern_guid(NPC,0)).pack('I',52).bits(0,2).flush().pack('iII',item,0,0).bits(0,1).flush().bits(0,6).flush().pack('i',quantity).finish()


def test_plain_reward_offer_preserves_text_emotes_identity_and_native_rewards(codec):
    reply=stateful(codec,[action('quest_response','SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE',offer())])[0]
    assert reply[0]=='SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE';r=Reader(bytes.fromhex(reply[1]))
    assert r.unpack('8i')==(0,)*8 and r.unpack('12i')==(0,)*12
    assert r.unpack('4iQi3i')==(2,0,12345,350,0,0,0,0,0)
    assert r.unpack('20i')==(0,)*20 and r.unpack('7i')==(0,)*7
    choices=[]
    for _ in range(6):
        assert r.bits(2)==0;r.align();item=r.unpack('iII');assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.align()
        choices.append((item,r.unpack('i')[0]))
    assert choices==[((39,0,0),1),((40,0,0),2)]+[((0,0,0),0)]*4
    assert r.bits(1)==0;r.align();assert r.unpack('I')==(1,) and r.guid()==modern_guid(NPC,0)
    assert r.unpack('7I')==(8,0,0,261,52,0,0) and r.unpack('2I')==(6,10)
    assert (r.bits(1),r.bits(2))==(1,0);r.align();assert r.unpack('7I')==(0,0,0,0,0,261,0)
    lengths=[r.bits(n) for n in [9,12,10,8,10,8]];r.align()
    assert [r.raw(n) for n in lengths]==[b'Protect the Frontier',b'Well done.',b'',b'',b'',b''];r.end()


def test_modern_choice_item_id_maps_to_native_index_not_the_item_id(codec):
    rows=stateful(codec,[action('quest_response','SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE',offer()),
        action('quest_request','CMSG_QUEST_GIVER_CHOOSE_REWARD',choice())])
    assert rows[1]==['CMSG_QUEST_GIVER_CHOOSE_REWARD',struct.pack('<QII',NPC,52,1).hex()]
    for item,quantity in [(999,1),(40,1),(0,0)]:
        rows=stateful(codec,[action('quest_response','SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE',offer()),
            action('quest_request','CMSG_QUEST_GIVER_CHOOSE_REWARD',choice(item,quantity))])
        assert 'error' in rows[1]
    assert 'error' in stateful(codec,[action('quest_request','CMSG_QUEST_GIVER_CHOOSE_REWARD',choice())])[0]


def test_no_choice_reward_keeps_native_index_zero(codec):
    rows=stateful(codec,[action('quest_response','SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE',offer([])),
        action('quest_request','CMSG_QUEST_GIVER_CHOOSE_REWARD',choice(0,0))])
    assert rows[1]==['CMSG_QUEST_GIVER_CHOOSE_REWARD',struct.pack('<QII',NPC,52,0).hex()]


def test_completion_requests_preserve_native_bool_width_and_active_owner(codec):
    for value in [0,1]:
        body=Writer().guid(*modern_guid(NPC,0)).pack('I',52).bits(value,1).finish()
        assert stateful(codec,[action('quest_request','CMSG_QUEST_GIVER_COMPLETE_QUEST',body)])[0]==[
            'CMSG_QUEST_GIVER_COMPLETE_QUEST',struct.pack('<QIB',NPC,52,value).hex()]
        assert 'error' in stateful(codec,[action('quest_request','CMSG_QUEST_GIVER_COMPLETE_QUEST',body)],active=False)[0]
    body=Writer().guid(*modern_guid(NPC,0)).pack('I',52).finish()
    assert stateful(codec,[action('quest_request','CMSG_QUEST_GIVER_REQUEST_REWARD',body)])[0]==[
        'CMSG_QUEST_GIVER_REQUEST_REWARD',struct.pack('<QI',NPC,52).hex()]


def test_offer_and_choice_require_exact_reader_lengths(codec):
    for body,name,fn in [(offer(),'SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE','quest_response'),
        (choice(),'CMSG_QUEST_GIVER_CHOOSE_REWARD','quest_request')]:
        for size in range(len(body)):
            actions=[action('quest_response','SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE',offer()),action(fn,name,body[:size])]
            assert 'error' in stateful(codec,actions)[1]
        assert 'error' in stateful(codec,[action(fn,name,body+b'x')])[0]
    assert stateful(codec,[action('quest_response','SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE',offer())],active=False)[0] is None
    for units in [[],[{**UNIT,'kind':4}],[{**UNIT,'fields':{}}]]:
        assert 'error' in stateful(codec,[action('quest_response','SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE',offer())],units)[0]


def test_reward_completion_preserves_signed_money_flags_and_retires_offer(codec):
    body=struct.pack('<6I',0,2,(-100)&0xffffffff,350,52,171)+b'\x80'
    rows=stateful(codec,[action('quest_response','SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE',offer()),
        action('quest_response','SMSG_QUEST_GIVER_QUEST_COMPLETE',body),
        action('quest_request','CMSG_QUEST_GIVER_CHOOSE_REWARD',choice())])
    assert rows[1][0]=='SMSG_QUEST_GIVER_QUEST_COMPLETE';r=Reader(bytes.fromhex(rows[1][1]))
    assert r.unpack('IIqII')==(52,350,-100,171,2) and [r.bits(1) for _ in range(4)]==[0,1,0,0]
    r.align();assert r.unpack('iII')==(0,0,0);assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.end()
    assert 'error' in rows[2]
