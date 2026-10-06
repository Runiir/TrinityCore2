import copy
import math
from . import portal_view,runtime
from .test_farm_loop import row


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
