"""Insert the existing owned quest's stock link and cancel it without submission."""
import argparse,json,re,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial
from .interaction_trial import binding_key
from .interaction_control_target import target,click
from .interaction_macros import require
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_links import insert
from .interaction_observation import read_current_page
from .observation.journal import entries
from . import actors

QUEST=28825
TITLE='A Personal Summons'


def saved(guid):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT * FROM client442_characters.character_queststatus WHERE guid=%s ORDER BY quest',(guid,))
        active=[dict(zip([x[0] for x in q.description],r)) for r in q.fetchall()]
        q.execute('SELECT * FROM client442_characters.character_queststatus_rewarded WHERE guid=%s ORDER BY quest',(guid,))
        rewarded=[dict(zip([x[0] for x in q.description],r)) for r in q.fetchall()]
    return {'active':active,'rewarded':rewarded}


def detail(t,label,ready=None):
    state,frame=read_current_page(t,label,'state',lambda s:isinstance(s.get('quest_log_probe'),dict) and
        (ready is None or ready(s['quest_log_probe'])))
    t.receipt.setdefault('quest_link_details',{})[label]={'state':state,'frame':frame};t.persist()
    return state,state['quest_log_probe']


def fixture(probe):
    rows=probe.get('rows');owned=probe.get('fixture',{})
    link=owned.get('link')
    if (any(type(probe.get(k)) is not int for k in ('count','total_quests','selection')) or
            probe.get('visible') is not False or probe.get('count')!=1 or probe.get('total_quests')!=1 or
            probe.get('selection') not in (0,1) or type(probe.get('watched_count')) is not int or
            probe['watched_count'] not in (0,1) or not isinstance(rows,list) or len(rows)!=1 or
            rows[0].get('header') is not True or rows[0].get('collapsed') is not True or
            rows[0].get('index')!=1 or rows[0].get('title')!='Stormwind City' or
            owned.get('id')!=QUEST or owned.get('active') is not True or not isinstance(link,str) or
            not re.fullmatch(r'\|c[0-9a-fA-F]{8}\|Hquest:28825:80\|h\[A Personal Summons\]\|h\|r',link)):
        raise RuntimeError('requires the exact existing collapsed owned quest fixture')
    return link


def open_log(t,label,key):
    require(t.step(label,'Open the stock quest log through its observed binding.',
        {'open':{'kind':'key','value':key}},lambda b,a,s:{'status':'quest_link_log_open' if s=='open' and
            'QuestLogFrame' in a['panels'] else 'client_or_protocol_failure'},diagnostic_action='open'),
        'quest_link_log_open')


def header(t,collapsed,label):
    state,current=detail(t,label+'_before')
    rows=[r for r in current['rows'] if r.get('header') and r.get('title')=='Stormwind City']
    if len(rows)!=1:raise RuntimeError('requires one exact original quest header')
    row=rows[0]
    if row['collapsed'] is collapsed:return
    require(click(t,label,'Restore or expand the observed stock Stormwind City quest header.',
        lambda c:c['kind']=='Button' and c.get('quest_log_header') is True and c.get('quest_log_index')==row['index'],
        lambda b,a,s:{'status':'quest_link_header_pass' if s and any(r.get('header') and
            r.get('title')=='Stormwind City' and r.get('collapsed') is collapsed
            for r in detail(t,label+'_result')[1]['rows']) else 'client_or_protocol_failure'}),'quest_link_header_pass')


def pending_matches(state,text,id):
    return (id==QUEST and state.get('chat_edit_open') is True and state.get('chat_edit_focused') is True and
        state.get('chat_edit_text')==text and not state.get('lua_errors') and not state.get('blocked_actions'))


def message_requests(session,since,until=None):
    return [{'name':row['name'],'time':row['time']} for row in entries(lab.ROOT/'evidence/world_packets.jsonl')
        if row.get('session')==session and row.get('time',0)>=since and
        (until is None or row.get('time',0)<=until) and row.get('direction')=='from_client' and
        row.get('name','').startswith('CMSG_CHAT_MESSAGE_')]


def restore(t,original,native,key,selection_restore=None):
    t.clean_panels();open_log(t,'fixture.quest_link.reopen',key)
    header(t,True,'fixture.quest_link.collapse')
    require(t.step('fixture.quest_link.close','Close the restored stock quest header.',
        {'close':{'kind':'key','value':key}},lambda b,a,s:{'status':'quest_link_log_closed' if s=='close' and
            'QuestLogFrame' not in a['panels'] else 'client_or_protocol_failure'},diagnostic_action='close'),
        'quest_link_log_closed')
    state,current=detail(t,'quest_link_closed_before_selection_restore')
    if current.get('selection')!=original['selection']:
        if original['selection']!=0:raise RuntimeError('stock quest selection cannot restore the original header')
        if selection_restore is None:raise RuntimeError('selection0 requires separately reviewed ordinary reentry')
        selection_restore(t,original,native,state,current)
        state,current=detail(t,'quest_link_restored_hidden')
    result={k:current.get(k)==original.get(k) for k in ['visible','count','total_quests','selection','rows','watched_count','fixture']}
    result.update(native_quests=saved(1)==native,chat_closed=not state.get('chat_edit_open'),
        ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'))
    window=t.receipt.get('quest_link_submission_window')
    if window:
        window['until']=time.time();result['no_message_request']=not message_requests(window['session'],window['since'],window['until'])
    t.receipt['quest_link_restoration']={'checks':result};t.persist()
    if not all(result.values()):raise RuntimeError('original quest/header/selection state did not restore')


def layout_source(t,path,original,native):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires an owned closed quest-layout calibration')
    old=json.loads(path.read_text());checks=old.get('quest_link_restoration',{}).get('checks',{})
    expected={'visible','count','total_quests','selection','rows','watched_count','fixture','native_quests','chat_closed','ui_clean'}
    restored=old.get('native_restoration',{}).get('checks',{})
    expected_native={'resources','stats','spells','actions','pose','afk','position','group','no_lua_errors','no_blocked_actions'}
    if (old.get('completed') is not True or old.get('failure') is not None or not old.get('finished_at') or
            old.get('quest_link_layout_calibration') is not True or old.get('actor')!=t.fixture or
            old.get('runtime')!=t.receipt['runtime'] or old.get('quest_link_original')!=original or
            old.get('quest_link_native_original')!=native or set(checks)!=expected or
            not all(v is True for v in checks.values()) or set(restored)!=expected_native or
            not all(v is True for v in restored.values()) or
            json.dumps(old.get('native_baseline'),sort_keys=True)!=json.dumps(t.receipt['native_baseline'],sort_keys=True)):
        raise RuntimeError('closed layout calibration does not match the current owned fixture')
    t.receipt['quest_link_layout_source']={'file':str(path),'sha256':lab.sha256(path)};t.persist()


def suite(t,inspect=False,calibrate=False,source=None,selection_restore=None):
    state,original=detail(t,'quest_link_hidden_original')
    if state.get('observer_version',0)<121:raise RuntimeError('requires read-only quest-link observer121')
    t.receipt.update(custom_script_permission='blocked_by_user',quest_link_original=original,
        qualified_scope='Owned primary: stock Shift-left-click on existing active quest28825 inserts its exact public quest link into blank chat; Escape cancels without submission, quest/watch/header/selection and native fixture restore. Delivery, hyperlink clicks and other quests remain open.');t.persist()
    if inspect:
        t.receipt['qualified_scope']='Read-only hidden quest-log reconnaissance only; no gameplay qualification.';t.persist();return
    expected=fixture(original)
    if original['selection']==0 and selection_restore is None:
        raise RuntimeError('selection0 requires the staged ordinary-reentry adapter before log input')
    if t.fixture['guid']!=1:raise RuntimeError('requires the exact owned primary')
    native=saved(1);keys=state.get('quest_log_keys') or []
    if [(r['quest'],r['status']) for r in native['active']]!=[(QUEST,1)]:
        raise RuntimeError('native accepted quest fixture differs')
    if not keys:raise RuntimeError('requires the installed quest-log binding')
    key=binding_key(keys[0]);t.receipt['quest_link_native_original']=native;t.persist()
    if calibrate:
        t.receipt.update(quest_link_layout_calibration=True,qualified_scope=
            'Layout calibration only: stock quest-log open/close and original collapsed header/selection restoration through separately reviewed ordinary same-character reentry. No quest-link input or gameplay qualification.');t.persist()
    else:
        if source is None:raise RuntimeError('requires a passed source-bound layout calibration before quest-link input')
        layout_source(t,source,original,native)
    try:
        open_log(t,'fixture.quest_link.open',key);header(t,False,'fixture.quest_link.expand')
        if calibrate:return
        _,current=detail(t,'quest_link_expanded')
        row=next((r for r in current['rows'] if r.get('quest_id')==QUEST and r.get('title')==TITLE and
            r.get('header') is False),None)
        if (row is None or current.get('offset')!=0 or current.get('fixture')!=original['fixture'] or
                current.get('watched_count')!=original['watched_count']):
            raise RuntimeError('stock expanded quest row or link identity differs')
        control=target(t,'owned_quest_link_row',lambda c:c['kind']=='Button' and c['enabled'] and
            c.get('quest_log_header') is False and c.get('quest_log_id')==QUEST and
            c.get('quest_log_index')==row['index']==c.get('quest_link_index') and c['text'].strip()==TITLE)
        session=actors.session_entry(t.fixture)['session'];since=time.time()
        t.receipt['quest_link_submission_window']={'session':session,'since':since};t.persist()
        def guard(t,text,id):
            state,current=detail(t,'quest_link_pending_exact')
            result={'exact_public_link':text==expected,'pending_chat':pending_matches(state,text,id),
                'watch_count':current['watched_count']==original['watched_count'],
                'same_owned_quest':current['fixture']==original['fixture'],'native_quests':saved(1)==native,
                'no_message_request':not message_requests(session,since)}
            t.receipt['quest_link_pending_checks']={'checks':result,'message_submitted':False};t.persist()
            if not all(result.values()):raise RuntimeError('pending quest link differs from the owned public/native fixture')
        insert(t,'quest',QUEST,control,on_insert=guard)
    except Exception as error:
        t.receipt['quest_link_execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        restore(t,original,native,key,selection_restore)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--inspect',action='store_true',help='Read hidden quest-log state without opening or mutating it')
    group.add_argument('--calibrate-layout',action='store_true',help='Verify original quest-layout restoration before any link input')
    group.add_argument('--layout-source',type=Path,help='Exact passed closed calibration authorizing one fresh link trial')
    a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:native_suite(t,operations=lambda t:suite(t,a.inspect,a.calibrate_layout,a.layout_source),preserve_settings=False);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
