import pytest
from . import taxi
from .test_farm_loop import row


def test_an_unknown_origin_uses_the_fresh_named_native_npc_at_its_coordinates():
    r=row();r['farm_ui']['soft_interact'].update(name='Kurzel',exists=True)
    origin={'id':652,'point':r['archaeology']['world']}
    assert taxi.origin_names(r,origin)=={'Kurzel'}
    assert taxi.origin_names(r,{'id':23,'point':origin['point']})=={'Doras'}
    r['farm_ui']['soft_interact']['exists']=False
    with pytest.raises(RuntimeError,match='no named flight master candidate'):taxi.origin_names(r,origin)
    r['farm_ui']['soft_interact']['exists']=True
    origin['point']={**origin['point'],'north':3}
    with pytest.raises(RuntimeError,match='no named flight master candidate'):taxi.origin_names(r,origin)


def test_confirmed_flight_master_interacts_without_exact_coordinate_or_extra_movement_choice(monkeypatch,tmp_path):
    import copy
    r=row();r['archaeology']['falling']=False;r['farm_ui']['soft_interact']['name']='Doras'
    node={'id':531,'label':'Dawnrise','enabled':True,'state':1,'x':.5,'y':.5,'fare_copper':900}
    menu=copy.deepcopy(r);menu['farm_ui']['taxi']=[node]
    end={'instance':1,'north':100,'west':0}
    arrived=copy.deepcopy(r);arrived['archaeology']['world']=end
    frames=iter([r,menu,menu,menu,arrived,arrived])
    monkeypatch.setattr(taxi,'observe',lambda _:next(frames))
    def choose(state,which,physical_state):
        action='arrived' if physical_state['destination_reached'] else 'taxi' if physical_state['taxi_map_open'] else 'interact'
        return action,{}, {},{}
    monkeypatch.setattr(taxi,'choose',choose)
    monkeypatch.setattr(taxi,'walk',lambda *_ ,**__:pytest.fail('already named NPC needs no coordinate approach'))
    monkeypatch.setattr(taxi.interact,'use',lambda *_:{'completed':True})
    monkeypatch.setattr(taxi,'stationary',lambda *_:None)
    sent=[];monkeypatch.setattr(taxi.inputs,'execute',lambda *args:sent.append(args[-1]) or {})
    monkeypatch.setattr(taxi.time,'sleep',lambda _:None)
    result=taxi.run(tmp_path/'taxi',{'id':23,'point':{'instance':1,'north':5,'west':0}},
        {'id':531,'point':end})
    assert result['completed'] and len(sent)==1
    assert result['phases'][0]['approach']['exact_coordinate_required'] is False
    assert result['phases'][1]['selected']['fare_copper']==900
