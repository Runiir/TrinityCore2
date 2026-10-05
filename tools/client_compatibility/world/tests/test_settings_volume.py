"""Numeric serialization must not hide a changed or invalid volume fixture."""
import copy
import pytest
from tools.client_compatibility.interaction_settings_volume import layout_checks,value


def fixture():
    return {'search':'','category':{'name':'Controls','id':5},'unapplied':False,
        'cvars':{'Sound_MasterVolume':'1.0','Sound_EnableAllSound':'0'},
        'values':{'Sound_MasterVolume':1,'Sound_EnableAllSound':False}}


def test_numeric_volume_serialization_preserves_the_setting():
    original=fixture();current=copy.deepcopy(original);current['cvars']['Sound_MasterVolume']='1'
    assert all(layout_checks(current,original).values())


def test_changed_volume_cannot_be_accepted_as_restored():
    original=fixture();current=copy.deepcopy(original)
    current['cvars']['Sound_MasterVolume']='0.95';current['values']['Sound_MasterVolume']=.95
    checks=layout_checks(current,original)
    assert not checks['cvars'] and not checks['values']


@pytest.mark.parametrize('change',['other_value','missing_cvar','extra_cvar'])
def test_only_master_volume_numeric_formatting_is_normalized(change):
    original=fixture();current=copy.deepcopy(original)
    if change=='other_value':current['cvars']['Sound_EnableAllSound']='1'
    elif change=='missing_cvar':current['cvars'].pop('Sound_EnableAllSound')
    else:current['cvars']['unexpected']='0'
    assert not layout_checks(current,original)['cvars']


@pytest.mark.parametrize('cvar,setting',[('nan',1),('1',float('nan')),('inf',1),('1',.95),('1.01',1.01)])
def test_invalid_or_disagreeing_public_volume_values_are_rejected(cvar,setting):
    probe=fixture();probe['cvars']['Sound_MasterVolume']=cvar;probe['values']['Sound_MasterVolume']=setting
    with pytest.raises(RuntimeError,match='disagree'):value(probe)
