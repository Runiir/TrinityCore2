from tools.client_compatibility import hostile_avoidance as h
from tools.client_compatibility.world.objects import INDEX


def test_visible_living_hostiles_only_and_vertical_clearance(monkeypatch):
    player=[1,1,0,1,1,8,*([0]*8)]
    enemy=[2,14,0,8,8,1,*([0]*8)]
    monkeypatch.setattr(h,'factions',lambda:{1:player,2:enemy})
    unit={'map':0,'movement':{'position':[10,20,3,0]},'fields':{
        INDEX['UNIT_FIELD_FACTIONTEMPLATE']:2,INDEX['UNIT_FIELD_LEVEL']:58,
        INDEX['UNIT_FIELD_HEALTH']:100}}
    hostiles=h.visible_hostiles({123:unit},0,1,85)
    assert len(hostiles)==1 and hostiles[0]['clearance_radius']==9.5
    assert not h.clear([10,20,3],hostiles)
    assert h.clear([10,20,30],hostiles) and h.clear([30,20,3],hostiles)
    unit['fields'][INDEX['UNIT_FIELD_HEALTH']]=0
    assert h.visible_hostiles({123:unit},0,1,85)==[]
