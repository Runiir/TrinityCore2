"""Stage a stock quest trial around separately reviewed ordinary reentry."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab,actors
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial
from . import interaction_quest_link as links
from .interaction_quest_selection_recovery import enter,LAYOUT,NATIVE
from .interaction_bridge_restoration import capture,restore
from .interaction_settings_booleans import detail as settings_detail
from .interaction_owned_language_fixture import logout
from .interaction_lifecycle import Packets
from .interaction_bridge_deploy import shot


class AwaitSelectionReview(Exception):
    """The ordinary logout phase closed; no world-entry input may follow yet."""


def prepared_matches(old,current):
    checks=old.get('quest_prelogout_checks',{})
    expected=LAYOUT-{'selection'}|{'only_selection_differs','settings_preserved'}
    native=old.get('bridge_native_restoration',{}).get('checks',{})
    return (old.get('completed') is True and old.get('failure') is None and old.get('finished_at') and
        old.get('phase')=='await_primary_character_selection_review' and
        old.get('quest_trial_kind') in ('layout','link') and old.get('actor')==current.get('actor') and
        old.get('runtime')==current.get('runtime') and old.get('original_quest_log',{}).get('selection')==0 and
        set(checks)==expected and all(v is True for v in checks.values()) and
        set(native)==NATIVE-{'group'} and all(v is True for v in native.values()) and
        set(old.get('logout_checks',{}))=={'ordinary_request','native_complete','native_enumeration'} and
        all(v is True for v in old['logout_checks'].values()))


def link_evidence_matches(old):
    pending=old.get('quest_link_pending_checks',{}).get('checks',{})
    expected={'exact_public_link','pending_chat','watch_count','same_owned_quest','native_quests','no_message_request'}
    cases=[c for c in old.get('cases',[]) if c.get('id')=='ui_misc.quest_link']
    if len(cases)!=1:return False
    case=cases[0];oracle=case.get('oracle',{});checks=oracle.get('checks',{})
    expected_action={'ordinary_shift_click','blank_before','chat_still_open','requested_link','rendered_label_markup',
        'no_item_cursor','clean','no_spell_cast_request','no_owned_native_cast_completion'}
    return (set(pending)==expected and all(v is True for v in pending.values()) and
        old.get('quest_no_message_request') is True and case.get('status')=='stock_chat_link_pass' and
        case.get('selected')=='link' and case.get('input',{}).get('modifiers')==['shift'] and
        oracle.get('kind')=='quest' and oracle.get('id')==links.QUEST and oracle.get('message_submitted') is False and
        oracle.get('pending_text')==old.get('original_quest_log',{}).get('fixture',{}).get('link') and
        set(checks)==expected_action and all(v is True for v in checks.values()))


def pause(t,original,native,state,current):
    checks={k:current.get(k)==original.get(k) for k in
        ['visible','count','total_quests','rows','watched_count','fixture']}
    checks.update(native_quests=links.saved(1)==native,chat_closed=not state.get('chat_edit_open'),
        ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'),
        only_selection_differs=original['selection']==0 and current.get('selection')==2)
    window=t.receipt.get('quest_link_submission_window')
    if window:
        window['until']=time.time()
        t.receipt['quest_no_message_request']=not links.message_requests(window['session'],window['since'],window['until'])
        if not t.receipt['quest_no_message_request']:raise RuntimeError('quest-link trial submitted a chat message')
    restore(t,t.receipt['native_baseline'])
    settings=settings_detail(t,'quest_prelogout_settings')
    checks['settings_preserved']=all(settings.get(k)==t.receipt['original_settings'].get(k) for k in
        ['cvars','values','category','search','unapplied'])
    t.receipt.update(quest_prelogout_checks=checks,original_quest_log=original,original_native=t.receipt['native_baseline'],
        original_native_quests=native,original_group=t.receipt['quest_original_group']);t.persist()
    if not all(checks.values()):raise RuntimeError('quest trial differs beyond the original selection0 fixture')
    session=actors.session_entry(t.fixture)['session'];packets=Packets(session);started=time.time();logout(t)
    deadline=time.monotonic()+12
    while not packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','from_native'):
        if time.monotonic()>deadline:raise RuntimeError('staged quest logout lacks native enumeration')
        time.sleep(.2)
    checks={'ordinary_request':packets.has(started,'CMSG_LOGOUT_REQUEST','from_client'),
        'native_complete':packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native'),'native_enumeration':True}
    t.receipt.update(logout_checks=checks,previous_session=session,phase='await_primary_character_selection_review',
        selection_frame=shot(t.out/'primary_selection.png'),qualified_scope=
        'Preparation phase only: stock quest controls and one ordinary logout. Requires fresh owned selection review and complete same-character reentry before any calibration or quest-link qualification.');t.persist()
    if not all(checks.values()):raise RuntimeError('staged quest logout wire checks differ')
    raise AwaitSelectionReview()


def begin(t,kind,layout_source):
    t.clean_panels();state,original=links.detail(t,'quest_staged_cold_original')
    links.fixture(original)
    if t.fixture['guid']!=1 or original['selection']!=0:raise RuntimeError('requires the exact owned cold selection0 fixture')
    t.receipt.update(native_baseline=json.loads(json.dumps(capture(t))),original_settings=settings_detail(t,'quest_staged_settings'),
        quest_original_group=state['group'],quest_trial_kind=kind,custom_script_permission='blocked_by_user');t.persist()
    links.suite(t,calibrate=kind=='layout',source=layout_source,selection_restore=pause)
    raise RuntimeError('staged quest trial did not reach reviewed reentry boundary')


def finish(t,path,review):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires the owned closed quest preparation')
    old=json.loads(path.read_text())
    if not prepared_matches(old,t.receipt):raise RuntimeError('closed quest preparation or owned lifetime differs')
    enter(t,path,review)
    state,current=links.detail(t,'quest_staged_final_hidden')
    checks={k:current.get(k)==old['original_quest_log'].get(k) for k in
        ['visible','count','total_quests','selection','rows','watched_count','fixture']}
    checks.update(native_quests=links.saved(1)==old['original_native_quests'],chat_closed=not state.get('chat_edit_open'),
        ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'))
    native=dict(t.receipt['bridge_native_restoration']['checks']);native['group']=state['group']==old['original_group']
    t.receipt.update(quest_prepared_source={'file':str(path),'sha256':lab.sha256(path)},quest_trial_kind=old['quest_trial_kind'],
        quest_link_layout_calibration=old['quest_trial_kind']=='layout',native_baseline=old['original_native'],
        quest_link_original=old['original_quest_log'],quest_link_native_original=old['original_native_quests'],
        quest_link_restoration={'checks':checks},native_restoration={'checks':native},
        qualified_scope=('Calibration only: stock quest-log layout roundtrip with original selection0 and native/settings restoration through verified ordinary same-character reentry.'
            if old['quest_trial_kind']=='layout' else
            'Owned existing quest28825 stock Shift-left-click inserted its exact public link into blank chat. Escape cancelled without submission. Original quest/header/watch/selection0 and native/settings fixture restored through separately reviewed ordinary same-character reentry. Other quests and delivery remain open.'));t.persist()
    if old.get('quest_link_execution_failure'):
        t.receipt['quest_link_execution_failure']=old['quest_link_execution_failure'];t.persist()
        raise RuntimeError('quest operation failed before completed cleanup: '+old['quest_link_execution_failure'])
    if set(native)!=NATIVE or not all(native.values()) or set(checks)!=LAYOUT or not all(checks.values()):
        raise RuntimeError('staged quest layout or native fixture did not fully restore')
    if old['quest_trial_kind']=='link':
        t.receipt.update(quest_link_pending_checks=old.get('quest_link_pending_checks'),
            quest_no_message_request=old.get('quest_no_message_request'));t.persist()
        if not link_evidence_matches(old):
            raise RuntimeError('staged quest-link insertion lacks exact completed pending/no-submission evidence')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=['begin','finish'],required=True)
    p.add_argument('--kind',choices=['layout','link']);p.add_argument('--layout-source',type=Path)
    p.add_argument('--source',type=Path);p.add_argument('--review',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.phase=='begin' and (not a.kind or a.source or a.review or (a.kind=='link')!=bool(a.layout_source)):
        p.error('begin requires its kind and only link requires a passed layout source')
    if a.phase=='finish' and (not a.source or not a.review or a.kind or a.layout_source):
        p.error('finish requires only its closed preparation source and fresh selection review')
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:
            (begin(t,a.kind,a.layout_source) if a.phase=='begin' else finish(t,a.source,a.review))
            t.receipt['completed']=True
        except AwaitSelectionReview:t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase')}),flush=True)


if __name__=='__main__':main()
