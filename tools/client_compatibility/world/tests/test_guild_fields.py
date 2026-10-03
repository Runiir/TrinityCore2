"""Native guild membership reaches the initial player and sparse join/leave masks."""
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec, result
from tools.client_compatibility.world.tests.test_inventory_packets import read_block, mask

GUILD_HIGH = (28 << 58) | (1 << 42)


def fields(guild=1):
    # Native OBJECT_FIELD_DATA observed on the live guild fixture: [1,535822336].
    return {INDEX['OBJECT_FIELD_DATA']: guild, INDEX['OBJECT_FIELD_DATA']+1: 0x1ff00000 if guild else 0,
        INDEX['PLAYER_GUILDRANK']: 0, INDEX['PLAYER_GUILDLEVEL']: 1 if guild else 0,
        INDEX['PLAYER_GUILD_TIMESTAMP']: 123 if guild else 0, INDEX['PLAYER_FLAGS']: 1 << 28 if guild else 0}


def test_native_membership_create_uses_guild_guid_and_level(codec):
    out = result(codec, op='object_values', snapshot={'kind': 4, 'fields': fields()}, character={})
    assert out['UnitData']['GuildGUID'] == [1, GUILD_HIGH]
    assert out['PlayerData']['GuildRankID'] == 0 and out['PlayerData']['GuildLevel'] == 1
    assert out['PlayerData']['GuildTimeStamp'] == 123


def test_sparse_join_and_leave_send_public_membership_and_zero_rank(codec):
    for guild in [1, 0]:
        native = fields(guild)
        block = result(codec, op='guild_update', snapshot={'guid': 1, 'kind': 4, 'fields': native},
                       changed=native, character={})
        r = read_block(block, (1, player_high()), (1 << 5) | (1 << 6))
        assert mask(r, 8) == {96, 108};r.align()
        assert r.guid() == ((guild, GUILD_HIGH) if guild else (0, 0))
        assert mask(r, 5) == {0, 9, 10, 11, 13, 22}
        assert r.bits(1) == 0;r.align()
        assert r.unpack('IIIii') == (native[INDEX['PLAYER_FLAGS']], 0, 0,
            native[INDEX['PLAYER_GUILDLEVEL']], native[INDEX['PLAYER_GUILD_TIMESTAMP']]);r.end()


def test_unrelated_delta_does_not_emit_membership_and_invalid_native_identity_rejected(codec):
    args = dict(op='guild_update', snapshot={'guid': 1, 'kind': 4, 'fields': fields()}, character={})
    assert result(codec, **args, changed={}) == ''
    wrong = fields();wrong[INDEX['OBJECT_FIELD_DATA']+1] = 0x40000000
    assert codec(op='object_values', snapshot={'kind': 4, 'fields': wrong}, character={}) == {
        'error': 'invalid native guild identity'}
