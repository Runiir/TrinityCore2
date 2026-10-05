"""Stock control targets require typed public agreement, including native CVars."""
import copy
from types import SimpleNamespace
import pytest
from tools.client_compatibility.interaction_settings_controls import agrees,interact_fixture_restorable,validate_layout,restore_interact_fixture
from tools.client_compatibility.interaction_trial import Trial
from tools.client_compatibility.interaction_settings_controls_recovery import source_layout,verify_resume


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


def test_exact_historical_proxy_fixture_difference_is_identifiable():
    original=interact_layout();current=copy.deepcopy(original);current['cvars']['softTargetInteract']='1'
    assert interact_fixture_restorable(current,original)


def test_script_restore_is_refused_before_any_input():
    original=interact_layout();current=copy.deepcopy(original);current['cvars']['softTargetInteract']='1'
    t=SimpleNamespace(receipt={},persist=lambda:None)
    with pytest.raises(RuntimeError,match='custom scripts stay blocked'):
        restore_interact_fixture(t,original,current,'never_send')
    assert t.receipt['unrestored_cvars']=={'softTargetInteract':{'original':'0','after':'1'}}
    assert t.receipt['custom_script_permission']=='blocked_by_user'


@pytest.mark.parametrize('flag,wanted',[('1',False),('3',True)])
def test_canonical_stock_proxy_start_can_roundtrip_without_scripts(flag,wanted):
    layout=interact_layout();layout['cvars']['softTargetInteract']=flag
    layout['values']['PROXY_ENABLE_INTERACT']=wanted
    validate_layout(layout,['enableMovePad','PROXY_ENABLE_INTERACT'])


def test_original_none_is_rejected_in_the_all_settings_preflight():
    with pytest.raises(RuntimeError,match='original0 cannot restore'):
        validate_layout(interact_layout(),['enableMovePad','PROXY_ENABLE_INTERACT'])


@pytest.mark.parametrize('text',['/run SetCVar("softTargetInteract", 0)',' /SCRIPT x()','/console softTargetInteract 0'])
def test_script_commands_are_refused_before_input_initialization(text):
    with pytest.raises(RuntimeError,match='blocked by user instruction'):
        Trial.__new__(Trial).submit_chat(text)


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


def closed_menu_failure():
    return {'completed':False,'finished_at':1,'failure':
        'RuntimeError: operation did not advance: settings.inspect_menu client_or_protocol_failure',
        'actor':{'guid':1},'runtime':{'client':{'pid':1}},'source':{'path':'original','sha256':'digest'},
        'source_preflight':{'native':{str(i):True for i in range(10)}},'cases':[
            {'id':'fixture.recover_interact_none_close','status':'settings_panel_closed'},
            {'id':'fixture.recover_interact_none_console','status':'fixture_console_submitted'},
            {'id':'settings.inspect_menu','status':'client_or_protocol_failure','after':{'panels':[],'chat_edit_open':False}}]}


def test_post_console_resume_requires_the_closed_menu_transition():
    old=closed_menu_failure();verify_resume(old,old['source'],old['actor'],old['runtime'])


@pytest.mark.parametrize('change',['live','source','case','panel','chat','native','missing_native'])
def test_post_console_resume_rejects_changed_or_incomplete_sources(change):
    old=closed_menu_failure();source=copy.deepcopy(old['source'])
    if change=='live':old['finished_at']=None
    elif change=='source':old['source']['sha256']='different'
    elif change=='case':old['cases'][1]['status']='infrastructure_failure'
    elif change=='panel':old['cases'][-1]['after']['panels']=['GameMenuFrame']
    elif change=='chat':old['cases'][-1]['after']['chat_edit_open']=True
    elif change=='native':old['source_preflight']['native']['0']=False
    else:old['source_preflight']['native'].pop('0')
    with pytest.raises(RuntimeError,match='post-console'):verify_resume(old,source,old['actor'],old['runtime'])
