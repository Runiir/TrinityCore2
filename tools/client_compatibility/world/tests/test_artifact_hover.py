from tools.client_compatibility import archaeology_inputs as subject


def test_high_sloping_ground_artifact_is_reached_within_short_search():
    points=subject.find_hover_points()
    # Trial 60's faced artifact was above y=240 in all three dry stances.
    assert points.index((640,176))<5
    assert points.index((640,208))<10
    assert points.index((640,240))<14
    # Baa'ri's thin, tilted interaction shape can miss a 16-pixel scan.
    assert points.index((640,248))<15
    assert points.index((640,264))<17
    assert len(points)==len(set(points))


def test_stale_artifact_tooltip_requires_a_fresh_confirmation(monkeypatch,tmp_path):
    from PIL import Image
    path=tmp_path/'latest.png';Image.new('RGB',(1,1)).save(path)
    checksum=next(iter(subject.FIND_CHECKSUMS))
    monkeypatch.setattr(subject.time,'sleep',lambda _:None)
    monkeypatch.setattr(subject,'find_hover_points',lambda:[(640,176),(640,208)])
    values=iter([checksum,0,0,checksum,0,checksum])
    monkeypatch.setattr(subject,'screenshot',lambda _:(None,{'tooltip_name_checksum':next(values)}))
    class Inputs:
        def __init__(self):self.moves=[]
        def move(self,x,y):self.moves.append((x,y))
    inputs=Inputs()
    assert subject.locate_find(inputs,path,timeout=12)==(640,208)
    assert inputs.moves==[(640,176),(400,100),(640,176),(640,208),(400,100),(640,208)]
    assert (tmp_path/'localized_find.webp').exists()


def test_object_expiry_stops_cursor_search_without_a_click(monkeypatch,tmp_path):
    from tools.client_compatibility.find_interaction import FindExpired
    import pytest
    def expired():raise FindExpired('removed in owned packets')
    class Inputs:
        def move(self,*_):raise AssertionError('expired object must not be hovered')
    with pytest.raises(FindExpired):
        subject.locate_find(Inputs(),tmp_path/'unused.png',require_visible=expired)
