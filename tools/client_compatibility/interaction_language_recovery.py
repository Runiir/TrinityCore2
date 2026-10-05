"""Remove only the trace-backed extra language skill while its owner is offline."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial,binding_key
from .interaction_bridge_deploy import shot,identity
from .interaction_lifecycle import Packets
from .interaction_chat_language import native_skills
from .interaction_spellbook_navigation import known
from .interaction_spellbook_professions import skills
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_sit_stand import pose,afk
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_actions import saved_actions
from .interaction_fixture_permissions import permission_rows
from .interaction_actionbar_pages import detail as bar_detail
from .interaction_ground_movement import position
from .observation.inventory import Inventory
from .observation.journal import Cursor


def source(path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires the private failed language receipt')
    d=json.loads(path.read_text())
    failed={k for k,v in d.get('language_restoration',{}).get('checks',{}).items() if not v}
    legacy=(d['failure']=='RuntimeError: original language fixture restoration differs' and
        failed=={'original_skills','original_native_skills'})
    staged=(d.get('language_lifecycle_schema')=='client442_language_lifecycle_v1' and
        d.get('phase')=='await_offline_language_cleanup' and
        {'original_skills','original_native_skills'}<=failed<=
        {'original_skills','original_native_skills','original_languages'})
    if (d['actor']['guid']!=1 or d['completed'] or not d.get('finished_at') or
        not (legacy or staged) or
        not all(d['native_restoration']['checks'].values()) or
        not all(r.get('restored') for r in d['fixture_permissions'])):
        raise RuntimeError('exact failed fixture or restoration evidence differs')
    return d


def offline(t,path):
    old=source(path);original=old['language_fixture_baseline']
    if t.fixture!=old['actor'] or t.receipt['runtime']!=old['runtime']:
        raise RuntimeError('owned actor or process lifetime differs')
    if known(1)!=original['spells'] or sorted(skills(1))!=sorted(original['skills']+[[111,1,300]]):
        raise RuntimeError('refuses an unexpected native spell or skill change')
    t.clean_panels();state,frame=t.observe('language_recovery_before_logout')
    session=actors.session_entry(t.fixture)['session'];packets=Packets(session);started=time.time()
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},previous_session=session,
        baseline={'state':state,'frame':frame},native_world=identity('worldserver'),phase='logout_started');t.persist()
    t.submit_chat('/logout')
    deadline=time.monotonic()+45
    while not packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native'):
        if time.monotonic()>deadline:raise RuntimeError('normal owned logout did not complete')
        time.sleep(.2)
    if not packets.has(started,'CMSG_LOGOUT_REQUEST','from_client'):
        raise RuntimeError('ordinary logout request was not observed')
    frame=shot(t.out/'owned_selection.png')
    with lab.connection() as con,con.cursor() as q:
        q.execute('SELECT online FROM client442_characters.characters WHERE guid=1');row=q.fetchone()
        if row!=(0,) or sorted(skills(1))!=sorted(original['skills']+[[111,1,300]]):
            raise RuntimeError('refuses skill cleanup until the exact owned character is offline')
        q.execute('DELETE FROM client442_characters.character_skills WHERE guid=1 AND skill=111 AND value=1 AND max=300')
        if q.rowcount!=1:raise RuntimeError('exact extra language row was not removed')
        con.commit()
    if skills(1)!=original['skills']:raise RuntimeError('offline skill rows differ from source baseline')
    t.receipt.update(phase='await_owned_selection_review',selection_frame=frame,
        offline_skill_rows_restored=True,completed=True);t.persist()


def enter(t,path,offline_path,review_path):
    old=source(path);done=json.loads(offline_path.read_text())
    if (not done['completed'] or done.get('phase')!='await_owned_selection_review' or
        done['actor']!=t.fixture or done['runtime']!=t.receipt['runtime'] or
        done['source']['sha256']!=lab.sha256(path) or identity('worldserver')!=done['native_world']):
        raise RuntimeError('reviewed owned cleanup identity differs')
    review=json.loads(review_path.read_text());frame=review['frame']
    image=review_path.parent/frame['file'];monitor=frame['monitor']
    if (review['offline_episode_sha256']!=lab.sha256(offline_path) or lab.sha256(image)!=frame['sha256'] or
        not monitor['second_monitor_verified'] or monitor['input_isolation']['actor']!='primary'):
        raise RuntimeError('settled owned selection evidence differs')
    with lab.connection() as con,con.cursor() as q:
        q.execute('SELECT online FROM client442_characters.characters WHERE guid=1')
        if q.fetchone()!=(0,) or skills(1)!=old['language_fixture_baseline']['skills']:
            raise RuntimeError('owned offline baseline changed before reviewed reentry')
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},
        offline_cleanup={'path':str(offline_path),'sha256':lab.sha256(offline_path)},
        reviewed_selection={'path':str(review_path),'sha256':lab.sha256(review_path),'frame':frame},
        selection_before=shot(t.out/'selection_before.png'));t.persist()
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in cursor.poll():pass
    started=time.time()
    t.io.key('Return',hold=1.2);time.sleep(8)
    after,frame=t.observe('owned_language_reentry',seconds=120)
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    native=old['native_baseline'];original=old['language_fixture_baseline']
    if pose(oracle)!=native['pose']:
        if {pose(oracle)['stand'],native['pose']['stand']}!={0,1}:raise RuntimeError('unexpected reentry pose')
        bar=bar_detail(t,'language_recovery_pose_binding')
        t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':1.2});time.sleep(12)
    if afk(oracle)!=native['afk']:t.execute({'kind':'chat','value':'/afk'})
    public=detail(t,'language_recovery_restored');state,frame=t.observe('language_recovery_rendered')
    login=[{k:r[k] for k in ['session','time','name','direction']} for r in cursor.poll()
        if r.get('session')==session and r.get('time',0)>=started and
        r.get('name') in ['CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD']]
    checks={'resources':resources(oracle)==native['resources'],'stats':restored_native_state(native['stats'],native_state(oracle)),
        'spells':known(1)==native['spells'],'actions':saved_actions(1)==native['actions'],
        'pose':pose(oracle)==native['pose'],'afk':afk(oracle)==native['afk'],
        'position':position(1)==native['position'],'group':state['group']==done['baseline']['state']['group'],
        'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions'),
        'skills':skills(1)==original['skills'],'native_skills':native_skills(oracle)==original['native_skills'],
        'target':oracle.pair(1,'UNIT_FIELD_TARGET')==original['target'],
        'languages':public['languages']==old['language_baseline']['languages'],
        'chat_settings':signature(public)==signature(old['language_baseline']),
        'channels':public['channels']==old['language_baseline']['channels'],
        'native_world_unchanged':identity('worldserver')==done['native_world'],
        'ordinary_login':any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in login),
        'native_login':any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in login)}
    t.receipt.update(reentry_checks=checks,session=session,public=public,frame=frame,login_packets=login);t.persist()
    if not all(checks.values()):raise RuntimeError('source-bound language recovery differs')
    t.receipt['completed']=True


def verify(t,path,entered_path):
    old=source(path);entered=json.loads(entered_path.read_text())
    failed={k for k,v in entered.get('reentry_checks',{}).items() if not v}
    if (entered['completed'] or not entered.get('finished_at') or failed!={'native_skills'} or
        entered['failure']!='RuntimeError: source-bound language recovery differs' or
        entered['actor']!=t.fixture or entered['runtime']!=t.receipt['runtime']):
        raise RuntimeError('exact stale-oracle reentry evidence differs')
    offline_path=Path(entered['offline_cleanup']['path'])
    if lab.sha256(offline_path)!=entered['offline_cleanup']['sha256']:
        raise RuntimeError('offline baseline evidence changed')
    offline=json.loads(offline_path.read_text())
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    native=old['native_baseline'];original=old['language_fixture_baseline']
    public=detail(t,'language_recovery_verified');state,frame=t.observe('language_recovery_verified_rendered')
    checks={'resources':resources(oracle)==native['resources'],'stats':restored_native_state(native['stats'],native_state(oracle)),
        'spells':known(1)==native['spells'],'actions':saved_actions(1)==native['actions'],
        'pose':pose(oracle)==native['pose'],'afk':afk(oracle)==native['afk'],
        'position':position(1)==native['position'],'group':state['group']==offline['baseline']['state']['group'],
        'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions'),
        'skills':skills(1)==original['skills'],'native_skills':native_skills(oracle)==original['native_skills'],
        'target':oracle.pair(1,'UNIT_FIELD_TARGET')==original['target'],
        'languages':public['languages']==old['language_baseline']['languages'],
        'chat_settings':signature(public)==signature(old['language_baseline']),
        'channels':public['channels']==old['language_baseline']['channels'],
        'permissions':all(permission_rows(t.fixture['account_id'],r['permission'])==tuple(r['baseline'])
            for r in old['fixture_permissions']),
        'native_world_unchanged':identity('worldserver')==offline['native_world'],
        'same_completed_login':session==entered['session'] and all(entered['reentry_checks'][k]
            for k in ['ordinary_login','native_login','native_world_unchanged'])}
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},
        entered_source={'path':str(entered_path),'sha256':lab.sha256(entered_path)},
        verification_checks=checks,frame=frame,public=public,gameplay_input_replayed=False,
        scope='Fresh source-bound restoration after correcting native oracle recreation semantics. Earlier failed episodes remain excluded.');t.persist()
    if not all(checks.values()):raise RuntimeError('fresh language recovery verification differs')
    t.receipt['completed']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--offline-source',type=Path)
    p.add_argument('--verify-entered-source',type=Path)
    p.add_argument('--reviewed-owned-selection',action='store_true');p.add_argument('--selection-review',type=Path);a=p.parse_args()
    if a.offline_source and (not a.reviewed_owned_selection or not a.selection_review):
        p.error('review the settled owned Harnessone selection frame first')
    t=Trial(a.output,controller='code')
    try:
        if a.verify_entered_source:verify(t,a.source,a.verify_entered_source)
        elif a.offline_source:enter(t,a.source,a.offline_source,a.selection_review)
        else:offline(t,a.source)
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}),flush=True)
