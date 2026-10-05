"""A loaded hidden panel must still publish read-only settings at bounded intervals."""
import copy,json,shutil,subprocess
from pathlib import Path
import pytest
from tools.client_compatibility.interaction_settings_discard import recovery_matches


def test_hidden_loaded_settings_are_observed_every_ten_state_ticks():
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SettingsObservation.lua'
    program='dofile('+json.dumps(str(source))+''')
    local hidden={IsVisible=function() return false end}
    local visible={IsVisible=function() return true end}
    for tick=1,30 do
        assert(Client442ShouldObserveSettings(nil,tick)==false)
        assert(Client442ShouldObserveSettings(visible,tick)==true)
        assert(Client442ShouldObserveSettings(hidden,tick)==(tick%10==0))
    end
    '''
    subprocess.run([lua,'-'],input=program,text=True,check=True,capture_output=True)


def receipt():
    return {'finished_at':1,'completed':False,'failure':'RuntimeError: settings diagnostic did not become visible',
        'actor':{'guid':1},'runtime':{'client':{'pid':2,'start_ticks':'3'}},
        'native_baseline':{'resources':{'money':10},'pose':{'stand':1}},
        'native_restoration':{'checks':{key:True for key in
            ['resources','stats','spells','actions','pose','afk','position','group','no_lua_errors','no_blocked_actions']}}}


def test_exact_closed_source_matches_recovery_fixture():
    old=receipt();assert recovery_matches(old,copy.deepcopy(old))


@pytest.mark.parametrize('change',['open','completed','other_failure','actor','runtime','cleanup','missing_check','native_value'])
def test_stale_or_unrestored_source_refuses_recovery(change):
    old=receipt();current=copy.deepcopy(old)
    if change=='open':old['finished_at']=None
    elif change=='completed':old['completed']=True
    elif change=='other_failure':old['failure']='other'
    elif change=='actor':current['actor']['guid']=2
    elif change=='runtime':current['runtime']['client']['start_ticks']='4'
    elif change=='cleanup':old['native_restoration']['checks']['pose']=False
    elif change=='missing_check':old['native_restoration']['checks'].pop('stats')
    else:current['native_baseline']['resources']['money']=9
    assert not recovery_matches(old,current)
