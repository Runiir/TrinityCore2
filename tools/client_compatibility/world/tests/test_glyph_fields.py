"""Glyph layouts require nine owner slot identities as well as learned glyphs."""
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import mask

SLOTS=INDEX['PLAYER_FIELD_GLYPH_SLOTS_1'];GLYPHS=INDEX['PLAYER_FIELD_GLYPHS_1'];ENABLED=INDEX['PLAYER_GLYPHS_ENABLED']
NATIVE_SLOTS=[21,22,23,24,25,26,41,42,43]
MODERN_SLOTS=[22,41,42,23,43,25,21,24,26]


def test_glyph_create_maps_socket_types_without_reordering_values_or_unlock_mask(codec):
    fields={**{SLOTS+i:n for i,n in enumerate(NATIVE_SLOTS)},**{GLYPHS+i:100+i for i in range(9)},ENABLED:67}
    active=result(codec,op='object_values',snapshot={'fields':fields},character={})['ActivePlayerData']
    assert active['GlyphSlots']==MODERN_SLOTS and active['Glyphs']==list(range(100,109)) and active['GlyphsEnabled']==67
    # 60895 DB2 types are 0 Prime, 1 Major and 2 Minor. Native level-25
    # sockets (bits 0,1,6) still unlock one of each semantic type.
    types={21:0,22:1,23:1,24:0,25:1,26:0,41:2,42:2,43:2}
    assert [types[n]+1 for n in active['GlyphSlots']]==[2,3,3,2,3,2,1,1,1]
    assert sorted(types[active['GlyphSlots'][i]] for i in range(9) if 67>>i&1)==[0,1,2]


def test_sparse_glyph_updates_preserve_clears_last_slot_and_only_owner_fields(codec):
    fields={SLOTS+8:43,GLYPHS:0,GLYPHS+8:109,ENABLED:511}
    body=result(codec,op='glyph_update',snapshot={'guid':1,'fields':fields},changed=fields)
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos and r.unpack('BBBI')==(1,0,3,1<<7)
    assert mask(r,46,first32=True)=={96,127,1410,1419,1420,1428};r.align()
    assert r.unpack('H')==(511,)
    assert r.unpack('3I')==(0,26,109);r.end()
    assert result(codec,op='glyph_update',snapshot={'guid':1,'fields':fields},changed={INDEX['UNIT_FIELD_HEALTH']:100})==''
    assert 'error' in codec(op='glyph_update',snapshot={'guid':1,'fields':{ENABLED:512}},changed={ENABLED:512})


def test_sparse_glyph_slot_mapping_matches_creation_and_rejects_unknown_rows(codec):
    fields={SLOTS+i:n for i,n in enumerate(NATIVE_SLOTS)}
    body=result(codec,op='glyph_update',snapshot={'guid':1,'fields':fields},changed=fields)
    r=Reader(bytes.fromhex(body));r.unpack('B');r.guid();r.unpack('I');r.unpack('BBBI')
    assert mask(r,46,first32=True)==set(range(1410,1420));r.align()
    assert list(r.unpack('9I'))==MODERN_SLOTS;r.end()
    invalid={SLOTS:27}
    assert 'error' in codec(op='glyph_update',snapshot={'guid':1,'fields':invalid},changed=invalid)
    assert 'error' in codec(op='object_values',snapshot={'fields':invalid},character={})
