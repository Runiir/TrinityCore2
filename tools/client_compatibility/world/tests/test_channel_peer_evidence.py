"""Peer evidence must distinguish native counts from modern channel identity."""
import pytest
from tools.client_compatibility.interaction_channel_peer import wire_updates
from tools.client_compatibility.world.buffer import Writer,player_high


@pytest.mark.parametrize('opcode,count',[('SMSG_USERLIST_UPDATE',2),('SMSG_USERLIST_REMOVE',1)])
def test_peer_wire_evidence_requires_both_correct_fields(opcode,count):
    channel='TC442UIChannel1234abcd'
    def rows(member_count,channel_id,guid=2):
        native=Writer().pack('Q',guid);modern=Writer().guid(guid,player_high())
        if opcode!='SMSG_USERLIST_REMOVE':native.pack('B',0);modern.pack('B',0)
        native.pack('BI',1,member_count).raw(channel.encode()+b'\0')
        modern.pack('II',1,channel_id).bits(len(channel),7).raw(channel.encode())
        return [{'direction':direction,'name':opcode,'body':body.finish().hex()}
            for direction,body in [('from_native',native),('to_client',modern)]]
    assert all(wire_updates(rows(count,0),channel,opcode,count)['checks'].values())
    assert not wire_updates(rows(count,count),channel,opcode,count)['checks']['modern_peer_channel_identity']
    assert not wire_updates(rows(count+1,0),channel,opcode,count)['checks']['native_peer_update']
    assert not any(wire_updates(rows(count,0,3),channel,opcode,count)['checks'].values())
