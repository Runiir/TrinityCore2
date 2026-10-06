"""A paid failure may be retained only with its owned purchase/learn/catalog sequence."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_pet_training_disconnect import proof,catalog
from tools.client_compatibility.interaction_pet_control_training import persisted_training


PET=(0xf14<<52)|(416<<32)|13
NPC=(0xf13<<52)|(906<<32)|120395


def sample():
    failed={'native_session':'owned','purchase_started_at':10,'finished_at':20}
    selected={'native_trainer_guid':NPC}
    body=struct.pack('<QHIBBH10IBIB',PET,23,0,3,1,0,*([0x07000001]*10),1,0xc1000c26,0).hex()
    rows=[]
    for time,direction,name,value in [(11,'from_client','CMSG_TRAINER_BUY_SPELL','00'),
        (12,'to_native','CMSG_TRAINER_BUY_SPELL',struct.pack('<QII',NPC,154,80388).hex()),
        (13,'from_native','SMSG_LEARNED_SPELL','bf6c010000000000'),
        (14,'to_client','SMSG_LEARNED_SPELLS','010000000000000000bf6c010000'),
        (15,'from_native','SMSG_PET_SPELLS',body)]:
        rows.append(dict(session='owned',time=time,direction=direction,name=name,body=value))
    events=[dict(session='owned',time=15.1,event='native_stream_closed',error='unsupported native pet mode')]
    return failed,selected,rows,events


def test_paid_failure_keeps_exact_packet_and_assist_mode():
    value=proof(*sample())
    assert value['catalog']['guid']==PET and value['catalog']['react']==3
    assert value['catalog']['actions']==[0xc1000c26]


@pytest.mark.parametrize('change',['session','duplicate','wrong_npc','wrong_spell','wrong_learn',
    'late_close','wrong_error','other_mode','client_catalog','out_of_order','trailing','purchase_trailing'])
def test_paid_failure_refuses_unattributable_purchase_or_catalog(change):
    failed,selected,rows,events=copy.deepcopy(sample())
    if change=='session':rows[1]['session']='foreign'
    elif change=='duplicate':rows.append(dict(rows[1]))
    elif change=='wrong_npc':selected['native_trainer_guid']+=1
    elif change=='wrong_spell':rows[1]['body']=struct.pack('<QII',NPC,154,688).hex()
    elif change=='wrong_learn':rows[2]['body']='0000000000000000'
    elif change=='late_close':events[0]['time']=17
    elif change=='wrong_error':events[0]['error']='unrelated failure'
    elif change=='other_mode':
        b=bytearray.fromhex(rows[4]['body']);b[14]=2;rows[4]['body']=b.hex()
    elif change=='client_catalog':rows.append(dict(rows[4],direction='to_client',name='SMSG_PET_SPELLS_MESSAGE'))
    elif change=='out_of_order':rows[2]['time']=16
    elif change=='trailing':rows[4]['body']+='00'
    elif change=='purchase_trailing':rows[1]['body']+='00'
    with pytest.raises((RuntimeError,ValueError)):proof(failed,selected,rows,events)


def test_catalog_reader_preserves_all_native_types_without_reencoding():
    parsed=catalog(sample()[2][4]['body'])
    assert parsed['buttons']==[0x07000001]*10 and parsed['cooldowns']==[]


@pytest.mark.parametrize('after,relation,expected',[
    ([[80388,1,0]],[[80388,93375,1]],True),
    ([[93375,1,0]],[[80388,93375,1]],False),
    ([[80388,1,0],[93375,1,0]],[[80388,93375,1]],False),
    ([[80388,1,0]],[[80388,93375,0]],False)])
def test_native_dependent_training_persists_parent_without_granting_child(after,relation,expected):
    assert persisted_training([],after,relation) is expected
