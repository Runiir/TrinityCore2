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
    elif change=='unrestorable_selection':old['selection']=0
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
