"""Pending logout is not a completed calibration or a qualified quest link."""
import copy
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_quest_reentry as staged,interaction_quest_link as links


def prepared():
    return {'completed':True,'failure':None,'finished_at':100,'phase':'await_primary_character_selection_review',
        'quest_trial_kind':'layout','actor':{'guid':1},'runtime':{'client':1},'original_quest_log':{'selection':0},
        'quest_prelogout_checks':{k:True for k in staged.LAYOUT-{'selection'}|{'only_selection_differs','settings_preserved'}},
        'bridge_native_restoration':{'checks':{k:True for k in staged.NATIVE-{'group'}}},
        'logout_checks':{k:True for k in ['ordinary_request','native_complete','native_enumeration']}}


def test_closed_preparation_only_authorizes_reviewed_cleanup():
    old=prepared();assert staged.prepared_matches(old,old)


@pytest.mark.parametrize('change',['open','failed','wrong_phase','wrong_kind','foreign_actor','foreign_runtime',
    'wrong_selection','missing_check','false_check','missing_logout','false_logout','missing_native','failed_native'])
def test_incomplete_or_foreign_preparation_refuses_reentry(change):
    old=prepared();current=copy.deepcopy(old)
    if change=='open':old['finished_at']=None
    elif change=='failed':old['completed']=False
    elif change=='wrong_phase':old['phase']='in_world'
    elif change=='wrong_kind':old['quest_trial_kind']='another_operation'
    elif change=='foreign_actor':current['actor']={'guid':2}
    elif change=='foreign_runtime':current['runtime']={'client':2}
    elif change=='wrong_selection':old['original_quest_log']['selection']=2
    elif change=='missing_check':old['quest_prelogout_checks'].pop('settings_preserved')
    elif change=='false_check':old['quest_prelogout_checks']['native_quests']=False
    elif change=='missing_logout':old['logout_checks'].pop('native_complete')
    elif change=='false_logout':old['logout_checks']['native_enumeration']=False
    elif change=='missing_native':old['bridge_native_restoration']['checks'].pop('pose')
    else:old['bridge_native_restoration']['checks']['afk']=False
    assert not staged.prepared_matches(old,current)


def link():
    text='|cff40c040|Hquest:28825:80|h[A Personal Summons]|h|r'
    action=['ordinary_shift_click','blank_before','chat_still_open','requested_link','rendered_label_markup',
        'no_item_cursor','clean','no_spell_cast_request','no_owned_native_cast_completion']
    return {'quest_link_pending_checks':{'checks':{k:True for k in
        ['exact_public_link','pending_chat','watch_count','same_owned_quest','native_quests','no_message_request']}},
        'quest_no_message_request':True,'original_quest_log':{'fixture':{'link':text}},
        'cases':[{'id':'ui_misc.quest_link','status':'stock_chat_link_pass','selected':'link','input':{'modifiers':['shift']},
            'oracle':{'kind':'quest','id':28825,'message_submitted':False,'pending_text':text,
                'checks':{k:True for k in action}}}]}


def test_exact_pending_stock_link_and_no_submission_evidence_pass():
    assert staged.link_evidence_matches(link())


@pytest.mark.parametrize('change',['submitted','missing_pending','pending_failed','missing_action','action_failed',
    'duplicate_case','case_failed','wrong_modifier','other_quest','wrong_text','submission_unknown'])
def test_cleanup_cannot_qualify_missing_or_failed_link_evidence(change):
    old=link();case=old['cases'][0];oracle=case['oracle']
    if change=='submitted':old['quest_no_message_request']=False
    elif change=='missing_pending':old['quest_link_pending_checks']['checks'].pop('pending_chat')
    elif change=='pending_failed':old['quest_link_pending_checks']['checks']['watch_count']=False
    elif change=='missing_action':oracle['checks'].pop('no_spell_cast_request')
    elif change=='action_failed':oracle['checks']['no_item_cursor']=False
    elif change=='duplicate_case':old['cases'].append(copy.deepcopy(case))
    elif change=='case_failed':case['status']='client_or_protocol_failure'
    elif change=='wrong_modifier':case['input']['modifiers']=[]
    elif change=='other_quest':oracle['id']=28766
    elif change=='wrong_text':oracle['pending_text']='[A Personal Summons]'
    else:oracle['message_submitted']=None
    assert not staged.link_evidence_matches(old)


def test_cold_zero_fixture_without_staged_reentry_refuses_before_any_log_input(monkeypatch):
    from tools.client_compatibility.world.tests.test_quest_link import baseline
    original=baseline();original['selection']=0
    t=SimpleNamespace(receipt={},fixture={'guid':1},persist=lambda:None)
    monkeypatch.setattr(links,'detail',lambda *args:({'observer_version':121},original))
    monkeypatch.setattr(links,'open_log',lambda *args:pytest.fail('quest log opened before a restoration path'))
    with pytest.raises(RuntimeError,match='staged ordinary-reentry adapter'):
        links.suite(t,calibrate=True)
