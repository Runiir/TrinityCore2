"""Reject stale Apply state, higher allocations and changed graphics fixtures."""
import copy
import pytest
from tools.client_compatibility.interaction_render_scale import VARIABLE,scale,value_checks


def fixture():
    return {'cvars':{'RenderScale':'1','gxResolution':'1280x720','gxMonitor':'0'},
        'values':{VARIABLE:1,'PROXY_RESOLUTION':'1280x720'},'unapplied':False}


def test_pending_lower_scale_does_not_claim_an_applied_change():
    baseline=fixture();current=copy.deepcopy(baseline);current['values'][VARIABLE]=.99;current['unapplied']=True
    assert all(value_checks(current,baseline,1,.99,True).values())
    assert not value_checks(current,baseline,.99,.99,False)['actual_render_scale']
    assert not value_checks(current,baseline,1,.99,False)['unapplied_state']


@pytest.mark.parametrize('field',['actual','pending','unapplied','resolution','monitor','other_setting'])
def test_restoration_rejects_changed_or_unapplied_graphics_state(field):
    baseline=fixture();current=copy.deepcopy(baseline)
    if field=='actual':current['cvars']['RenderScale']='.99'
    elif field=='pending':current['values'][VARIABLE]=.99
    elif field=='unapplied':current['unapplied']=True
    elif field=='resolution':current['cvars']['gxResolution']='1920x1080'
    elif field=='monitor':current['cvars']['gxMonitor']='1'
    else:current['values']['PROXY_RESOLUTION']='1920x1080'
    assert not all(value_checks(current,baseline,1,1,False).values())


@pytest.mark.parametrize('actual,pending',[('nan',1),('inf',1),('1',True),('1',float('nan')),('1.1',1),(1,1.1),('0',1)])
def test_invalid_scale_and_increased_allocation_are_rejected(actual,pending):
    current=fixture();current['cvars']['RenderScale']=actual;current['values'][VARIABLE]=pending
    with pytest.raises(RuntimeError):scale(current)


def test_equal_cvar_numeric_serialization_does_not_hide_other_changes():
    baseline=fixture();current=copy.deepcopy(baseline);current['cvars']['RenderScale']='1.000000'
    assert all(value_checks(current,baseline,1,1,False).values())
