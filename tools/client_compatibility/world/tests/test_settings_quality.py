"""Pending presets require complete child agreement and unchanged native settings."""
import copy
import pytest
from tools.client_compatibility.interaction_settings_quality import CHILDREN,VARIABLE,fixture,checks


def baseline():
    children={key:1 for key in CHILDREN.values()}
    return {'cvars':{key:'1' for key in ['graphicsQuality',*CHILDREN,'RenderScale']},
        'values':{VARIABLE:1,**children,'PROXY_RESOLUTION':'1280x720'},'unapplied':False,
        'discard_dialogs':[],'lower_graphics_quality':0,'lower_graphics_values':{
            key:1 if key=='PROXY_PARTICLE_DENSITY' else 0 for key in CHILDREN.values()}}


def pending(old):
    current=copy.deepcopy(old);current['values'].update(old['lower_graphics_values'])
    current['values'][VARIABLE]=0;current['unapplied']=True;return current


def test_complete_lower_pending_map_keeps_every_native_cvar_fixed():
    old=baseline();assert fixture(old)==1
    assert all(checks(pending(old),old,True).values())
    assert all(checks(copy.deepcopy(old),old,False).values())


@pytest.mark.parametrize('change',['native','child','missing_child','quality_bool','unapplied','resolution','missing_native'])
def test_partial_or_applied_change_cannot_pass_as_pending_preset(change):
    old=baseline();current=pending(old)
    if change=='native':current['cvars']['graphicsShadowQuality']='0'
    elif change=='child':current['values']['PROXY_SHADOW_QUALITY']=1
    elif change=='missing_child':current['values'].pop('PROXY_SHADOW_QUALITY')
    elif change=='quality_bool':current['values'][VARIABLE]=False
    elif change=='unapplied':current['unapplied']=False
    elif change=='resolution':current['values']['PROXY_RESOLUTION']='1920x1080'
    else:current['cvars'].pop('graphicsSunshafts')
    assert not all(checks(current,old,True).values())


@pytest.mark.parametrize('change',['quality_bool','missing_map','wrong_level','particle_minimum','native_mismatch','missing_cvar'])
def test_unverified_fixture_refuses_before_quality_input(change):
    old=baseline()
    if change=='quality_bool':old['values'][VARIABLE]=True
    elif change=='missing_map':old['lower_graphics_values'].pop('PROXY_SUNSHAFTS')
    elif change=='wrong_level':old['lower_graphics_quality']=1
    elif change=='particle_minimum':old['lower_graphics_values']['PROXY_PARTICLE_DENSITY']=0
    elif change=='native_mismatch':old['cvars']['graphicsShadowQuality']='0'
    else:old['cvars'].pop('graphicsSunshafts')
    with pytest.raises(RuntimeError):fixture(old)
