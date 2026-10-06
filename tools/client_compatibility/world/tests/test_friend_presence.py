"""Owned friend transitions and pending stock whispers bind to exact identities."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_friend_presence import wire_checks,source_matches,original_position,HIGH
from tools.client_compatibility.interaction_friend_whisper import pending
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


def test_original_database_position_uses_its_actual_list_shape():
    row={'position_x':-8914.86,'position_y':-135.609,'position_z':80.4425,'orientation':5.83261,'map':0}
    assert original_position([-8914.86,-135.609,80.4425,5.83261,0],row)
    assert not original_position([-8913.86,-135.609,80.4425,5.83261,0],row)
    assert not original_position([-8914.86,-135.609,80.4425,5.83261,1],row)
