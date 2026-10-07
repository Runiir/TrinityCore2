"""A repeated candidate deployment retains its original primary and archived authority."""
from copy import deepcopy
import pytest
from tools.client_compatibility import lab_runtime as lab
from tools.client_compatibility.stopped_native_ancestry import prior_transition,primary_native,passed_tests,SCHEMA


def data():
    root={'pid':1};current={'pid':4};bridge={'pid':2};client={'pid':5}
    ref={'path':str(lab.ROOT/'evidence/old/native_tame_deploy01/deployment.json'),'sha256':'deployment'}
    d={'schema':SCHEMA,'completed':True,'installed':True,'failure':None,'finished_at':7,
        'installation_checks':dict.fromkeys(range(9),True),'native_restarted':True,'bridge_unchanged':True,
        'native_before':root,'native':current,'before':bridge,'after':bridge,'scout_lifetime':client,
        'primary_stop_source':{'sha256':'primary'},'binary_sha256':'candidate1'}
    base={str(i):{'native':{'online':0}} for i in range(1,7)}
    p={'runtime':{'worldserver':current,'modern_world':bridge,'client':client},'primary_stop_source':d['primary_stop_source'],
        'completed':True,'phase':'parked_scout_resource_paused','before':base,'after':base,
        'checks':dict.fromkeys(range(8),True),'started_at':8,'finished_at':9}
    cp={'file':'artifact','sha256':'archive','bytes':10,'cloud_verified':True,'file_manifest':[
        {'path':str(lab.ROOT/'evidence/old/native_tame_deploy01/deployment.json').removeprefix(str(lab.ROOT)+'/'),
            'sha256':'deployment'}, {'path':'bin/worldserver','sha256':'candidate1'}]}
    review={'actual_remote_verified':True,'complete_json_png_verified':True,'archive_sha256':'archive',
        'bytes':10,'pointer':'artifact.dvc'}
    return deepcopy((d,p,review,cp,ref))


def test_repeated_native_candidate_is_bound_to_actual_previous_archive():
    assert prior_transition(*data())=={'pid':1}


@pytest.mark.parametrize('fault',['failed','unfinished','uninstalled','partial_checks','not_restarted','changed_bridge',
    'wrong_native','wrong_bridge','wrong_scout','wrong_primary','pause_order','pause_failed','pause_partial',
    'pause_changed','remote_unread','members_unverified','wrong_archive','wrong_size','wrong_pointer',
    'cloud_unverified','changed_deployment','missing_binary','foreign_binary'])
def test_unbound_predecessor_is_refused(fault):
    d,p,r,c,ref=data()
    if fault=='failed':d['failure']='failed'
    elif fault=='unfinished':d['finished_at']=None
    elif fault=='uninstalled':d['installed']=False
    elif fault=='partial_checks':d['installation_checks'][0]=False
    elif fault=='not_restarted':d['native_restarted']=False
    elif fault=='changed_bridge':d['bridge_unchanged']=False
    elif fault=='wrong_native':d['native']={'pid':99}
    elif fault=='wrong_bridge':d['after']={'pid':99}
    elif fault=='wrong_scout':d['scout_lifetime']={'pid':99}
    elif fault=='wrong_primary':d['primary_stop_source']={}
    elif fault=='pause_order':p['started_at']=6
    elif fault=='pause_failed':p['completed']=False
    elif fault=='pause_partial':p['checks'][0]=False
    elif fault=='pause_changed':p['after']={}
    elif fault=='remote_unread':r['actual_remote_verified']=False
    elif fault=='members_unverified':r['complete_json_png_verified']=False
    elif fault=='wrong_archive':r['archive_sha256']='other'
    elif fault=='wrong_size':r['bytes']=11
    elif fault=='wrong_pointer':r['pointer']='other'
    elif fault=='cloud_unverified':c['cloud_verified']=False
    elif fault=='changed_deployment':c['file_manifest'][0]['sha256']='other'
    elif fault=='missing_binary':c['file_manifest'].pop()
    else:c['file_manifest'][1]['sha256']='other'
    with pytest.raises(RuntimeError):prior_transition(d,p,r,c,ref)


def test_original_primary_native_cannot_change_without_a_predecessor():
    with pytest.raises(RuntimeError):primary_native({'native_before':{'pid':1},'primary_native':{'pid':99}})


def test_second_replacement_keeps_original_primary_native():
    d,p,r,c,ref=data();d.update(native_before={'pid':3},primary_native={'pid':1},previous_native_deployment={})
    d['previous_native_deployment']={'sha256':'older'}
    assert prior_transition(d,p,r,c,ref)=={'pid':1}


@pytest.mark.parametrize('text',['101 passed in 1s\n','103 passed in 1s\n','4339 passed in 53.91s\n'])
def test_complete_candidate_test_logs_are_supported(text):
    assert passed_tests(text)>=101


@pytest.mark.parametrize('text',['100 passed in 1s\n','103 passed, 1 failed in 1s\n','103 passed, 1 skipped in 1s\n',
    '103 passed in 1s\n1 error\n','103 passed in 1s\n103 passed in 1s\n','unfinished'])
def test_partial_failed_or_ambiguous_test_logs_are_refused(text):
    with pytest.raises(RuntimeError):passed_tests(text)
