import pytest
from tools.client_compatibility.interaction_recipe_navigation import drag_points


def probe():
    return {'count':318,'slider':{'low':0,'high':4960,'value':0,'track_top':18000,'track_bottom':26000,
        'thumb':{'x':45000,'y':18000}}}


def test_recipe_scrollbar_uses_row_ratio_with_pixel_unit_slider_and_clamped_endpoints():
    p=probe();start,end=drag_points(p,122)
    assert start==[879,198] and end==[879,232]
    assert drag_points(p,0)[1][1]<start[1]
    assert drag_points(p,310)[1][1]>round(26000/65535*720)


@pytest.mark.parametrize('change',[
    lambda p:p['slider'].update(high=0),lambda p:p['slider'].update(track_bottom=100),
    lambda p:p['slider'].update(value=float('nan')),lambda p:p['slider']['thumb'].update(x=70000)])
def test_recipe_scrollbar_rejects_unusable_or_foreign_viewport_geometry(change):
    p=probe();change(p)
    with pytest.raises(RuntimeError,match='invalid'):drag_points(p,122)


def test_recipe_scrollbar_rejects_offsets_outside_the_visible_catalog():
    with pytest.raises(RuntimeError,match='invalid'):drag_points(probe(),311)
