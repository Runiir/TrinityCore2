"""Restore the source-bound initial offline friend cache through normal reentry."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_friend_notes import FRIEND
from .interaction_friend_note_persistence import ORIGINAL_FIELDS,closed,selection_review
from .interaction_friends import social,public,canonical,open_friends,close_friends,restored
from .interaction_bridge_restoration import capture,restore
from .interaction_owned_language_fixture import logout
from .interaction_bridge_deploy import shot
from .interaction_lifecycle import Packets
from .interaction_chat_window import detail as chat_detail
from .interaction_chat_settings import signature
from .interaction_trade import inventory
from .interaction_quest_link import saved as quests
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_ground_movement import position
from .observation.character_selection import characters
from .auth.realms import ADDRESS

NATIVE={'resources','stats','spells','actions','pose','afk','position','no_lua_errors','no_blocked_actions'}
FRIENDS={'native_social','public_friends','inventory_money','offline_owned_dwarf','quest_layout','native_quests',
    'same_session','group','panels_closed','chat_closed','no_lua_errors','no_blocked_actions'}
PHASE='await_original_offline_friend_cache_reentry'


def source_matches(old,current):
    native=old.get('bridge_native_restoration',{}).get('checks',{})
    friends=old.get('friend_restoration',{}).get('checks',{})
    failed=(old.get('completed') is False and old.get('failure')==
        'RuntimeError: fresh target control was not observed: fixture.friend_whisper.row')
    guard=old.get('friend_whisper_guard',{})
    unsent=(old.get('completed') is False and old.get('failure')==
        'RuntimeError: exact owned friend whisper text or target differs' and
        guard.get('exact') is False and guard.get('submitted') is False and
        guard.get('input_replayed') is False and guard.get('target') in (FRIEND,FRIEND+'-Client442Lab') and
        isinstance(guard.get('token'),str) and bool(re.fullmatch(r'TC442UI:friend_[0-9a-f]{8}',guard['token'])))
    ignored=old.get('ignored_chat_restoration',{}).get('checks',{})
    ignored_failed=(old.get('completed') is False and old.get('failure')==
        'RuntimeError: owned ignored-chat outcomes differ' and
        set(ignored)=={'native_social','public_friends_preserved','stock_ignore_empty'} and
        all(v is True for v in ignored.values()))
    prepared=(old.get('friend_cache_restore_required') is True and
        ((old.get('completed') is True and old.get('failure') is None) or ignored_failed))
    return (bool(old.get('finished_at')) and (failed or unsent or prepared) and old.get('actor')==current.get('actor') and
        old.get('runtime')==current.get('runtime') and old.get('actor',{}).get('guid')==1 and
        set(native)==NATIVE and all(v is True for v in native.values()) and set(friends)==FRIENDS and
        friends['public_friends'] is False and all(v is True for k,v in friends.items() if k!='public_friends') and
        old.get('original_social')==[[1,2,1,''],[2,1,1,'']] and old.get('original_public_friends')==[
            {'name':FRIEND,'connected':False,'level':0,'notes':''}] and
        old.get('original_quest_log',{}).get('selection')==0 and
        old.get('custom_script_permission')=='blocked_by_user' and
        old.get('softTargetInteract')=={'original':'0','current_stock_disabled':'1','original_restored':False})


def offline(t):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT online FROM client442_characters.characters WHERE guid=1 AND account=%s',
            (t.fixture['account_id'],));row=q.fetchone()
        if row not in [(0,),(1,)]:raise RuntimeError('owned primary native online row is absent or invalid')
        return row==(0,)


def prepare(t,path):
    path,old=closed(path)
    if not source_matches(old,t.receipt):raise RuntimeError('closed friend-cache-only mismatch differs')
    peer_path=path.parent.parent/'scout/episode.json';peer=json.loads(peer_path.read_text())
    checks=peer.get('parked_restoration',{}).get('checks',{})
    if (not peer.get('finished_at') or peer.get('actor',{}).get('guid')!=2 or len(checks)!=19 or
        not all(v is True for v in checks.values())):raise RuntimeError('source scout is not fully parked')
    state,frame=t.observe('friend_cache_recovery_current')
    if (public(state.get('friends'))!=[{'name':FRIEND,'connected':False,'level':1,'notes':''}] or
        state['group']!=old['original_group'] or social()!=old['original_social'] or
        canonical(capture(t))!=old['native_baseline'] or canonical(inventory())!=old['original_inventory'] or
        quests(1)!=old['original_native_quests']):raise RuntimeError('current fixture is not the exact isolated cached-level difference')
    current_chat=chat_detail(t,'friend_cache_recovery_chat')
    if signature(current_chat)!=signature(old['original_chat']):raise RuntimeError('original chat settings differ')
    restore(t,old['native_baseline'])
    t.receipt.update({k:old[k] for k in ORIGINAL_FIELDS},original_chat=old['original_chat'],
        source_original={'path':str(path),'sha256':lab.sha256(path)},
        source_parked_scout={'path':str(peer_path),'sha256':lab.sha256(peer_path)},
        previous_session=old['session'],current_cache_before=state['friends'],current_cache_frame=frame,
        qualified_scope='Cleanup only: one normal primary logout/reentry restores the exact original unknown offline friend cache. No social qualification.');t.persist()
    session=actors.session_entry(t.fixture)['session'];packets=Packets(session);started=time.time();logout(t)
    deadline=time.monotonic()+15
    while not packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','to_client'):
        if time.monotonic()>deadline:raise RuntimeError('cache cleanup logout lacks modern enumeration')
        time.sleep(.2)
    rows=[r for r in packets.since(started) if r['name'] in
        ('CMSG_LOGOUT_REQUEST','SMSG_LOGOUT_COMPLETE','SMSG_ENUM_CHARACTERS_RESULT')]
    expected=[{'guid':[1,(2<<58)|(1<<42)],'name':'Harnessone','flags':0,'equipment':state['equipment'],
        'level':85,'slot':0,'realm':ADDRESS}]
    enums=[characters(bytes.fromhex(r['body'])) for r in rows if r['name']=='SMSG_ENUM_CHARACTERS_RESULT' and r['direction']=='to_client']
    checks={'ordinary_request':packets.has(started,'CMSG_LOGOUT_REQUEST','from_client'),
        'native_complete':packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native'),
        'native_enumeration':packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','from_native'),
        'modern_owned_enumeration':bool(enums) and all(e==expected for e in enums),'native_offline':offline(t)}
    t.receipt.update(logout_checks=checks,logout_packets=rows,phase=PHASE,session=session,
        selection_frame=shot(t.out/'primary_selection.png'));t.persist()
    if not all(checks.values()):raise RuntimeError('cache cleanup logout identity differs')


def finish(t,path,review):
    path,old=closed(path);checks=old.get('logout_checks',{})
    if (old.get('completed') is not True or old.get('failure') is not None or not old.get('finished_at') or
        old.get('phase')!=PHASE or old.get('actor')!=t.fixture or old.get('runtime')!=t.receipt['runtime'] or
        len(checks)!=5 or not all(v is True for v in checks.values())):
        raise RuntimeError('closed original friend cache logout differs')
    selection_review(t,review,path)
    original_path,original=closed(Path(old['source_original']['path']))
    if lab.sha256(original_path)!=old['source_original']['sha256'] or not source_matches(original,t.receipt):
        raise RuntimeError('original cache mismatch source changed')
    base=original['native_baseline']
    if (not offline(t) or known(1)!=base['spells'] or saved_actions(1)!=base['actions'] or position(1)!=base['position']):
        raise RuntimeError('offline original primary native fixture differs')
    t.receipt.update({k:original[k] for k in ORIGINAL_FIELDS},original_chat=original['original_chat'],
        source={'path':str(path),'sha256':lab.sha256(path)},source_original=old['source_original'],
        reviewed_selection={'path':str(review.resolve()),'sha256':lab.sha256(review),
            'frame':json.loads(review.read_text())['frame']},previous_session=old['session'],
        qualified_scope='Cleanup only: exact original unknown offline friend cache and full fixture restoration after normal reentry. No feature qualification.');t.persist()
    packets=Packets(old['session']);started=time.time();t.execute({'kind':'key','value':'Return','hold':1.2})
    state,frame=t.observe('friend_cache_recovery_entered',seconds=240)
    session=actors.session_entry(t.fixture)['session'];packets.session=session
    rows=[r for r in packets.since(started) if r['name'] in ('CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD')]
    checks={'owned_character':state.get('guid')==t.guid and state.get('player')=='Harnessone' and state.get('level')==85,
        'observer123':state.get('observer_version')==123,'native_online':not offline(t),
        'ordinary_login':any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in rows),
        'native_login':any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in rows)}
    t.receipt.update(reentry_checks=checks,entry_packets=rows,entry_frame=frame,session=session);t.persist()
    if not all(checks.values()):raise RuntimeError('cache cleanup reentry differs')
    try:
        open_friends(t,'fixture.friend_cache.restored_open');state,frame=t.observe('original_offline_friend_cache_restored')
        checks={'original_public_cache':public(state.get('friends'))==original['original_public_friends'],
            'native_social':social()==original['original_social'],'friends_ready':state.get('friends_ready') is True}
        t.receipt['friend_cache_restoration']={'checks':checks,'state':state,'frame':frame};t.persist()
        if not all(checks.values()):raise RuntimeError('original unknown offline friend cache did not reset')
    finally:
        close_friends(t);expected={**original,'session':session};restored(t,expected)
        current=chat_detail(t,'friend_cache_original_chat_restored');checks={
            'original_chat_settings':signature(current)==signature(original['original_chat'])}
        t.receipt['chat_restoration']={'checks':checks};t.persist();restore(t,base)
        if not all(checks.values()):raise RuntimeError('original chat settings did not restore')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=['prepare','finish'],required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--review',type=Path);a=p.parse_args()
    if (a.phase=='finish')!=bool(a.review):p.error('only finish requires fresh selection review')
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        try:(prepare(t,a.source) if a.phase=='prepare' else finish(t,a.source,a.review));t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}),flush=True)
