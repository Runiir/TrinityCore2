"""Stock control targets require typed public agreement, including native CVars."""
import copy
import pytest
from tools.client_compatibility.interaction_settings_controls import agrees,interact_fixture_restorable
from tools.client_compatibility.interaction_settings_controls_recovery import source_layout


@pytest.mark.parametrize('wanted',[False,True])
def test_move_pad_requires_public_setting_and_cvar_agreement(wanted):
    probe={'values':{'enableMovePad':wanted},'cvars':{'enableMovePad':str(int(wanted))}}
    assert agrees(probe,'enableMovePad',wanted)
    probe['cvars']['enableMovePad']=str(int(not wanted))
    assert not agrees(probe,'enableMovePad',wanted)


def test_move_pad_cannot_pass_without_its_cvar():
    assert not agrees({'values':{'enableMovePad':True},'cvars':{}},'enableMovePad',True)


@pytest.mark.parametrize('actual',[1,'1',None])
def test_proxy_setting_does_not_accept_an_untyped_truthy_value(actual):
    assert not agrees({'values':{'PROXY_ENABLE_INTERACT':actual}},'PROXY_ENABLE_INTERACT',True)


@pytest.mark.parametrize('wanted',[False,True])
def test_proxy_setting_uses_its_registered_public_boolean(wanted):
    probe={'values':{'PROXY_ENABLE_INTERACT':wanted},'cvars':{'softTargetInteract':'3' if wanted else '1'}}
    assert agrees(probe,'PROXY_ENABLE_INTERACT',wanted)
    probe['values']['PROXY_ENABLE_INTERACT']=not wanted
    assert not agrees(probe,'PROXY_ENABLE_INTERACT',wanted)


@pytest.mark.parametrize('wanted',[0,1])
def test_non_boolean_requested_targets_are_rejected(wanted):
    with pytest.raises(ValueError,match='boolean'):agrees({},'enableMovePad',wanted)


@pytest.mark.parametrize('flag,wanted,accepted',[('0',False,True),('1',False,True),('3',True,True),
    ('3',False,False),('1',True,False),('2',False,False),(None,False,False)])
def test_interact_proxy_requires_observed_supported_flags(flag,wanted,accepted):
    assert agrees({'values':{'PROXY_ENABLE_INTERACT':wanted},'cvars':{'softTargetInteract':flag}},
        'PROXY_ENABLE_INTERACT',wanted)==accepted


def interact_layout():
    return {'cvars':{'softTargetInteract':'0','enableMovePad':'0'},
        'values':{'PROXY_ENABLE_INTERACT':False,'enableMovePad':False},
        'interact_keys':{'known':True,'primary':'','secondary':''},'move_pad_visible':False,'unapplied':False}


def test_exact_proxy_fixture_difference_can_be_recovered():
    original=interact_layout();current=copy.deepcopy(original);current['cvars']['softTargetInteract']='1'
    assert interact_fixture_restorable(current,original)


@pytest.mark.parametrize('change',['flag','other_cvar','missing_cvar','extra_cvar','proxy','binding','pad','pending'])
def test_proxy_cleanup_rejects_other_fixture_changes(change):
    original=interact_layout();current=copy.deepcopy(original);current['cvars']['softTargetInteract']='1'
    if change=='flag':current['cvars']['softTargetInteract']='3'
    elif change=='other_cvar':current['cvars']['enableMovePad']='1'
    elif change=='missing_cvar':current['cvars'].pop('enableMovePad')
    elif change=='extra_cvar':current['cvars']['unexpected']='0'
    elif change=='proxy':current['values']['PROXY_ENABLE_INTERACT']=True
    elif change=='binding':current['interact_keys']['primary']='F'
    elif change=='pad':current['move_pad_visible']=True
    else:current['unapplied']=True
    assert not interact_fixture_restorable(current,original)


def closed_proxy_failure():
    layout=interact_layout();last=copy.deepcopy(layout);last['cvars']['softTargetInteract']='1'
    return {'completed':False,'finished_at':1,'failure':
        'RuntimeError: panel cleanup did not change state; refusing to replay Escape',
        'actor':{'guid':1},'runtime':{'client':{'pid':1}},
        'code_commit':'5806289004811953b1c0fe829a03c06237c5cd1c',
        'cases':[{'id':k,'status':'stock_control_setting_pass'} for k in ('settings.interface.change',
            'settings.interface.restore','settings.keyboard_controls.change','settings.keyboard_controls.restore')],
        'control_layout_baseline':layout,'settings_details':{
            'fixture.restore_stock_controls_restored':{'state':{'settings_probe':last}}},
        'volume_layout_restoration':{'checks':{'search':True,'category':True,'values':True,'unapplied':True,'cvars':False}}}


def test_closed_proxy_failure_identifies_the_exact_source():
    old=closed_proxy_failure()
    assert source_layout(old,old['actor'],old['runtime'])==old['control_layout_baseline']


@pytest.mark.parametrize('change',['live','success','failure','actor','runtime','commit','case','layout','cvar'])
def test_proxy_recovery_rejects_unrelated_or_live_sources(change):
    old=closed_proxy_failure();fixture=copy.deepcopy(old['actor']);runtime=copy.deepcopy(old['runtime'])
    if change=='live':old['finished_at']=None
    elif change=='success':old['completed']=True
    elif change=='failure':old['failure']='different failure'
    elif change=='actor':old['actor']['guid']=2
    elif change=='runtime':old['runtime']['client']['pid']=2
    elif change=='commit':old['code_commit']='different source'
    elif change=='case':old['cases'][-1]['status']='client_or_protocol_failure'
    elif change=='layout':old['volume_layout_restoration']['checks']['values']=False
    else:old['settings_details']['fixture.restore_stock_controls_restored']['state']['settings_probe']['cvars']['enableMovePad']='1'
    with pytest.raises(RuntimeError,match='exact closed'):source_layout(old,fixture,runtime)
