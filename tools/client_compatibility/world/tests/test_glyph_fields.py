"""Glyph layouts require nine owner slot identities as well as learned glyphs."""
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import mask

SLOTS=INDEX['PLAYER_FIELD_GLYPH_SLOTS_1'];GLYPHS=INDEX['PLAYER_FIELD_GLYPHS_1'];ENABLED=INDEX['PLAYER_GLYPHS_ENABLED']


def test_glyph_create_preserves_all_nine_slots_values_and_enabled_mask(codec):
    fields={**{SLOTS+i:21+i for i in range(9)},**{GLYPHS+i:100+i for i in range(9)},ENABLED:511}
    active=result(codec,op='object_values',snapshot={'fields':fields},character={})['ActivePlayerData']
    assert active['GlyphSlots']==list(range(21,30)) and active['Glyphs']==list(range(100,109)) and active['GlyphsEnabled']==511


def test_sparse_glyph_updates_preserve_clears_last_slot_and_only_owner_fields(codec):
    fields={SLOTS+8:29,GLYPHS:0,GLYPHS+8:109,ENABLED:511}
    body=result(codec,op='glyph_update',snapshot={'guid':1,'fields':fields},changed=fields)
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos and r.unpack('BBBI')==(1,0,3,1<<7)
    assert mask(r,46,first32=True)=={96,127,1410,1419,1420,1428};r.align()
    assert r.unpack('H')==(511,)
    assert r.unpack('3I')==(0,29,109);r.end()
    assert result(codec,op='glyph_update',snapshot={'guid':1,'fields':fields},changed={INDEX['UNIT_FIELD_HEALTH']:100})==''
    assert 'error' in codec(op='glyph_update',snapshot={'guid':1,'fields':{ENABLED:512}},changed={ENABLED:512})
