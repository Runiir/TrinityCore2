"""The owned instance may acknowledge its mover before native player creation."""
import pytest
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec, result


def ack(**changes):
    return {'fn':'ack','body':'00000000','active_instance':True,**changes}


def test_early_ack_waits_for_native_creation_and_releases_once(codec):
    out=result(codec,op='login_active_mover',guid=4,actions=[{'fn':'begin'},ack(),ack(),
        {'fn':'world'},{'fn':'create'},{'fn':'create'}])
    assert [r['forward'] for r in out]==[False,False,False,False,True,False]
    assert out[2]['deferred'] is True and out[3]['awaiting_player'] is True
    assert out[4]['deferred'] is False and out[4]['awaiting_player'] is False


def test_normal_ack_after_native_creation_forwards_without_deferral(codec):
    out=result(codec,op='login_active_mover',guid=4,actions=[{'fn':'begin'},
        {'fn':'world'},{'fn':'create'},ack()])
    assert [r['forward'] for r in out]==[False,False,False,True]


@pytest.mark.parametrize('change',[{'active_instance':False},{'body':''},
    {'body':'000000'},{'body':'0000000000'}])
def test_foreign_channel_and_bad_ack_width_are_rejected(codec,change):
    assert 'error' in codec(op='login_active_mover',guid=4,actions=[{'fn':'begin'},ack(**change)])


@pytest.mark.parametrize('guid,actions',[(0,[{'fn':'begin'},ack()]),
    (4,[ack()]),(4,[{'fn':'begin'},ack(),{'fn':'logout'},ack()])])
def test_ack_requires_owned_login_or_created_player_and_logout_clears_it(codec,guid,actions):
    assert 'error' in codec(op='login_active_mover',guid=guid,actions=actions)


def test_logout_discards_pending_ack_before_next_owned_login(codec):
    out=result(codec,op='login_active_mover',guid=4,actions=[{'fn':'begin'},ack(),
        {'fn':'logout'},{'fn':'begin'},{'fn':'world'},{'fn':'create'}])
    assert not any(r['forward'] for r in out)
