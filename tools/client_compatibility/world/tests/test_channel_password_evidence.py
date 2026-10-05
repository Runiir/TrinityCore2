"""Gate evidence needs matching native and modern notices for the owned actor."""
import pytest
from tools.client_compatibility.interaction_channel_password import notice
from tools.client_compatibility.world.buffer import Writer,player_high


@pytest.mark.parametrize('kind,guid',[(4,0),(7,1)])
def test_password_notice_requires_both_wire_directions_and_exact_actor(kind,guid):
    name='TC442UIChannel1234abcd'
    native=Writer().pack('B',kind).raw(name.encode()+b'\0')
    if kind==7:native.pack('Q',guid)
    modern=Writer().bits(kind,6).bits(len(name),7).bits(0,6).guid(guid,player_high() if guid else 0)
    modern.guid().pack('I',0x01010001).guid().pack('II',0x01010001,0).raw(name.encode())
    rows=[{'direction':d,'name':'SMSG_CHANNEL_NOTIFY','body':body.finish().hex()}
        for d,body in [('from_native',native),('to_client',modern)]]
    assert notice(rows,name,kind,guid)['matches']
    assert not notice(rows[:1],name,kind,guid)['matches']
    assert not notice(rows,'TC442UIChannel99999999',kind,guid)['matches']
    if kind==7:assert not notice(rows,name,kind,2)['matches']
