"""Restore only the closed disabled-tab failure's owned Ignore flag and cache."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_friend_note_persistence import ORIGINAL_FIELDS,closed
from .interaction_friend_cache_recovery import NATIVE,FRIENDS
from .interaction_ignore_friend import ORIGINAL,IGNORED,ensure_ignore_tab,mutation
from .interaction_ignore import cleanup,source_matches as probe_matches
from .interaction_friend_presence import public_presence_matches
from .interaction_friends import social,canonical,open_friends,restored
from .interaction_bridge_restoration import capture,restore
from .interaction_trade import inventory
from .interaction_quest_link import saved as quests
from .interaction_lifecycle import Packets
from .interaction_chat_window import detail
from .interaction_chat_settings import signature


def source_matches(old,current,peer):
    native=old.get('bridge_native_restoration',{}).get('checks',{})
    friends=old.get('friend_restoration',{}).get('checks',{})
    parked=peer.get('parked_restoration',{}).get('checks',{})
    return (old.get('completed') is False and old.get('failure')=='RuntimeError: target is not an enabled ordinary button' and
        bool(old.get('finished_at')) and old.get('actor')==current.get('actor') and
        old.get('actor',{}).get('guid')==1 and old.get('runtime')==current.get('runtime') and
        set(native)==NATIVE and all(v is True for v in native.values()) and set(friends)==FRIENDS and
        friends['native_social'] is False and friends['public_friends'] is False and
        all(v is True for k,v in friends.items() if k not in ('native_social','public_friends')) and
        old.get('original_social')==ORIGINAL and old.get('original_public_friends')==[
            {'name':'Harnesstwo','connected':False,'level':0,'notes':''}] and
        old.get('original_quest_log',{}).get('selection')==0 and
        old.get('custom_script_permission')=='blocked_by_user' and
        old.get('softTargetInteract')=={'original':'0','current_stock_disabled':'1','original_restored':False} and
        bool(peer.get('finished_at')) and peer.get('actor',{}).get('guid')==2 and len(parked)==19 and
        all(v is True for v in parked.values()) and bool(old.get('ignored_chat_source')))


def recover(t,path):
    path,old=closed(path);peer_path=path.parent.parent/'scout/episode.json';peer=json.loads(peer_path.read_text())
    if not source_matches(old,t.receipt,peer):raise RuntimeError('closed disabled-tab cleanup source differs')
    probe_path=Path(old['ignored_chat_source']['path']);probe=json.loads(probe_path.read_text())
    if lab.sha256(probe_path)!=old['ignored_chat_source']['sha256'] or not probe_matches(probe,t.receipt):
        raise RuntimeError('original current Ignore dialog probe changed')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT name,level,online FROM client442_characters.characters WHERE guid=2 AND account=%s',
            (peer['actor']['account_id'],))
        if q.fetchone()!=('Harnesstwo',1,0):raise RuntimeError('source-bound scout is no longer parked offline')
    state,frame=t.observe('ignore_recovery_current')
    if (social()!=IGNORED or not public_presence_matches(state.get('friends'),False) or
        state['group']!=old['original_group'] or canonical(capture(t))!=old['native_baseline'] or
        canonical(inventory())!=old['original_inventory'] or quests(1)!=old['original_native_quests']):
        raise RuntimeError('current fixture is not exactly the saved Ignore bit plus cached level')
    current=detail(t,'ignore_recovery_original_chat')
    if signature(current)!=signature(old['original_chat']):raise RuntimeError('original chat settings differ')
    restore(t,old['native_baseline']);t.receipt.update({k:old[k] for k in ORIGINAL_FIELDS},
        original_chat=old['original_chat'],source={'path':str(path),'sha256':lab.sha256(path)},
        source_parked_scout={'path':str(peer_path),'sha256':lab.sha256(peer_path)},
        source_probe=old['ignored_chat_source'],session=actors.session_entry(t.fixture)['session'],
        current_frame=frame,qualified_scope='Cleanup only: remove the saved owned Ignore bit while scout stays offline; exact original primary cache reset remains required. No social qualification.');t.persist()
    packets=Packets(t.receipt['session'])
    try:
        open_friends(t,'fixture.ignore_recovery.open');ensure_ignore_tab(t,'fixture.ignore_recovery.tab')
        mutation(t,packets,'fixture.ignore_recovery.remove',probe,remove=True,connected=False)
    finally:cleanup(t)
    try:restored(t,{**old,'session':t.receipt['session']})
    except RuntimeError:
        native=t.receipt.get('bridge_native_restoration',{}).get('checks',{})
        friends=t.receipt.get('friend_restoration',{}).get('checks',{})
        if (set(native)!=NATIVE or not all(v is True for v in native.values()) or set(friends)!=FRIENDS or
            friends['public_friends'] is not False or any(v is not True for k,v in friends.items() if k!='public_friends')):raise
        t.receipt.update(friend_cache_restore_required=True,phase='await_original_primary_friend_cache_reset');t.persist()
    current=detail(t,'ignore_recovery_chat_restored');checks={'original_chat_settings':signature(current)==signature(old['original_chat'])}
    t.receipt['chat_restoration']={'checks':checks};t.persist();restore(t,old['native_baseline'])
    if not all(checks.values()):raise RuntimeError('original chat settings did not restore')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        try:recover(t,a.source);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}),flush=True)
