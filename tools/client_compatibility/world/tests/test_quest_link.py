"""Only the existing owned quest and exact stock-generated pending link qualify."""
import copy
import pytest
from tools.client_compatibility import interaction_quest_link as links

LINK='|cffffff00|Hquest:28825:80|h[A Personal Summons]|h|r'


def baseline():
    return {'visible':False,'count':1,'total_quests':1,'selection':1,'watched_count':0,
        'rows':[{'index':1,'title':'Stormwind City','header':True,'collapsed':True}],
        'fixture':{'id':28825,'active':True,'link':LINK}}


def test_exact_existing_collapsed_fixture_and_pending_chat():
    assert links.fixture(baseline())==LINK
    assert links.pending_matches({'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_text':LINK},LINK,28825)


@pytest.mark.parametrize('change',['other_quest','level','title','multiple_quests','count_bool','unrestorable_selection',
    'already_open','expanded','other_zone','not_active','watch_unknown','missing_rows'])
def test_non_owned_or_unrestorable_fixture_refuses_before_log_input(change):
    old=baseline()
    if change=='other_quest':old['fixture']['id']=28766
    elif change=='level':old['fixture']['link']=LINK.replace(':80|',':85|')
    elif change=='title':old['fixture']['link']=LINK.replace('A Personal Summons','Another quest')
    elif change=='multiple_quests':old['total_quests']=2
    elif change=='count_bool':old['count']=True
    elif change=='unrestorable_selection':old['selection']=2
    elif change=='already_open':old['visible']=True
    elif change=='expanded':old['rows'][0]['collapsed']=False
    elif change=='other_zone':old['rows'][0]['title']='Elwynn Forest'
    elif change=='not_active':old['fixture']['active']=False
    elif change=='watch_unknown':old.pop('watched_count')
    else:old['rows']={}
    with pytest.raises(RuntimeError):links.fixture(old)


@pytest.mark.parametrize('change',['closed','unfocused','different_text','other_id','lua_error','blocked'])
def test_pending_link_does_not_accept_missing_focus_or_a_different_result(change):
    state={'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_text':LINK};id=28825
    if change=='closed':state['chat_edit_open']=False
    elif change=='unfocused':state['chat_edit_focused']=False
    elif change=='different_text':state['chat_edit_text']='[A Personal Summons]'
    elif change=='other_id':id=28766
    elif change=='lua_error':state['lua_errors']=['error']
    else:state['blocked_actions']=['blocked']
    assert not links.pending_matches(state,LINK,id)


def test_submission_check_is_owned_session_and_window_specific(monkeypatch):
    packets=[{'name':'CMSG_CHAT_MESSAGE_SAY','time':10,'session':'own','direction':'from_client'},
        {'name':'CMSG_CHAT_MESSAGE_SAY','time':9,'session':'own','direction':'from_client'},
        {'name':'CMSG_CHAT_MESSAGE_SAY','time':11,'session':'other','direction':'from_client'},
        {'name':'SMSG_CHAT','time':11,'session':'own','direction':'to_client'},
        {'name':'CMSG_CAST_SPELL','time':11,'session':'own','direction':'from_client'}]
    monkeypatch.setattr(links,'entries',lambda path:packets)
    assert links.message_requests('own',10)==[{'name':'CMSG_CHAT_MESSAGE_SAY','time':10}]


def test_original_zero_selection_requires_calibration_rather_than_fabricating_header_selection():
    old=baseline();old['selection']=0;assert links.fixture(old)==LINK


@pytest.mark.parametrize('change',['valid','open','failed','link_run','other_actor','other_runtime','different_layout',
    'different_native','partial_checks','false_check','native_failure','baseline_change'])
def test_only_complete_source_bound_layout_calibration_can_authorize_link(tmp_path,monkeypatch,change):
    import json
    from types import SimpleNamespace
    original=baseline();native={'active':[{'quest':28825,'status':1}],'rewarded':[]}
    current={'runtime':{'world':1},'native_baseline':{'pose':1}}
    t=SimpleNamespace(fixture={'guid':1},receipt=current,persist=lambda:None)
    checks={k:True for k in ['visible','count','total_quests','selection','rows','watched_count','fixture',
        'native_quests','chat_closed','ui_clean']}
    old={'completed':True,'failure':None,'finished_at':100,'quest_link_layout_calibration':True,
        'actor':t.fixture,'runtime':current['runtime'],'native_baseline':current['native_baseline'],
        'quest_link_original':original,'quest_link_native_original':native,
        'quest_link_restoration':{'checks':checks},'native_restoration':{'checks':{k:True for k in
            ['resources','stats','spells','actions','pose','afk','position','group','no_lua_errors','no_blocked_actions']}}}
    old=copy.deepcopy(old)
    if change=='open':old['finished_at']=None
    elif change=='failed':old['completed']=False
    elif change=='link_run':old['quest_link_layout_calibration']=False
    elif change=='other_actor':old['actor']={'guid':2}
    elif change=='other_runtime':old['runtime']={'world':2}
    elif change=='different_layout':old['quest_link_original']['selection']=0
    elif change=='different_native':old['quest_link_native_original']['active'][0]['status']=3
    elif change=='partial_checks':old['quest_link_restoration']['checks'].pop('selection')
    elif change=='false_check':old['quest_link_restoration']['checks']['selection']=False
    elif change=='native_failure':old['native_restoration']['checks']['pose']=False
    elif change=='baseline_change':old['native_baseline']['pose']=0
    monkeypatch.setattr(links.lab,'ROOT',tmp_path);folder=tmp_path/'evidence/calibration';folder.mkdir(parents=True)
    path=folder/'episode.json';path.write_text(json.dumps(old))
    if change=='valid':
        links.layout_source(t,path,original,native);assert len(current['quest_link_layout_source']['sha256'])==64
    else:
        with pytest.raises(RuntimeError):links.layout_source(t,path,original,native)
