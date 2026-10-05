"""Pending display selection cannot pass after an active size/mode or unrelated change."""
import copy
import pytest
from tools.client_compatibility.interaction_display_pending import SPECS,candidate,checks,fixture,recon_matches


def baseline():
    return {'cvars':{'gxMaximize':'0','gxMonitor':'0','RenderScale':'1'},
        'values':{'PROXY_RESOLUTION':'1280x720','PROXY_DISPLAY_MODE':False,'PROXY_PRIMARY_MONITOR':0,
            'PROXY_GRAPHICS_QUALITY':1},'unapplied':False,'discard_dialogs':[],
        'display_state':{'monitor':0,'fullscreen':False,'screen_width':1280,'screen_height':720,
            'window_size':{'width':1280,'height':720}}}


@pytest.mark.parametrize('kind,wanted',[('resolution','1280x800'),('window_mode',True),('monitor_selection',1)])
def test_pending_stock_option_and_exact_restoration_keep_active_display_fixed(kind,wanted):
    old=baseline();fixture(old);current=copy.deepcopy(old)
    current['values'][SPECS[kind][1]]=wanted;current['unapplied']=True
    assert all(checks(current,old,kind,True,wanted).values())
    assert all(checks(copy.deepcopy(old),old,kind,False).values())


@pytest.mark.parametrize('change',['native_mode','native_monitor','window_size','screen_size','other_setting','pending_flag'])
def test_applied_or_unrelated_change_cannot_qualify_pending_selection(change):
    old=baseline();current=copy.deepcopy(old);current['values']['PROXY_DISPLAY_MODE']=True;current['unapplied']=True
    if change=='native_mode':current['cvars']['gxMaximize']='1'
    elif change=='native_monitor':current['cvars']['gxMonitor']='1'
    elif change=='window_size':current['display_state']['window_size']['width']=1920
    elif change=='screen_size':current['display_state']['screen_height']=1080
    elif change=='other_setting':current['values']['PROXY_GRAPHICS_QUALITY']=2
    else:current['unapplied']=False
    assert not all(checks(current,old,'window_mode',True,True).values())


@pytest.mark.parametrize('kind,value',[('resolution','0x0'),('resolution','3840x2160'),('resolution','1280x720'),
    ('resolution',True),('window_mode',1),('monitor_selection',True)])
def test_untyped_unchanged_or_unbounded_candidate_is_rejected(kind,value):
    assert not candidate(kind,value,baseline()['values'][SPECS[kind][1]])


@pytest.mark.parametrize('change',['no_size','foreign_size','unknown_mode','bool_monitor','pending'])
def test_unverified_active_fixture_refuses_before_selection(change):
    old=baseline()
    if change=='no_size':old['display_state'].pop('window_size')
    elif change=='foreign_size':old['display_state']['window_size']['height']=1080
    elif change=='unknown_mode':old['cvars'].pop('gxMaximize')
    elif change=='bool_monitor':old['display_state']['monitor']=False
    else:old['unapplied']=True
    with pytest.raises(RuntimeError):fixture(old)


def source():
    return {'completed':True,'finished_at':1,'actor':{'guid':1},'runtime':{'client':{'pid':2,'start_ticks':'3'}},
        'settings_layout_restoration':{'checks':{key:True for key in ['search','category','values','unapplied','cvars']}},
        'native_restoration':{'checks':{key:True for key in
            ['resources','stats','spells','actions','pose','afk','position','group','no_lua_errors','no_blocked_actions']}},
        'settings_recon':[{'term':row[0]} for row in SPECS.values()]}


def test_closed_owned_recon_and_all_restoration_checks_match():
    old=source();assert recon_matches(old,copy.deepcopy(old),list(SPECS))


@pytest.mark.parametrize('change',['open','failed','actor','runtime','missing_layout','missing_native','failed_cleanup','wrong_term',
    'unknown_native_check'])
def test_incomplete_or_other_recon_refuses_before_input(change):
    old=source();current=copy.deepcopy(old)
    if change=='open':old['finished_at']=None
    elif change=='failed':old['completed']=False
    elif change=='actor':current['actor']['guid']=2
    elif change=='runtime':current['runtime']['client']['start_ticks']='4'
    elif change=='missing_layout':old['settings_layout_restoration']['checks'].pop('cvars')
    elif change=='missing_native':old['native_restoration']['checks'].pop('pose')
    elif change=='failed_cleanup':old['native_restoration']['checks']['pose']=False
    elif change=='unknown_native_check':
        old['native_restoration']['checks']['unknown']=old['native_restoration']['checks'].pop('pose')
    else:old['settings_recon']=[]
    assert not recon_matches(old,current,list(SPECS))
