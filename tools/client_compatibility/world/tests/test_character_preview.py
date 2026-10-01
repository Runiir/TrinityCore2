"""Classic 60895 character-list equipment uses 19 records of 22 bytes."""
from tools.client_compatibility.world import characters
from tools.client_compatibility.world.buffer import Reader


def test_equipped_items_have_display_inventory_subclass_and_item_id(monkeypatch):
    character={'guid':1,'slot':0,'race':1,'gender':0,'class':1,'level':85,'map':0,
        'zone':10,'position_x':-10471,'position_y':-450,'position_z':50,'logout_time':0,'name':'Harnessone'}
    gear=[None]*19;gear[0]=(103376,1,0,4,0,78688,0);gear[15]=(103383,17,0,8,0,78478,0)
    seen=[]
    monkeypatch.setattr(characters,'rows',lambda account:seen.append(account) or [character])
    monkeypatch.setattr(characters,'visual_equipment',lambda account:seen.append(account) or {1:gear})
    r=Reader(characters.enumeration(7));r.bits(9);r.unpack('IIiIIIII');r.guid()
    r.unpack('IBBBBhIBii3fQ');r.guid();r.unpack('IIIBIII')
    slots=[r.unpack('IBIBiII') for _ in range(19)]
    assert slots[0]==gear[0] and slots[15]==gear[15]
    assert all(row==(0,0,0,0,0,0,0) for i,row in enumerate(slots) if i not in [0,15])
    assert seen==[7,7]
    assert r.unpack('iQi5iIIiI')[2]==60895
    length=r.bits(6);r.bits(1);assert r.raw(length)==b'Harnessone'
    r.bits(3);r.unpack('IIIi');assert (r.bits(1),r.bits(1),r.bits(3))==(1,1,0);r.end()
