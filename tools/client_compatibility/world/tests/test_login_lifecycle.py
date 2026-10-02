"""Each new instance receives its world before legacy initialization updates."""
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec, result, action
from tools.client_compatibility.world.tests.test_logout_account_cache import update


def packet(name, body=''):
    return dict(fn='packet', name=name, body=body)


def test_login_world_precedes_early_aura_and_bind_then_preserves_wire_order(codec):
    early = [packet('SMSG_AURA_UPDATE', '010200'), packet('SMSG_BIND_POINT_UPDATE', '00'*20)]
    world = packet('SMSG_LOGIN_VERIFY_WORLD', '00'*20)
    out = result(codec, op='login_barrier', actions=[dict(fn='begin'), *early, world,
                 packet('SMSG_UPDATE_OBJECT', '010203')])
    assert [row['packets'] for row in out[:2]] == [[], []]
    assert out[2] == dict(packets=[[p['name'], p['body']] for p in [world, *early]],
                          pending=False, queued=0, bytes=0)
    assert out[3]['packets'] == [['SMSG_UPDATE_OBJECT', '010203']]


def test_account_cache_replies_are_available_while_waiting_for_login_world(codec):
    packets = [packet(name, '0102') for name in ['SMSG_ACCOUNT_DATA_TIMES',
               'SMSG_UPDATE_ACCOUNT_DATA', 'SMSG_UPDATE_ACCOUNT_DATA_COMPLETE']]
    out = result(codec, op='login_barrier', actions=[dict(fn='begin'), *packets])
    assert all(row == dict(packets=[[p['name'], p['body']]], pending=True, queued=0, bytes=0)
               for row, p in zip(out, packets))


def test_login_queue_and_duplicate_login_are_bounded(codec):
    assert codec(op='login_barrier', actions=[dict(fn='begin'), dict(fn='begin')]) == {
        'error': 'repeated native login barrier'}
    assert codec(op='login_barrier', actions=[dict(fn='begin')] + [packet('SMSG_UPDATE_OBJECT')]*513) == {
        'error': 'native login initialization exceeds bounded queue'}


def test_logout_clears_previous_world_but_preserves_final_owned_settings_route(codec):
    assert result(codec, op='logout_reset') == dict(last_guid=2, account_time=123, callback=True,
        created=False, character=None, snapshot=None, world_entries=0)
    out = result(codec, op='stateful', character={'guid': 2}, snapshot={'guid': 2},
        gameobjects=[], units=[], actions=[action('logout_complete', '', b''),
        action('account_request', 'CMSG_UPDATE_ACCOUNT_DATA', update())])
    assert out[0] is None and out[1] == ['CMSG_UPDATE_ACCOUNT_DATA', '030000007b00000000000000']
