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
