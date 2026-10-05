import pytest
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_oracle_lifecycle import packet
from tools.client_compatibility.world.tests.test_inventory_packets import mask


def update(codec,fields,guid=1):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'fields':{}},
        gameobjects=[],units=[{'guid':2,'kind':4,'map':0,'fields':{},'public_character':{'name':'Harnesstwo','gender':0}}],
        actions=[{'fn':'object_updates','name':'SMSG_UPDATE_OBJECT','body':packet(guid,fields)}])[0]


def payload(reply):
    assert reply is not None,'native owner skill delta was silently dropped'
    assert reply[0]=='SMSG_UPDATE_OBJECT'
    r=Reader(bytes.fromhex(reply[1]));assert r.unpack('HI')==(0,1)
    assert r.bits(1)==1 and r.bits(1)==0
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('BBBI')==(1,0,3,1<<7)
    assert mask(r,46,True)=={0,36};r.align()
    return r


@pytest.mark.parametrize('added',[True,False])
def test_language_skill_add_and_clear_keep_both_native_halfwords(codec,added):
    values={'PLAYER_SKILL_LINEID_0':98|(111<<16 if added else 0),
        'PLAYER_SKILL_STEP_0':1<<16 if added else 0,
        'PLAYER_SKILL_RANK_0':300|(1<<16 if added else 0),
        'PLAYER_SKILL_MAX_RANK_0':300|(300<<16 if added else 0)}
    r=payload(update(codec,{INDEX[k]:v for k,v in values.items()}))
    assert mask(r,57,True)=={0,1,2,257,258,513,514,769,770,1025,1026};r.align()
    assert r.unpack('10H')==(98,0,300,300,300,111 if added else 0,
        1 if added else 0,1 if added else 0,1 if added else 0,300 if added else 0)
    r.end()


def test_last_native_rank_pair_updates_starting_rank_without_extra_modern_slots(codec):
    r=payload(update(codec,{INDEX['PLAYER_SKILL_RANK_0']+63:0xffff8000}))
    assert mask(r,57,True)=={0,639,640,895,896};r.align()
    assert r.unpack('4H')==(32768,32768,65535,65535);r.end()


def test_signed_skill_bonus_is_preserved_and_peer_skill_data_stays_private(codec):
    fields={INDEX['PLAYER_SKILL_MODIFIER_0']:0xfffffffe}
    r=payload(update(codec,fields));assert mask(r,57,True)=={0,1281,1282};r.align()
    assert r.unpack('2h')==(-2,-1);r.end()
    assert update(codec,fields,guid=2) is None
