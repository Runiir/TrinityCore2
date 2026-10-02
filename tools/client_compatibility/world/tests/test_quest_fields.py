"""Quest log ownership and counters survive creates, changes, abandonment and slot 25."""
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import mask

START=INDEX['PLAYER_QUEST_LOG_1_1']


def log(r):
    time,quest,state=r.unpack('q i I');return time,quest,state,r.unpack('24H')


def test_native_packed_counter_values_and_timer_in_all_25_create_slots(codec):
    native={START+slot*5+part:value for slot in [0,24] for part,value in enumerate([28766+slot,slot%3,0x80010002,0xffff0004,1700000000])}
    values=result(codec,op='object_values',snapshot={'fields':native},character={})['PlayerData']['QuestLog']
    assert len(values)==25
    for slot in [0,24]:
        assert values[slot]=={'EndTime':1700000000,'QuestID':28766+slot,'StateFlags':slot%3,
            'ObjectiveProgress':[2,32769,4,65535]+[0]*20}
    assert values[1]=={'EndTime':0,'QuestID':0,'StateFlags':0,'ObjectiveProgress':[0]*24}


def test_sparse_counter_delta_sends_complete_owned_slots_across_mask_blocks(codec):
    native={START:28766,START+2:3,START+24*5:28825,START+24*5+1:1}
    changed={START+2:3,START+24*5+1:1}
    body=result(codec,op='quest_update',snapshot={'guid':1,'fields':native},changed=changed)
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,);assert r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('BBBI')==(3,0,3,1<<6)
    assert mask(r,5)=={42,43,67};assert r.bits(1)==1;r.align()
    assert log(r)==(0,28766,0,(3,0,0,0)+tuple([0]*20))
    assert log(r)==(0,28825,1,tuple([0]*24));r.end()


def test_abandoned_slot_is_zeroed_and_unrelated_fields_emit_no_quest_delta(codec):
    assert result(codec,op='quest_update',snapshot={'guid':1,'fields':{}},changed={START:0})
    assert result(codec,op='quest_update',snapshot={'guid':1,'fields':{}},changed={INDEX['PLAYER_XP']:1})==''
