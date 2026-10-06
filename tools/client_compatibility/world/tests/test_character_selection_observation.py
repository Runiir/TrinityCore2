"""Character selection must consume the declared native race-unlock list."""
import pytest
from tools.client_compatibility.observation.character_selection import characters
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


@pytest.mark.parametrize('races',[[],[1],[1,2,3,4,5,6,7,8,9,10,11,22]])
def test_enumeration_consumes_every_declared_unlock_entry(codec,races):
    body=result(codec,op='character_list',characters=[],equipment=[],displays=[],
        race_classes=[{'race':race,'class':1,'expansion':0} for race in races])
    assert characters(bytes.fromhex(body))==[]


def test_owned_primary_gear_and_packed_realm_survive_multi_race_trailer(codec):
    c={'guid':1,'name':'Harnessone','slot':0,'race':1,'gender':0,'class':1,'level':85,'map':0,
        'zone':3,'position_x':-6396,'position_y':-3343,'position_z':260,'logout_time':100,'characterFlags':0}
    body=result(codec,op='character_list',characters=[c],
        equipment=[{'guid':1,'slot':0,'itemEntry':78688}],displays=[[78688,103376,1,4]],
        race_classes=[{'race':race,'class':1,'expansion':0} for race in [1,3,22]])
    rows=characters(bytes.fromhex(body))
    assert rows==[{'guid':[1,(2<<58)|(1<<42)],'name':'Harnessone','flags':0,
        'equipment':[78688]+[0]*18,'level':85,'slot':0,'realm':0x01010001}]
