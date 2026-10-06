"""Check an owned stock friend note across normal character logout and reentry."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_friend_notes import baseline,source_matches,set_note,cancel_dialog,FRIEND,GUID,HIGH
from .interaction_friends import canonical,social,public,open_friends,close_friends,restored
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_bridge_deploy import shot
from .interaction_owned_language_fixture import logout
from .interaction_lifecycle import Packets
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_ground_movement import position
from .observation.character_selection import characters
from .world.buffer import Reader

NOTE='Owned offline scout note UI105'
PHASE='await_owned_friend_note_selection_review'
ORIGINAL_FIELDS=('native_baseline','original_social','original_public_friends','original_inventory',
    'original_quest_log','original_native_quests','original_group','offline_owned_dwarf',
    'custom_script_permission','softTargetInteract')
LOGOUT_CHECKS={'ordinary_request','native_complete','native_enumeration','modern_owned_enumeration','native_offline'}


def closed(path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned episode')
    return path,json.loads(path.read_text())


def online(t):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT name,level,online FROM client442_characters.characters WHERE guid=1 AND account=%s',
                  (t.fixture['account_id'],))
        row=q.fetchone()
    if row is None or row[:2]!=('Harnessone',85):raise RuntimeError('owned primary native identity differs')
    return row[2]


def prepared_matches(old,current):
    checks=old.get('logout_checks',{})
    return (old.get('completed') is True and old.get('failure') is None and bool(old.get('finished_at')) and
        old.get('actor')==current.get('actor') and old.get('runtime')==current.get('runtime') and
        old.get('phase')==PHASE and old.get('marker_note')==NOTE and
        set(checks)==LOGOUT_CHECKS and all(v is True for v in checks.values()) and
        all(k in old for k in ORIGINAL_FIELDS) and old.get('original_social')==[[1,2,1,''],[2,1,1,'']] and
        old.get('original_public_friends')==[{'name':FRIEND,'connected':False,'level':0,'notes':''}] and
        old.get('original_quest_log',{}).get('selection')==0 and
        old.get('custom_script_permission')=='blocked_by_user' and
        old.get('softTargetInteract')=={'original':'0','current_stock_disabled':'1','original_restored':False})


def contact_checks(rows):
    native=[];modern=[]
    for row in rows:
        if row.get('name')!='SMSG_CONTACT_LIST':continue
        r=Reader(bytes.fromhex(row['body']));flags=r.unpack('I')[0]
        if flags&~7:raise ValueError('unexpected contact-list flags')
        entries=[]
        if row['direction']=='from_native':
            count=r.unpack('I')[0]
            if count>255:raise ValueError('unbounded native contacts')
            for _ in range(count):
                guid,kind=r.unpack('QI');note=bytearray()
                while True:
                    value=r.raw(1)
                    if value==b'\0':break
                    note.extend(value)
                    if len(note)>1023:raise ValueError('unbounded native note')
                status=r.unpack('B')[0] if kind&1 else 0
                area,level,klass=r.unpack('III') if status else (0,0,0)
                entries.append((guid,kind,status,area,level,klass,note.decode()))
            r.end();native.append((flags,entries))
        elif row['direction']=='to_client':
            count=r.bits(8)
            for _ in range(count):
                guid=r.guid();account=r.guid();realm,virtual,kind,status,area,level,klass=r.unpack('IIIBIII')
                note=r.raw(r.bits(10)).decode()
                entries.append((guid,account,realm,virtual,kind,status,area,level,klass,note))
            r.end();modern.append((flags,entries))
    expected_native=[(GUID,1,0,0,0,0,NOTE)]
    expected_modern=[((GUID,HIGH),(0,0),1,1,1,0,0,0,0,NOTE)]
    return {'native_reloaded_marker':bool(native) and all(e==expected_native for _,e in native),
        'modern_reloaded_marker':bool(modern) and all(e==expected_modern for _,e in modern),
        'paired_contact_lists':len(native)==len(modern) and [f for f,_ in native]==[f for f,_ in modern],
        'no_note_rewrite_after_login':not any(r.get('name')=='CMSG_SET_CONTACT_NOTES' for r in rows)}


def cleanup_note(t,packets,probe,original):
    cancel_dialog(t);current=social()
    if current!=original['original_social']:
        if current!=[[1,2,1,NOTE],[2,1,1,'']]:
            raise RuntimeError('note cleanup refuses any unrelated social change')
        state,_=t.observe('friend_note_persistence_restore_guard')
        if 'FriendsFrame' not in state['panels']:open_friends(t,'fixture.friend_note.restore_open')
        set_note(t,packets,'fixture.friend_note.restore','',probe)
    close_friends(t);restored(t,original)


def prepare(t,path):
    path,probe=closed(path)
    if not source_matches(probe,t.receipt):raise RuntimeError('current closed owned note-dialog probe differs')
    baseline(t,123);state,_=t.observe('friend_note_persistence_original')
    if t.receipt['original_quest_log']['selection']!=0:raise RuntimeError('original hidden quest selection differs')
    t.receipt.update(source_probe={'path':str(path),'sha256':lab.sha256(path)},marker_note=NOTE,
        expected_selection=[{'guid':[1,HIGH],'name':'Harnessone','flags':0,'equipment':state['equipment'],
            'level':85,'slot':0,'realm':1}],qualified_scope=
        'Setup only: temporary owned offline friend note and ordinary logout. No persistence qualification.');t.persist()
    packets=Packets(t.receipt['session']);logout_started=False
    try:
        open_friends(t,'fixture.friend_note.open');set_note(t,packets,'fixture.friend_note.persist_marker',NOTE,probe)
        close_friends(t);started=time.time();logout_started=True
        t.receipt['logout_started_at']=started;t.persist();logout(t)
        deadline=time.monotonic()+15
        while not packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','to_client'):
            if time.monotonic()>deadline:raise RuntimeError('ordinary logout lacks modern character enumeration')
            time.sleep(.2)
        rows=[r for r in packets.since(started) if r['name'] in
            ('CMSG_LOGOUT_REQUEST','SMSG_LOGOUT_COMPLETE','SMSG_ENUM_CHARACTERS_RESULT')]
        enums=[characters(bytes.fromhex(r['body'])) for r in rows if
            r['name']=='SMSG_ENUM_CHARACTERS_RESULT' and r['direction']=='to_client']
        checks={'ordinary_request':packets.has(started,'CMSG_LOGOUT_REQUEST','from_client'),
            'native_complete':packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native'),
            'native_enumeration':packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','from_native'),
            'modern_owned_enumeration':bool(enums) and all(e==t.receipt['expected_selection'] for e in enums),
            'native_offline':online(t)==0}
        t.receipt.update(logout_checks=checks,logout_packets=rows,character_enumerations=enums,
            previous_session=t.receipt['session'],phase=PHASE,selection_frame=shot(t.out/'primary_selection.png'));t.persist()
        if not all(checks.values()):raise RuntimeError('normal owned note logout checks differ')
    except Exception:
        if not logout_started or online(t)==1:cleanup_note(t,packets,probe,t.receipt)
        else:t.receipt['cleanup_requires_reviewed_reentry']=True;t.persist()
        raise


def selection_review(t,path,source):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence'):raise ValueError('requires private owned selection review')
    review=json.loads(path.read_text());frame=review.get('frame',{});image=path.parent/frame.get('file','')
    monitor=frame.get('monitor',{});current=owned_input.focus()
    if (review.get('reviewed') is not True or review.get('episode_sha256')!=lab.sha256(source) or
        review.get('selected_character')!='Harnessone' or review.get('selected_level')!=85 or
        not image.resolve().is_relative_to(lab.ROOT/'evidence') or not image.is_file() or
        lab.sha256(image)!=frame.get('sha256') or not 0<=time.time()-image.stat().st_mtime<=120 or
        not monitor.get('second_monitor_verified') or monitor.get('pid')!=t.receipt['runtime']['client']['pid'] or
        monitor.get('input_isolation',{}).get('actor')!='primary' or
        monitor.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid']):
        raise RuntimeError('fresh reviewed owned primary selection differs')
    return review


def finish(t,path,review_path):
    path,old=closed(path)
    if not prepared_matches(old,t.receipt):raise RuntimeError('closed owned note/logout preparation differs')
    review=selection_review(t,review_path,path);native=old['native_baseline']
    if (online(t)!=0 or social()!=[[1,2,1,NOTE],[2,1,1,'']] or
        known(1)!=native['spells'] or saved_actions(1)!=native['actions'] or position(1)!=native['position']):
        raise RuntimeError('offline original actor or temporary note differs')
    probe_path,probe=closed(Path(old['source_probe']['path']))
    if lab.sha256(probe_path)!=old['source_probe']['sha256'] or not source_matches(probe,t.receipt):
        raise RuntimeError('source dialog probe changed')
    original={k:canonical(old[k]) for k in ORIGINAL_FIELDS}
    t.receipt.update(original,source={'path':str(path),'sha256':lab.sha256(path)},
        reviewed_selection={'path':str(review_path.resolve()),'sha256':lab.sha256(review_path),'frame':review['frame']},
        previous_session=old['session'],marker_note=NOTE,qualified_scope=
        'One short ASCII owned offline friend note across ordinary same-character logout/reentry, followed by exact empty-note and original fixture restoration.');t.persist()
    packets=Packets(old['session']);started=time.time();entered=False
    try:
        t.receipt['entry_input']={'kind':'key','value':'Return','hold':1.2};t.persist()
        t.execute(t.receipt['entry_input']);state,frame=t.observe('friend_note_persistence_reentered',seconds=240)
        entered=True;session=actors.session_entry(t.fixture)['session'];packets.session=session
        original['session']=session;t.receipt['session']=session
        login=[r for r in packets.since(started) if r['name'] in ('CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD')]
        checks={'same_owned_character':state.get('player')=='Harnessone' and state.get('level')==85 and state.get('guid')==t.guid,
            'observer123':state.get('observer_version')==123,'native_online':online(t)==1,
            'ordinary_login':any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in login),
            'native_login':any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in login)}
        t.receipt.update(reentry_checks=checks,login_packets=login,reentry_frame=frame);t.persist()
        if not all(checks.values()):raise RuntimeError('normal owned note reentry checks differ')
        open_friends(t,'fixture.friend_note.persist_open');state,frame=t.observe('friend_note_persisted')
        rows=[r for r in packets.since(started) if r['name'] in ('SMSG_CONTACT_LIST','CMSG_SET_CONTACT_NOTES')]
        checks=contact_checks(rows);checks.update(native_note=social()==[[1,2,1,NOTE],[2,1,1,'']],
            public_note=public(state.get('friends'))==[{'name':FRIEND,'connected':False,'level':0,'notes':NOTE}],
            friends_ready=state.get('friends_ready') is True,stock_window='FriendsFrame' in state['panels'],
            no_lua_errors=not state.get('lua_errors'),no_blocked_actions=not state.get('blocked_actions'))
        row=target(t,'friends.note_persist.hover',lambda c:c['kind']=='Button' and
            c['name'].startswith('FriendsFrameFriendsScrollFrameButton') and c['text']==FRIEND)
        t.execute({'kind':'hover','value':point(row)});time.sleep(1)
        rendered,rendered_frame=t.observe('friend_note_persisted_rendered');t.execute({'kind':'hover','value':[1000,360]})
        t.receipt['cases'].append({'id':'friends.note_persist','selected':'ordinary_reentry',
            'status':'friend_note_persistence_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'error':None,'oracle':{'checks':checks,'packets':rows},'after':state,'after_frame':frame,
            'rendered':rendered,'rendered_frame':rendered_frame});t.persist()
        if not all(checks.values()):raise RuntimeError('owned note did not persist from native contacts')
    finally:
        if entered:cleanup_note(t,packets,probe,original)
        else:t.receipt['cleanup_requires_reviewed_reentry']=True;t.persist()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=['prepare','finish'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--review',type=Path);a=p.parse_args()
    if (a.phase=='finish')!=bool(a.review):p.error('only finish requires an actual fresh selection review')
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        try:
            (prepare(t,a.source) if a.phase=='prepare' else finish(t,a.source,a.review));t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure')}),flush=True)


if __name__=='__main__':main()
