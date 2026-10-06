import copy
import math
from . import portal_view,runtime
from .test_farm_loop import row
import pytest


def test_hints_require_named_interaction_and_observed_destination(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before=row();before['movement']['facing_radians']=1.2;before['farm_ui']['camera_zoom']=25
    p={'key':'tb-org','from':before['archaeology']['world'],
        'destination':'Orgrimmar','to':{'instance':2,'north':100,'west':200}}
    after=copy.deepcopy(before);after['archaeology']['world']=p['to']
    assert not portal_view.remember(p,before,{'name':'Party Options'},after)
    assert not portal_view.remember(p,before,{'name':'Portal to Orgrimmar'},before)
    assert portal_view.remember(p,before,{'name':'Portal to Orgrimmar'},after,evidence='closed receipt')
    hint=portal_view.read(p,before)
    assert hint['facing_radians']==1.2 and hint['zoom']==25
    target=portal_view.aim(hint,before)
    assert math.isclose(math.atan2(target['west'],target['north']),1.2)
    changed=copy.deepcopy(before);changed['runtime']['pid']=9
    assert portal_view.read(p,changed) is None


@pytest.mark.parametrize('change',[None,'position','facing','zoom','viewport'])
def test_verified_cursor_is_reused_only_as_a_probe_from_a_matching_view(monkeypatch,tmp_path,change):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before=row();before['movement']['facing_radians']=1.2;before['farm_ui']['camera_zoom']=5.5
    p={'key':'tb-org','from':before['archaeology']['world'],'destination':'Orgrimmar',
        'to':{'instance':732,'north':100,'west':200}}
    after=copy.deepcopy(before);after['archaeology']['world']=p['to']
    assert portal_view.remember(p,before,{'name':'Portal to Orgrimmar','cursor':{'x':.5625,'y':380/900}},after)
    hint=portal_view.read(p,before)
    if change=='position':before['archaeology']['world']['north']+=2
    elif change=='facing':before['movement']['facing_radians']+=.3
    elif change=='zoom':before['farm_ui']['camera_zoom']+=2
    elif change=='viewport':hint['viewport']=[1920,1080]
    assert portal_view.search_point(hint,before)==((720,380) if change is None else None)
