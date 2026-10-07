"""Successful captures cannot substitute changed, foreign or incomplete sources."""
from copy import deepcopy
import pytest
from tools.client_compatibility.owned_reentry_boundary import captured


def data():
    runtime={'client':3,'worldserver':1,'modern_world':2};origin={'guid':2};hunter={'guid':6}
    refs={k:{'path':k,'sha256':k} for k in ('preparation','stage','previous','park','primary')}
    def row(count,actor,start,end):
        return {'completed':True,'failure':None,'started_at':start,'finished_at':end,
            'runtime':runtime,'actor':actor,'fixture_source':refs['preparation'],'model':None,
            'custom_script_permission':'blocked_by_user','checks':dict.fromkeys(range(count),True)}
    previous=row(9,hunter,1,2);previous['native_session']='owned'
    park=row(4,hunter,3,4);park.update(phase='await_original_selection_review',
        retained_class_fixture={'online':0},retained_class_saved={},retained_class_pets=[])
    stage=row(14,origin,5,6);stage.update(phase='await_owned_reentry_review',
        sources=[refs[k] for k in ('preparation','previous','park','primary')],
        primary_stop_source=refs['primary'],all_offline_snapshot={str(i):{
            'native':{'online':0},'saved':{},'pets':[],'inventory':[]} for i in range(1,7)})
    entry=row(9,hunter,7,12);entry.update(phase='owned_class_entered',source=refs['stage'],
        capture_disarmed=True,input_sent=True,qualification_added=False,native_session='owned',
        ordinary_input={'kind':'reviewed_lobby_click','point':[640,660]},capture_config={
            'schema':'client442_owned_entry_request_probe_v1','owner':6,'account_id':2,
            'runtime':runtime,'session':'owned','created_at':8,'expires_at':128,
            'entry_source':{'sha256':'previous'}},capture_packets=[{
                'session':'owned','direction':'from_client','name':'CMSG_GET_ACCOUNT_CHARACTER_LIST',
                'time':9,'body':'0000000000'}],native_login_requests=[{
                'session':'owned','direction':'to_native','name':'CMSG_PLAYER_LOGIN','time':10}])
    return deepcopy((entry,stage,previous,park,runtime,origin,hunter,refs))


def test_complete_captured_reentry_is_eligible():captured(*data())


@pytest.mark.parametrize('fault',['failed','unfinished','runtime','actor','preparation','model','script',
    'checks','stage_source','previous_source','armed','input','qualification','click','session','lease',
    'order','online','saved','pet','native_login','foreign_login','secret','width','packet_time'])
def test_foreign_changed_or_incomplete_sources_are_rejected(fault):
    e,s,p,park,r,o,h,refs=data()
    if fault=='failed':e['failure']='failure'
    elif fault=='unfinished':e['finished_at']=None
    elif fault=='runtime':s['runtime']={}
    elif fault=='actor':e['actor']=o
    elif fault=='preparation':e['fixture_source']={}
    elif fault=='model':e['model']='retired'
    elif fault=='script':s['custom_script_permission']='enabled'
    elif fault=='checks':e['checks'][0]=False
    elif fault=='stage_source':e['source']={}
    elif fault=='previous_source':s['sources'][1]={}
    elif fault=='armed':e['capture_disarmed']=False
    elif fault=='input':e['input_sent']=False
    elif fault=='qualification':e['qualification_added']=True
    elif fault=='click':e['ordinary_input']['point']=[1,1]
    elif fault=='session':e['capture_config']['session']='foreign'
    elif fault=='lease':e['capture_config']['expires_at']=129
    elif fault=='order':park['started_at']=0
    elif fault=='online':s['all_offline_snapshot']['1']['native']['online']=1
    elif fault=='saved':s['all_offline_snapshot']['6']['saved']={'changed':True}
    elif fault=='pet':s['all_offline_snapshot']['6']['pets']=[4]
    elif fault=='native_login':e['native_login_requests']=[]
    elif fault=='foreign_login':e['native_login_requests'][0]['session']='foreign'
    elif fault=='secret':e['capture_packets'][0]['name']='CMSG_AUTH_SESSION'
    elif fault=='width':e['capture_packets'][0]['body']='00'
    else:e['capture_packets'][0]['time']=129
    with pytest.raises(RuntimeError):captured(e,s,p,park,r,o,h,refs)
