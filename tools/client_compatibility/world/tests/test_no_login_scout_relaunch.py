"""Never restart a scout that may have entered the world or has an open trial."""
from copy import deepcopy
import pytest
from tools.client_compatibility.interaction_offline_scout_relaunch import no_login


def data():
    fixture={'guid':6,'class':3};runtime={'worldserver':{'pid':1},'client':{'pid':2}}
    ref={'path':'preparation/episode.json','sha256':'prepared'}
    failed={'completed':False,'finished_at':3,'failure':'RuntimeError: UI observation did not become decodable',
        'phase':'owned_class_entry_started','actor':fixture,'runtime':runtime,'fixture_source':ref}
    events=[{'event':'native_stream_closed','session':'owned'}]
    return failed,ref,fixture,runtime,events


def test_closed_no_login_failure_can_replace_only_the_owned_offline_scout():no_login(*data())


@pytest.mark.parametrize('fault',['open','successful','other_failure','other_phase','other_actor','other_runtime',
    'other_preparation','login_sent','native_created','no_disconnect'])
def test_unknown_or_already_entered_trial_is_refused(fault):
    failed,ref,fixture,runtime,events=deepcopy(data())
    if fault=='open':failed['finished_at']=None
    elif fault=='successful':failed['completed']=True
    elif fault=='other_failure':failed['failure']='unknown'
    elif fault=='other_phase':failed['phase']='owned_class_entered'
    elif fault=='other_actor':failed['actor']={'guid':1}
    elif fault=='other_runtime':failed['runtime']={'worldserver':{'pid':99}}
    elif fault=='other_preparation':failed['fixture_source']={}
    elif fault=='login_sent':events.append({'name':'CMSG_PLAYER_LOGIN'})
    elif fault=='native_created':events.append({'event':'native_player_created','guid':6})
    else:events=[]
    with pytest.raises(RuntimeError):no_login(failed,ref,fixture,runtime,events)
