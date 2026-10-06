"""Owned friend transitions and pending stock whispers bind to exact identities."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_friend_presence import wire_checks,source_matches,original_position,public_presence_matches,cache_reset_required,HIGH
from tools.client_compatibility.interaction_friend_whisper import pending,owned_online_row,settling_pending,await_pending
from tools.client_compatibility.world.buffer import Writer


def trace(connected=True,guid=2,realm=1,level=1,area=12):
    result=2 if connected else 3
    native=struct.pack('<BQ',result,guid)+(struct.pack('<BIII',1,area,level,1) if connected else b'')
    modern=Writer().pack('B',result).guid(guid,HIGH).guid().pack('IBIII',realm,int(connected),
        area if connected else 0,level if connected else 0,1 if connected else 0).bits(0,10).finish()
    return [{'name':'SMSG_FRIEND_STATUS','direction':d,'body':b.hex()} for d,b in
        [('from_native',native),('to_client',modern)]]


@pytest.mark.parametrize('connected',[False,True])
def test_exact_owned_online_and_offline_presence(connected):
    assert all(wire_checks(trace(connected),connected).values())


@pytest.mark.parametrize('change',['guid','realm','level','area','missing_native','missing_modern','duplicate','trailing'])
def test_other_or_unattributable_presence_is_rejected(change):
    rows=trace()
    if change=='guid':rows=trace(guid=3)
    elif change=='realm':rows=trace(realm=2)
    elif change=='level':rows=trace(level=85)
    elif change=='area':rows=trace(area=3)
    elif change=='missing_native':rows.pop(0)
    elif change=='missing_modern':rows.pop(1)
    elif change=='duplicate':rows.append(rows[0])
    else:
        rows[1]['body']+='00'
        with pytest.raises(ValueError):wire_checks(rows,True)
        return
    assert not all(wire_checks(rows,True).values())


def preflight():
    return {'completed':True,'failure':None,'finished_at':100,'actor':{'guid':2},
        'runtime':{'client':{'pid':12,'start_ticks':'34'}},'parked_native':{'online':0,'name':'Harnesstwo','level':1},
        'qualified_scope':'Read-only owned offline scout preflight; no input or gameplay qualification.'}


def test_closed_owned_parked_preflight_is_admissible():
    old=preflight();assert source_matches(old,old)


@pytest.mark.parametrize('change',['failed','open','actor','runtime','online','name','level','other_scope'])
def test_other_or_live_preflight_cannot_authorize_entry(change):
    old=preflight();current=copy.deepcopy(old)
    if change=='failed':old['failure']='another failure'
    elif change=='open':old['finished_at']=None
    elif change=='actor':current['actor']['guid']=3
    elif change=='runtime':current['runtime']['client']['start_ticks']='35'
    elif change=='online':old['parked_native']['online']=1
    elif change=='name':old['parked_native']['name']='Harnessdwarf'
    elif change=='level':old['parked_native']['level']=85
    else:old['qualified_scope']='another setup'
    assert not source_matches(old,current)


@pytest.mark.parametrize('target',['Harnesstwo','Harnesstwo-Client442Lab'])
def test_stock_pending_whisper_accepts_only_owned_same_realm_name(target):
    assert pending({'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'WHISPER',
        'chat_edit_target':target,'chat_edit_text':'owned marker'},'owned marker')


@pytest.mark.parametrize('change',[{'chat_edit_open':False},{'chat_edit_focused':False},
    {'chat_edit_type':'SAY'},{'chat_edit_target':'Anotherplayer'},
    {'chat_edit_target':'Harnesstwo-Anotherrealm'},{'chat_edit_text':'owned marker extra'}])
def test_changed_pending_whisper_is_refused(change):
    state={'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'WHISPER',
        'chat_edit_target':'Harnesstwo','chat_edit_text':'owned marker'};state.update(change)
    assert not pending(state,'owned marker')


def test_stale_prefix_can_settle_without_retyping_or_sending():
    states=[{'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'WHISPER',
        'chat_edit_target':'Harnesstwo','chat_edit_text':text} for text in ['TC442UI:friend_1487b6','TC442UI:friend_1487b663']]
    class ReadOnly:
        receipt={}
        def observe(self,*args,**kwargs):return states.pop(0),{'file':'sample.png'}
        def persist(self):pass
    t=ReadOnly();state,frame=await_pending(t,'TC442UI:friend_1487b663')
    assert pending(state,'TC442UI:friend_1487b663')
    assert len(t.receipt['friend_whisper_settling'])==2
    assert all(s['input_replayed'] is False for s in t.receipt['friend_whisper_settling'])


@pytest.mark.parametrize('change',[{'chat_edit_text':'unrelated'},{'chat_edit_target':'Anotherplayer'},
    {'chat_edit_target':'Harnesstwo-Anotherrealm'},{'chat_edit_type':'SAY'},
    {'chat_edit_focused':False},{'chat_edit_open':False},{'chat_edit_text':None}])
def test_changed_editor_cannot_be_treated_as_pending_prefix(change):
    state={'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'WHISPER',
        'chat_edit_target':'Harnesstwo','chat_edit_text':'TC442UI:friend_1487b6'};state.update(change)
    assert not settling_pending(state,'TC442UI:friend_1487b663')


def test_pending_prefix_timeout_does_not_accept_or_send(monkeypatch):
    from tools.client_compatibility import interaction_friend_whisper as whisper
    ticks=iter([0,11]);monkeypatch.setattr(whisper.time,'monotonic',lambda:next(ticks))
    state={'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_type':'WHISPER',
        'chat_edit_target':'Harnesstwo','chat_edit_text':'TC442UI:friend_1487b6'}
    class ReadOnly:
        receipt={}
        def observe(self,*args,**kwargs):return state,{'file':'sample.png'}
        def persist(self):pass
    t=ReadOnly();observed,frame=await_pending(t,'TC442UI:friend_1487b663')
    assert not pending(observed,'TC442UI:friend_1487b663')
    assert len(t.receipt['friend_whisper_settling'])==1
    assert t.receipt['friend_whisper_settling'][0]['input_replayed'] is False


def test_original_database_position_uses_its_actual_list_shape():
    row={'position_x':-8914.86,'position_y':-135.609,'position_z':80.4425,'orientation':5.83261,'map':0}
    assert original_position([-8914.86,-135.609,80.4425,5.83261,0],row)
    assert not original_position([-8913.86,-135.609,80.4425,5.83261,0],row)
    assert not original_position([-8914.86,-135.609,80.4425,5.83261,1],row)


def test_actual_online_control_label_includes_level_and_class():
    c={'kind':'Button','name':'FriendsFrameFriendsScrollFrameButton1','text':'Harnesstwo, Level 1 Warrior'}
    assert owned_online_row(c)
    for text in ['Harnesstwo','Harnesstwo, Level 85 Warrior','Anotherplayer, Level 1 Warrior',
            'Harnesstwo, Level 1 Mage','Harnesstwo-Anotherrealm, Level 1 Warrior']:
        assert not owned_online_row({**c,'text':text})


@pytest.mark.parametrize('connected',[False,True])
def test_post_online_public_cache_retains_the_verified_level_when_offline(connected):
    row={'name':'Harnesstwo','connected':connected,'level':1,'notes':''}
    assert public_presence_matches([row],connected)
    assert not public_presence_matches([{**row,'level':0}],connected)
    assert not public_presence_matches([{**row,'notes':'changed'}],connected)


def cache_pending():
    from tools.client_compatibility.world.tests.test_friend_cache_recovery import fixture
    old=fixture(True);old['cases']=[{'id':id,'status':status} for id,status in [
        ('friends.online_presence','owned_friend_presence_pass'),('friends.whisper','owned_friend_whisper_pass'),
        ('fixture.friend_offline_transition','owned_friend_presence_pass')]]
    return old


def test_only_cache_difference_after_all_feature_cases_routes_to_required_reset():
    assert cache_reset_required(cache_pending())


@pytest.mark.parametrize('change',['failed_whisper','missing_offline','other_native','other_friend','different_original','already_reset'])
def test_partial_or_other_restoration_failures_cannot_route_as_cache_only(change):
    old=cache_pending()
    if change=='failed_whisper':old['cases'][1]['status']='client_or_protocol_failure'
    elif change=='missing_offline':old['cases'].pop()
    elif change=='other_native':old['bridge_native_restoration']['checks']['stats']=False
    elif change=='other_friend':old['friend_restoration']['checks']['inventory_money']=False
    elif change=='different_original':old['original_public_friends'][0]['level']=1
    else:old['friend_restoration']['checks']['public_friends']=True
    assert not cache_reset_required(old)
