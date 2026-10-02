"""Late raid-frame reads cannot disconnect the authenticated realm after logout."""
from tools.client_compatibility.world.buffer import Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


def test_final_party_stats_refresh_after_logout_is_consumed_without_native_forwarding(codec):
    body=Writer().bits(0,1).guid(2,player_high()).finish().hex()
    assert result(codec,op='late_party_query',active=False,name='CMSG_REQUEST_PARTY_MEMBER_STATS',body=body) is True
    assert result(codec,op='late_party_query',active=True,name='CMSG_REQUEST_PARTY_MEMBER_STATS',body=body) is False
    assert result(codec,op='late_party_query',active=False,name='CMSG_REQUEST_PARTY_JOIN_UPDATES',body='00') is True
    for name in ['CMSG_LEAVE_GROUP','CMSG_PARTY_INVITE','CMSG_SET_PARTY_LEADER']:
        assert result(codec,op='late_party_query',active=False,name=name,body='') is False
    for bad in ['',body+'00']:
        assert 'error' in codec(op='late_party_query',active=False,name='CMSG_REQUEST_PARTY_MEMBER_STATS',body=bad)
