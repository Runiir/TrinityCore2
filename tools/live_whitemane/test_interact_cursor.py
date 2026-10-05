from types import SimpleNamespace
from . import interact,runtime


def test_a_named_tooltip_is_not_accepted_at_the_previous_cursor_position(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before={'farm_ui':{'sequence':7}}
    def frame(sequence,x,y):
        return {'farm_ui':{'sequence':sequence,'cursor':{'x':x/1280,'y':y/900},
            'tooltip':'Night Elf Archaeology Find'}}
    frames=iter([frame(8,620,540),frame(9,600,520)])
    monkeypatch.setattr(interact,'observe',lambda _:next(frames))
    monkeypatch.setattr(interact,'stationary',lambda *_:None)
    sleeps=[]
    monkeypatch.setattr(interact,'time',SimpleNamespace(monotonic=lambda:0,sleep=lambda n:sleeps.append(n)))
    moves=[]
    observed=interact.hover(SimpleNamespace(move=lambda x,y:moves.append((x,y))),(600,520),before,tmp_path)
    assert observed['farm_ui']['sequence']==9 and moves==[(600,520)] and sleeps==[.02]


def test_confirming_a_hover_waits_for_the_object_tooltip_after_cursor_arrival(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before={'farm_ui':{'sequence':7}}
    def frame(sequence,tooltip):
        return {'farm_ui':{'sequence':sequence,'cursor':{'x':600/1280,'y':520/900},'tooltip':tooltip}}
    frames=iter([frame(8,None),frame(9,'Night Elf Archaeology Find')])
    monkeypatch.setattr(interact,'observe',lambda _:next(frames))
    monkeypatch.setattr(interact,'stationary',lambda *_:None)
    monkeypatch.setattr(interact,'time',SimpleNamespace(monotonic=lambda:0,sleep=lambda _:None))
    observed=interact.hover(SimpleNamespace(move=lambda *args:None),(600,520),before,tmp_path,
        expected='Night Elf Archaeology Find')
    assert observed['farm_ui']['sequence']==9


def test_search_uses_the_actual_named_mouseover_without_claiming_cursor_arrival(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before={'farm_ui':{'sequence':7}}
    fresh={'farm_ui':{'sequence':8,'cursor':{'x':591/1280,'y':520/900},
        'tooltip':'Night Elf Archaeology Find'}}
    monkeypatch.setattr(interact,'observe',lambda _:fresh)
    monkeypatch.setattr(interact,'stationary',lambda *_:None)
    moves=[]
    observed=interact.hover(SimpleNamespace(move=lambda *point:moves.append(point)),
        (600,540),before,tmp_path,allow_found=True)
    assert moves==[(600,540)]
    assert observed['farm_ui']['cursor']=={'x':591/1280,'y':520/900}
