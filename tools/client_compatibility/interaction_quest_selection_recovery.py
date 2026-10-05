"""Recover only the failed owned quest-layout fixture through reviewed reentry."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial
from .interaction_quest_link import detail,saved
from .interaction_settings_booleans import detail as settings_detail
from .interaction_bridge_restoration import capture,restore
from .interaction_owned_language_fixture import logout
from .interaction_bridge_deploy import shot
from .interaction_lifecycle import Packets
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_ground_movement import position
from .observation.journal import Cursor

NATIVE={'resources','stats','spells','actions','pose','afk','position','group','no_lua_errors','no_blocked_actions'}
LAYOUT={'visible','count','total_quests','selection','rows','watched_count','fixture','native_quests','chat_closed','ui_clean'}


def source_matches(old,current):
    checks=old.get('quest_link_restoration',{}).get('checks',{})
    native=old.get('native_restoration',{}).get('checks',{})
    return (old.get('completed') is False and old.get('finished_at') and
        old.get('failure')=='RuntimeError: original quest/header/selection state did not restore' and
        old.get('quest_link_layout_calibration') is True and old.get('actor')==current.get('actor') and
        old.get('runtime')==current.get('runtime') and set(checks)==LAYOUT and checks.get('selection') is False and
        all(v is True for k,v in checks.items() if k!='selection') and set(native)==NATIVE and
        all(v is True for v in native.values()) and old.get('quest_link_original',{}).get('selection')==0)


def source(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires an owned closed failed quest-layout calibration')
    old=json.loads(path.read_text())
    if not source_matches(old,t.receipt) or t.fixture['guid']!=1:
        raise RuntimeError('failed calibration or current owned lifetime differs')
    return old


def prepare(t,path):
    old=source(t,path);t.clean_panels();state,current=detail(t,'quest_selection_recovery_before')
    original=old['quest_link_original'];native=json.loads(json.dumps(capture(t)))
    if (current.get('selection')!=2 or any(current.get(k)!=original.get(k) for k in
            ['visible','count','total_quests','rows','watched_count','fixture']) or
            native!=old['native_baseline'] or saved(1)!=old['quest_link_native_original']):
        raise RuntimeError('cleanup requires the exact isolated selection0-to2 difference')
    settings=settings_detail(t,'quest_selection_settings_before')
    t.receipt.update(source={'file':str(path.resolve()),'sha256':lab.sha256(path)},
        original_quest_log=original,original_native=native,original_native_quests=old['quest_link_native_original'],
        original_settings=settings,original_group=state['group'],
        qualified_scope='Cleanup only: one ordinary primary logout and separately reviewed same-character reentry to recover the failed selection0 fixture. No quest-link qualification.',custom_script_permission='blocked_by_user');t.persist()
    session=actors.session_entry(t.fixture)['session'];packets=Packets(session);started=time.time();logout(t)
    deadline=time.monotonic()+12
    while not packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','from_native'):
        if time.monotonic()>deadline:raise RuntimeError('cleanup logout lacks native character enumeration')
        time.sleep(.2)
    checks={'ordinary_request':packets.has(started,'CMSG_LOGOUT_REQUEST','from_client'),
        'native_complete':packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native'),'native_enumeration':True}
    t.receipt.update(logout_checks=checks,previous_session=session,phase='await_primary_character_selection_review',
        selection_frame=shot(t.out/'primary_selection.png'));t.persist()
    if not all(checks.values()):raise RuntimeError('ordinary cleanup logout wire checks differ')


def enter(t,path,review_path):
    path=path.resolve();review_path=review_path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence') or not review_path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires owned closed logout and fresh lobby review')
    old=json.loads(path.read_text());review=json.loads(review_path.read_text())
    frame=review.get('frame',{});image=review_path.parent/frame.get('file','')
    monitor=frame.get('monitor',{});current=owned_input.focus()
    if (old.get('completed') is not True or not old.get('finished_at') or old.get('actor')!=t.fixture or
            old.get('runtime')!=t.receipt['runtime'] or old.get('phase')!='await_primary_character_selection_review' or
            review.get('logout_episode_sha256')!=lab.sha256(path) or review.get('selected_character')!='Harnessone' or
            review.get('selected_level')!=85 or review.get('reviewed') is not True or
            not image.resolve().is_relative_to(lab.ROOT/'evidence') or not image.is_file() or
            frame.get('sha256')!=old.get('selection_frame',{}).get('sha256') or
            not 0<=time.time()-image.stat().st_mtime<=120 or
            lab.sha256(image)!=frame.get('sha256') or not monitor.get('second_monitor_verified') or
            monitor.get('pid')!=t.receipt['runtime']['client']['pid'] or
            monitor.get('input_isolation',{}).get('actor')!='primary' or
            monitor.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid']):
        raise RuntimeError('fresh reviewed owned primary selection differs')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT online FROM client442_characters.characters WHERE guid=1 AND account=%s',(t.fixture['account_id'],))
        if q.fetchone()!=(0,):raise RuntimeError('reviewed primary is not offline')
    base=old['original_native']
    if known(1)!=base['spells'] or saved_actions(1)!=base['actions'] or position(1)!=base['position']:
        raise RuntimeError('offline native primary differs')
    t.receipt.update(source={'file':str(path),'sha256':lab.sha256(path)},
        reviewed_selection={'path':str(review_path),'sha256':lab.sha256(review_path)},
        qualified_scope='Cleanup-only verified ordinary same-character reentry after the failed quest-layout calibration. No quest-link input or qualification.',custom_script_permission='blocked_by_user');t.persist()
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in cursor.poll():pass
    started=time.time();t.io.key('Return',hold=1.2);state,frame=t.observe('quest_selection_reentered',seconds=240)
    session=actors.session_entry(t.fixture)['session'];packets=[{k:r[k] for k in ['time','name','direction']} for r in cursor.poll()
        if r.get('time',0)>=started and r.get('session')==session and r.get('name') in
        {'CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD'}]
    checks={'owned_guid':state['guid']==t.guid,'owned_name':state['player']=='Harnessone','level':state['level']==85,
        'ordinary_login':any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in packets),
        'native_login':any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in packets)}
    t.receipt.update(reentry_checks=checks,packets=packets,reentry_frame=frame,session=session);t.persist()
    if not all(checks.values()):raise RuntimeError('ordinary primary recovery reentry differs')
    restore(t,base);state,current=detail(t,'quest_selection_recovered_hidden')
    checks={k:current.get(k)==old['original_quest_log'].get(k) for k in
        ['visible','count','total_quests','selection','rows','watched_count','fixture']}
    checks.update(native_quests=saved(1)==old['original_native_quests'],group=state['group']==old['original_group'])
    settings=settings_detail(t,'quest_selection_settings_after')
    checks.update({k:settings.get(k)==old['original_settings'].get(k) for k in ['cvars','values','category','search','unapplied']})
    t.receipt['quest_selection_recovery']={'checks':checks};t.persist()
    if not all(checks.values()):raise RuntimeError('original quest selection or observed settings did not recover')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=['logout','enter'],required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--review',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if (a.phase=='enter')!=bool(a.review):p.error('only enter requires its fresh reviewed character selection')
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:(prepare(t,a.source) if a.phase=='logout' else enter(t,a.source,a.review));t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
