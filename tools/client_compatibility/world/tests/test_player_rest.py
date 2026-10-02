"""Rest state wire values that the ordinary XP UI consumes."""
import pytest
from tools.client_compatibility.world import objects
from tools.client_compatibility.world.buffer import Reader,player_high
from .test_native_bridge_codec import codec,result


@pytest.mark.parametrize('state,threshold',[(1,12345),(2,0),(6,789)])
def test_native_rest_create_values_preserve_the_backend(codec,state,threshold):
    native={objects.INDEX['PLAYER_BYTES_2']:state<<24|7<<16|3,
            objects.INDEX['PLAYER_REST_STATE_EXPERIENCE']:threshold}
    snapshot={'guid':1,'fields':native};character={'name':'Harnessone','gender':0}
    active=result(codec,op='object_values',snapshot=snapshot,character=character)['ActivePlayerData']
    assert active['RestInfo']==[{'StateID':state,'Threshold':threshold},{'StateID':2,'Threshold':0}]


@pytest.mark.parametrize('fields',[
    ['PLAYER_BYTES_2'],['PLAYER_REST_STATE_EXPERIENCE'],
    ['PLAYER_BYTES_2','PLAYER_REST_STATE_EXPERIENCE']])
def test_rest_update_uses_pinned_array_and_nested_masks(codec,fields):
    native={objects.INDEX['PLAYER_BYTES_2']:1<<24|4,
            objects.INDEX['PLAYER_REST_STATE_EXPERIENCE']:900}
    changed={objects.INDEX[name]:native[objects.INDEX[name]] for name in fields}
    body=bytes.fromhex(result(codec,op='rest_update',snapshot={'guid':17,'fields':native},changed=changed))
    r=Reader(body)
    assert r.unpack('B')==(0,)
    assert r.guid()==(17,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('BBBI')==(1,0,3,1<<7)
    assert r.unpack('I')==(1<<9,)
    assert r.bits(14)==0
    assert r.bits(32)==(1<<22)|(1<<23)
    r.flush()
    threshold='PLAYER_REST_STATE_EXPERIENCE' in fields
    state='PLAYER_BYTES_2' in fields
    assert r.bits(3)==1|int(threshold)<<1|int(state)<<2
    if threshold:assert r.unpack('I')==(900,)
    if state:assert r.unpack('B')==(1,)
    r.end()
    assert result(codec,op='rest_update',snapshot={'guid':17,'fields':native},changed={})==''
