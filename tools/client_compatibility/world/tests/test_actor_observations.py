import json
import pytest
from tools.client_compatibility.observation import archaeology,transport,journal
from tools.client_compatibility.world.buffer import Writer,player_high
from tools.client_compatibility.world.objects import INDEX


def write(path,records):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(record)+'\n' for record in records))


def entry(guid,session,time):
    return {'event':'native_player_created','guid':guid,'session':session,'time':time,
        'map':530,'position':[guid,0,0,0]}


def packet(session,name,body,direction='from_client',time=3):
    return {'session':session,'name':name,'body':body.hex(),'direction':direction,'time':time}


def moving(guid,x):
    return Writer().guid(guid,player_high()).pack('IIII6fII',1,0,0,42,x,0,0,0,0,0,0,0).bits(0,8).finish()


def test_explicit_actor_and_session_ignore_newer_other_login(tmp_path,monkeypatch):
    write(tmp_path/'logs/modern_world.jsonl',[entry(7,'a',1),entry(1,'b',2),entry(7,'new-a',4)])
    assert journal.player_entry(tmp_path,7,'a')['session']=='a'
    assert journal.player_entry(tmp_path,7)['session']=='new-a'
    assert journal.player_entry(tmp_path)['session']=='b'
    monkeypatch.setenv('CLIENT442_CHARACTER_GUID','7')
    assert journal.player_entry(tmp_path)['session']=='new-a'
    with pytest.raises(RuntimeError):journal.player_entry(tmp_path,8)
    with pytest.raises(RuntimeError):journal.player_entry(tmp_path,7,'b')


@pytest.mark.parametrize('guid',['0','-1','bad','1.5','4294967296',True])
def test_invalid_actor_identity_is_rejected(guid):
    with pytest.raises(ValueError):journal.character_guid(guid)


def test_two_observers_accept_only_their_normal_movement(tmp_path):
    write(tmp_path/'logs/modern_world.jsonl',[entry(7,'a',1),entry(1,'b',2)])
    write(tmp_path/'evidence/world_packets.jsonl',[
        packet('a','CMSG_MOVE_START_FORWARD',moving(7,70)),
        packet('b','CMSG_MOVE_START_FORWARD',moving(1,10))])
    a=transport.Observer(guid=7,session='a',root=tmp_path)
    b=transport.Observer(guid=1,session='b',root=tmp_path)
    assert a.poll()['position'][0]==70 and b.poll()['position'][0]==10
    assert archaeology.Observer(guid=7,session='a',root=tmp_path).poll(0)['player']['position'][0]==70
    # A foreign mover inside this actor's session remains a protocol error.
    with (tmp_path/'evidence/world_packets.jsonl').open('a') as handle:
        handle.write(json.dumps(packet('a','CMSG_MOVE_START_FORWARD',moving(1,999)))+'\n')
    with pytest.raises(ValueError):a.poll()


def test_visible_tools_are_filtered_by_actual_creator_not_guid_one(tmp_path,monkeypatch):
    write(tmp_path/'logs/modern_world.jsonl',[entry(7,'a',1),entry(1,'b',2)])
    tool_guid=(0xf11<<52)|(204272<<32)|17
    def records(body):
        owner=int(body[0]);return [{'update_type':2,'kind':5,'guid':tool_guid+owner,'map':530,
            'movement':{'position':[owner,0,0,0]},'fields':{INDEX['OBJECT_FIELD_CREATED_BY']:owner}}]
    monkeypatch.setattr(archaeology,'records',records)
    write(tmp_path/'evidence/world_packets.jsonl',[
        packet('a','SMSG_UPDATE_OBJECT',bytes([7]),'from_native'),
        packet('a','SMSG_UPDATE_OBJECT',bytes([1]),'from_native'),
        packet('b','SMSG_UPDATE_OBJECT',bytes([1]),'from_native')])
    observed=archaeology.Observer(guid=7,session='a',root=tmp_path).poll(0)
    assert observed['tool']['position'][0]==7


def test_attack_events_use_selected_player_identity(tmp_path):
    write(tmp_path/'logs/modern_world.jsonl',[entry(7,'a',1),entry(1,'b',2)])
    write(tmp_path/'evidence/world_packets.jsonl',[
        packet('a','SMSG_ATTACK_START',Writer().pack('QQ',99,7).finish(),'from_native'),
        packet('a','SMSG_ATTACK_START',Writer().pack('QQ',88,1).finish(),'from_native'),
        packet('b','SMSG_ATTACK_START',Writer().pack('QQ',66,7).finish(),'from_native')])
    assert transport.Observer(guid=7,session='a',root=tmp_path).poll()['attacking_units']==[99]
