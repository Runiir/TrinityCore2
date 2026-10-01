from tools.client_compatibility import flightmaster_input as subject


def test_high_nearby_npc_is_searched_before_center_only_budget_runs_out():
    points=subject.hover_points()
    # Loop 53 showed Furgu's body around y=190..235, above the old search.
    assert points.index((640,208))<8
    assert len(points)==len(set(points))


def test_fading_tooltip_cannot_supply_an_unconfirmed_click(monkeypatch,tmp_path):
    from PIL import Image
    from tools.client_compatibility import archaeology_inputs
    path=tmp_path/'latest.png';Image.new('RGB',(1,1)).save(path)
    monkeypatch.setattr(subject.time,'sleep',lambda _:None)
    monkeypatch.setattr(subject,'hover_points',lambda:[(640,192),(640,208)])
    # First hover is a stale tip, but returning to its point does not show it.
    values=iter([123,0,0,123,0,123])
    monkeypatch.setattr(archaeology_inputs,'screenshot',lambda _:(None,{'tooltip_name_checksum':next(values)}))
    class Inputs:
        def __init__(self):self.moves=[]
        def move(self,x,y):self.moves.append((x,y))
    inputs=Inputs()
    assert subject.locate(inputs,path,123)==[640,208]
    assert inputs.moves==[(640,192),(400,100),(640,192),(640,208),(400,100),(640,208)]
    assert (tmp_path/'localized_flightmaster.webp').exists()


def test_telaar_failed_landing_walks_into_real_interaction_range(monkeypatch,tmp_path):
    from tools.client_compatibility import archaeology_inputs,ground_navigation,travel_inputs
    import math
    start=[-2717.008789,7302.118164,88.590179,3.625399]
    goal=[-2723.1,7302.84,88.7157]
    position=start.copy()
    class Observer:
        def poll(self):return {'position':position.copy()}
    class Inputs:
        def key(self,key,hold):
            assert key=='w'
            position[0]+=math.cos(position[3])*hold*7
            position[1]+=math.sin(position[3])*hold*7
    def face(_,observer,target):
        position[3]=math.atan2(target[1]-position[1],target[0]-position[0]);return []
    monkeypatch.setattr(subject.time,'sleep',lambda _:None)
    monkeypatch.setattr(travel_inputs,'face',face)
    monkeypatch.setattr(ground_navigation,'route',lambda *_:{'points':[start[:3],goal[:]],'ground_only':True})
    monkeypatch.setattr(archaeology_inputs,'screenshot',lambda _:(
        {'in_world':True,'dead':False,'in_combat':False,'on_taxi':False},
        {'mounted':False,'flying':False,'falling':False,'swimming':False}))
    result=subject.approach(Inputs(),Observer(),530,goal,tmp_path/'latest.png')
    assert math.dist(start[:3],goal)>6
    assert math.dist(result['after'][:3],goal)<=4
    assert result['physical_keys']
