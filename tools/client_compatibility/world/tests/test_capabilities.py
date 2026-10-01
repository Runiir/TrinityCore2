"""Check normal-client capabilities and cast ownership across the two protocols."""
from types import SimpleNamespace
import struct
import pytest

from tools.client_compatibility.world import casting, initialization
from tools.client_compatibility.world.buffer import Reader, Writer, player_high


def request(unit=(0, 0), cast=(42, 47 << 58), target_flags=0):
    return (Writer().guid(*cast).pack("iiiIff", 0, 0, 80451, 123, 0, 0)
            .guid().pack("IIIB", 0, 0, 0, 0).bits(0, 9).flush()
            .bits(target_flags, 28).bits(0, 11).guid(*unit).guid().finish())


def test_survey_cast_preserves_spell_and_client_identity():
    owner = SimpleNamespace(character={"guid": 1})
    body, spell = casting.request(owner, request())
    assert struct.unpack("<BiiBI", body) == (1, 80451, 0, 0, 0)
    failed = struct.pack("<BiBI", 1, 80451, 99, 1234)
    modern = Reader(casting.response(owner, "SMSG_CAST_FAILED", failed))
    assert modern.guid() == (42, 47 << 58)
    assert modern.unpack("iI")[0] == 80451
    assert casting.response(owner, "SMSG_CAST_FAILED", struct.pack("<BiB", 2, 80451, 99)) is None
    assert casting.cancel(owner, Writer().guid(42, 47 << 58).pack("I", 80451).finish()) == struct.pack("<BI", 1, 80451)
    with pytest.raises(ValueError):
        casting.cancel(owner, Writer().guid(43, 47 << 58).pack("I", 80451).finish())


@pytest.mark.parametrize("body", [request(unit=(2, player_high()), target_flags=2),
    request(unit=(1, 3 << 58), target_flags=2), request(cast=(42, player_high())),
    request()[:-1], request() + b"\x00"])
def test_foreign_or_malformed_cast_is_rejected(body):
    owner = SimpleNamespace(character={"guid": 1})
    with pytest.raises(ValueError): casting.request(owner, body)
    assert not hasattr(owner, "casts")


def test_initial_spells_and_stance_buttons_are_not_invented():
    native = struct.pack("<BH", 1, 2) + struct.pack("<IhIhH", 80451, 0, 89722, 0, 0)
    r = Reader(initialization.known_spells(native))
    assert r.bits(1) == 1
    assert r.unpack("II") == (2, 0)
    assert r.unpack("II") == (80451, 89722)
    r.end()
    buttons = [0] * 144
    buttons[73] = 80451
    modern = initialization.action_buttons(struct.pack("<144IB", *buttons, 0))
    assert struct.unpack_from("<Q", modern, 73 * 8)[0] == 80451
    assert len(modern) == 1441


def test_actual_60895_survey_request_layout():
    body = bytes.fromhex("018702c2904ebc0000000000000000433a010067f1050000000000000000000000000000000000000000000000000000000000000000000000")
    owner = SimpleNamespace(character={"guid": 1})
    encoded, spell = casting.request(owner, body)
    assert spell == 80451
    assert len(encoded) == 14


def test_actual_native_survey_start_keeps_destination_and_cast_identity():
    body = bytes.fromhex("0101010101433a01000208000000000000e80300004000000000ab9c23c6aa0ae1c38874394200000000")
    owner = SimpleNamespace(character={"guid": 1}, casts={1: {
        "guid": (1, 47 << 58), "server_guid": (2, 47 << 58), "spell": 80451, "visual": 389479}})
    ack = Reader(casting.prepare(owner, body))
    assert ack.guid() == (1, 47 << 58)
    assert ack.guid() == (2, 47 << 58)
    ack.end()
    r = Reader(casting.response(owner, "SMSG_SPELL_START", body))
    assert r.guid() == (1, player_high())
    assert r.guid() == (1, player_high())
    assert r.guid() == (2, 47 << 58)
    assert r.guid() == (0, 0)
    assert r.unpack("iIIII") == (80451, 389479, 0x40802, 0, 1000)


def test_game_object_and_loot_require_native_visibility():
    from tools.client_compatibility.world import gameobjects, looting
    native = (0xF11 << 52) | (203071 << 32) | 123
    record = {"map": 0}
    owner = SimpleNamespace(character={"map": 0}, visible_gameobjects={native: record})
    identity = gameobjects.modern_guid(native, 0)
    assert identity == (123, (11 << 58) | (1 << 42) | (203071 << 6))
    assert looting.request(owner, "CMSG_GAME_OBJ_USE", Writer().guid(*identity).finish()) == [("CMSG_GAMEOBJ_USE", struct.pack("<Q", native))]
    with pytest.raises(ValueError): looting.request(owner, "CMSG_GAME_OBJ_USE", Writer().guid(124, identity[1]).finish())
    packet = struct.pack("<QBIBBBII", native, 1, 0, 0, 1, 0, 384, 5)
    name, _ = looting.response(owner, "SMSG_LOOT_RESPONSE", packet)
    assert name == "SMSG_LOOT_RESPONSE"
    loot = Writer().pack("I", 1).guid(*owner.loot["guid"]).pack("B", 0).bits(0, 1).finish()
    assert looting.request(owner, "CMSG_LOOT_ITEM", loot) == [("CMSG_LOOT_CURRENCY", b"\x00")]
    duplicate = Writer().pack("I", 2).guid(*owner.loot["guid"]).pack("B", 0).guid(*owner.loot["guid"]).pack("B", 0).bits(0, 1).finish()
    with pytest.raises(ValueError): looting.request(owner, "CMSG_LOOT_ITEM", duplicate)


def test_actual_archaeology_gather_click_is_owned_and_forwarded():
    from tools.client_compatibility.world.native_objects import guid
    native = (0xF11 << 52) | (203071 << 32) | 1559
    owner = SimpleNamespace(character={"guid": 1, "map": 0}, visible_gameobjects={native: {"map": 0}})
    body = bytes.fromhex("018707c23e48bc0000000000000000fb20010035e3050000000000000000000000000000000000000000000000000000000080000003a71706c04fc6042c0000")
    encoded, spell = casting.request(owner, body)
    r = Reader(encoded)
    assert r.unpack("BiiBI") == (1, 73979, 0, 0, 2048)
    assert guid(r) == native
    r.end()
    assert spell == 73979
    assert owner.casts[1]["server_guid"][1] & 63 == 3
    foreign = SimpleNamespace(character={"guid": 1}, visible_gameobjects={})
    with pytest.raises(ValueError): casting.request(foreign, body)
    r = Reader(casting.rejected(body))
    assert r.guid()[1] >> 58 == 47
    assert r.unpack("i")[0] == 73979


def test_destroyed_telescope_is_removed_from_client_and_authority():
    from tools.client_compatibility.world import gameobjects
    native = (0xF11 << 52) | (206590 << 32) | 123
    owner = SimpleNamespace(visible_gameobjects={native: {"map": 0}})
    r = Reader(gameobjects.destroy(owner, struct.pack("<QB", native, 0)))
    assert r.unpack("HI") == (0, 0)
    assert (r.bits(1), r.bits(1)) == (1, 1)
    assert r.unpack("HI") == (1, 1)
    assert r.guid() == gameobjects.modern_guid(native, 0)
    assert r.unpack("I") == (0,)
    r.end()
    assert not owner.visible_gameobjects


def test_new_research_project_can_be_serialized_after_first_fragment():
    from tools.client_compatibility.world.fields import serialize
    w = Writer()
    serialize(w, "ActivePlayerData", {"Research": [[{"ResearchProjectID": 203}]], "NumBackpackSlots": 16})
    assert len(w.finish()) > 100


@pytest.mark.parametrize("name,fmt", [("SMSG_SPELL_FAILURE", "H"), ("SMSG_SPELL_FAILED_OTHER", "B")])
def test_interrupted_survey_ends_the_owned_server_cast(name, fmt):
    owner = SimpleNamespace(character={"guid": 1})
    casting.request(owner, request())
    native = casting.packed(Writer(), 1).pack("BiB", 1, 80451, 46).finish()
    r = Reader(casting.response(owner, name, native))
    assert r.guid() == (1, player_high())
    assert r.guid() == owner.casts[1]["server_guid"]
    assert r.unpack("iI" + fmt) == (80451, 123, 67)
    r.end()
