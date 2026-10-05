"""Read the whole 60895 enumeration independently of its native serializer.

Pinned WPP 28fc3d1 CharacterHandler.ReadBasicCharacterListEntry places Flags
before Flags2/Flags3 and nineteen 22-byte visual records. Classic CharacterFlags
HideHelm/HideCloak retain 0x400/0x800, unlike world PlayerFlagsEx.
"""
import pytest
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


NATIVE_PAIRS=[{'race':1,'class':1,'expansion':0},{'race':3,'class':1,'expansion':0},
    {'race':3,'class':5,'expansion':0}]


def read_characters(body,unlocked=(1,3)):
    r=Reader(bytes.fromhex(body));assert r.bits(9)==0x122
    head=r.unpack('IIiIIIII');assert head[1:]==(0,85,len(unlocked),0,0,0,0)
    found=[]
    for _ in range(head[0]):
        guid=r.guid();realm,slot,race,gender,cls,spec,custom=r.unpack('IBBBBhI')
        level,map_id,zone,x,y,z,club=r.unpack('Bii3fQ');guild=r.guid()
        flags=r.unpack('IIIBIII');gear=[r.unpack('IBIBiII') for _ in range(19)]
        tail=r.unpack('iQi5iIIiI');length=r.bits(6);first=r.bits(1)
        name=r.raw(length).decode();assert r.bits(3)==0 and r.unpack('III')==(0,0,0)
        found.append({'guid':guid,'slot':slot,'flags':flags,'gear':gear,'name':name,
            'tail':tail,'first_login':first,'realm':realm})
    for race in unlocked:
        assert r.unpack('i')==(race,) and (r.bits(1),r.bits(1),r.bits(3))==(1,1,0)
    r.end()
    return found


@pytest.mark.parametrize('hidden',[0,0x400,0x800,0xc00])
def test_saved_visibility_reaches_each_owned_character_without_shifting_gear(codec,hidden):
    base={'slot':0,'race':1,'gender':0,'class':1,'level':85,'map':0,'zone':10,
        'position_x':-10471,'position_y':-450,'position_z':50,'logout_time':123,'at_login':0}
    characters=[dict(base,guid=1,name='Harnessone',characterFlags=hidden|0x2000),
        dict(base,guid=2,slot=1,name='Harnesstwo',characterFlags=hidden^0xc00)]
    body=result(codec,op='character_list',characters=characters,
        equipment=[{'guid':1,'slot':0,'itemEntry':78688},{'guid':1,'slot':14,'itemEntry':77097}],
        displays=[[78688,103376,1,4],[77097,102947,16,1]],race_classes=NATIVE_PAIRS)
    rows=read_characters(body)
    assert [x['guid'] for x in rows]==[(1,player_high()),(2,player_high())]
    assert [x['name'] for x in rows]==['Harnessone','Harnesstwo']
    assert [x['flags'] for x in rows]==[(hidden,0,0,0,0,0,0),(hidden^0xc00,0,0,0,0,0,0)]
    assert rows[0]['gear'][0]==(103376,1,0,4,0,78688,0)
    assert rows[0]['gear'][14]==(102947,16,0,1,0,77097,0)
    assert all(x==(0,0,0,0,0,0,0) for x in rows[1]['gear'])
    assert [x['tail'][2] for x in rows]==[60895,60895]
    assert [x['realm'] for x in rows]==[0x01010001]*2


def test_empty_account_enumeration_has_no_synthetic_character(codec):
    assert read_characters(result(codec,op='character_list',characters=[],equipment=[],displays=[],race_classes=NATIVE_PAIRS))==[]


def test_enum_does_not_invent_unlocked_races_when_native_capabilities_are_empty(codec):
    assert read_characters(result(codec,op='character_list',characters=[],equipment=[],displays=[],race_classes=[]),unlocked=())==[]
