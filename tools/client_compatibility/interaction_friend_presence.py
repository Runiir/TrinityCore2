"""Enter the owned parked scout, verify friend presence and whisper, then park it."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_friend_notes import baseline
from .interaction_friends import social,public,open_friends,close_friends,restored,canonical,HIGH
from .interaction_parked_bridge import native as parked_native,review as parked_review
from .interaction_bridge_restoration import capture,restore
from .interaction_owned_language_fixture import logout
from .interaction_bridge_deploy import shot
from .interaction_lifecycle import Packets
from .interaction_chat_window import detail as chat_detail
from .interaction_chat_settings import signature
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_spellbook_professions import skills
from .interaction_quest_link import saved as quests
from .interaction_ground_movement import position
from .interaction_friend_whisper import send,pending
from .world.buffer import Reader

FRIEND='Harnesstwo'
STABLE=('guid','account','name','race','class','gender','level','money','map','zone',
    'position_x','position_y','position_z','orientation')


def source_matches(old,current):
    return (old.get('completed') is True and old.get('failure') is None and bool(old.get('finished_at')) and
        old.get('actor')==current.get('actor') and old.get('runtime')==current.get('runtime') and
        old.get('actor',{}).get('guid')==2 and old.get('parked_native',{}).get('online')==0 and
        old.get('parked_native',{}).get('name')==FRIEND and old.get('parked_native',{}).get('level')==1 and
        old.get('qualified_scope','').startswith('Read-only owned offline scout preflight'))


def wire_checks(rows,connected,area=12):
    result=2 if connected else 3;native=[];modern=[]
    for row in rows:
        if row['name']!='SMSG_FRIEND_STATUS':continue
        body=bytes.fromhex(row['body'])
        if not body or body[0]!=result:continue
        if row['direction']=='from_native':native.append(body)
        elif row['direction']=='to_client':
            r=Reader(body);status=r.unpack('B')[0];guid=r.guid();account=r.guid()
            realm,online,zone,level,klass=r.unpack('IBIII');note=r.raw(r.bits(10)).decode();r.end()
            modern.append((status,guid,account,realm,online,zone,level,klass,note))
    expected=struct.pack('<BQ',result,2)+(struct.pack('<BIII',1,area,1,1) if connected else b'')
    return {'exact_native_presence':native==[expected],
        'exact_modern_presence':modern==[(result,(2,HIGH),(0,0),1,int(connected),area if connected else 0,
            1 if connected else 0,1 if connected else 0,'')]}


def presence(t,packets,started,connected,area):
    label='friend_online' if connected else 'friend_offline';state,frame=t.observe(label,seconds=60)
    rows=[r for r in packets.since(started) if r['name']=='SMSG_FRIEND_STATUS']
    checks=wire_checks(rows,connected,area);checks.update(public_presence=public(state.get('friends'))==[
        {'name':FRIEND,'connected':connected,'level':1 if connected else 0,'notes':''}],
        friends_ready=state.get('friends_ready') is True,stock_window='FriendsFrame' in state['panels'],
        native_social=social()==t.receipt['original_social'],group=state['group']==t.receipt['original_group'],
        chat_closed=not state.get('chat_edit_open'),no_lua_errors=not state.get('lua_errors'),
        no_blocked_actions=not state.get('blocked_actions'))
    t.receipt['cases'].append({'id':'friends.online_presence' if connected else 'fixture.friend_offline_transition',
        'status':'owned_friend_presence_pass' if all(checks.values()) else 'client_or_protocol_failure',
        'time':time.time(),'oracle':{'checks':checks,'packets':rows},'after':state,'after_frame':frame});t.persist()
    if not all(checks.values()):raise RuntimeError('owned friend presence transition differs')


def online(t):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT online FROM client442_characters.characters WHERE guid=%s AND account=%s',
            (t.fixture['guid'],t.fixture['account_id']));row=q.fetchone()
    if row is None:raise RuntimeError('owned character is absent')
    return row[0]


def original_position(current,row):
    expected=[row[k] for k in ('position_x','position_y','position_z','orientation','map')]
    return len(current)==5 and current[4]==expected[4] and all(abs(a-b)<.001 for a,b in zip(current[:4],expected[:4]))


def park(s,old,original_peer):
    errors=[]
    try:
        if 'native_baseline' in s.receipt:
            s.clean_panels();restore(s,s.receipt['native_baseline'])
            if 'original_chat' in s.receipt:
                after=chat_detail(s,'friend_presence_scout_chat_restored')
                checks={'original_chat_settings':signature(after)==signature(s.receipt['original_chat'])}
                s.receipt['chat_restoration']={'checks':checks};s.persist()
                if not all(checks.values()):raise RuntimeError('original scout chat settings differ')
        else:
            state,frame=s.observe('failed_entry_cleanup_guard',seconds=240)
            if state.get('guid')!=s.guid or state.get('player')!=FRIEND or state.get('level')!=1:
                raise RuntimeError('failed entry cleanup lacks the exact owned scout')
            s.receipt['failed_entry_cleanup']={'frame':frame,'scope':'Ordinary logout only; no qualification.'};s.persist()
    except Exception as error:errors.append(f'{type(error).__name__}: {error}')
    # Parking is necessary even if a read-only restoration comparison failed.
    stopped=time.time();logout(s);s.receipt['parked_frame']=shot(s.out/'scout_parked_after.png')
    current=parked_native(s);checks={k:current[k]==old['parked_native'][k] for k in STABLE}
    checks.update(spells=known(2)==original_peer['spells'],actions=saved_actions(2)==original_peer['actions'],
        skills=skills(2)==original_peer['skills'],quests=quests(2)==original_peer['quests'],offline=current['online']==0)
    s.receipt.update(parked_after=current,parked_restoration={'checks':checks},
        natural_lifecycle_changes={k:{'before':old['parked_native'][k],'after':v} for k,v in current.items()
            if v!=old['parked_native'].get(k)});s.persist()
    if not all(checks.values()):errors.append('RuntimeError: original parked scout persistent fixture differs')
    return stopped,errors


def run(out,source,review):
    out=out.resolve();source=source.resolve();review=review.resolve()
    if not out.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires owned evidence and closed scout source')
    out.mkdir(parents=True,exist_ok=False,mode=0o700);trials={};report={'started_at':time.time(),'completed':False,'failure':None}
    entered=False;entry_started=None;packets={};original_peer=None
    try:
        for name in ['primary','scout']:
            with actor(name):trials[name]=Trial(out/name,controller='code',chat_key_hold=1.2)
        p,s=trials['primary'],trials['scout'];old=json.loads(source.read_text())
        with actor('scout'):
            if not source_matches(old,s.receipt) or parked_native(s)!=old['parked_native']:
                raise RuntimeError('closed parked scout source or native fixture differs')
            parked_review(s,review,source,'friend_presence_entry')
            original_peer={'spells':known(2),'actions':saved_actions(2),'skills':skills(2),'quests':quests(2)}
            s.receipt.update(source={'path':str(source),'sha256':lab.sha256(source)},parked_native=old['parked_native'],
                original_peer=original_peer,reviewed_selection={'path':str(review),'sha256':lab.sha256(review),
                    'frame':json.loads(review.read_text())['frame']},custom_script_permission='blocked_by_user');s.persist()
        with actor('primary'):
            baseline(p,123);p.receipt['original_chat']=chat_detail(p,'friend_presence_original_chat');p.persist()
            open_friends(p,'fixture.friend_presence.open');state,frame=p.observe('friend_presence_offline_original')
            if public(state.get('friends'))!=p.receipt['original_public_friends']:
                raise RuntimeError('original offline public friend differs')
            p.receipt['offline_before_frame']=frame;p.receipt['qualified_scope']=(
                'One owned friend offline-to-online transition and stock Send Message whisper; qualification requires final original offline fixture restoration.');p.persist()
            packets['primary']=Packets(p.receipt['session'])
        packets['scout']=Packets('_parked_no_world_session_')
        with actor('scout'):
            parked_review(s,review,source,'friend_presence_entry')
            available=int(Path('/proc/meminfo').read_text().split('MemAvailable:')[1].split()[0])
            if available<6*1024*1024:raise RuntimeError('owned scout entry requires at least6GiB available memory')
            s.receipt['mem_available_before_entry_kib']=available;s.receipt['entry_input']={'kind':'key','value':'Return','hold':1.2};s.persist()
            entry_started=time.time();s.execute(s.receipt['entry_input']);state,frame=s.observe('friend_presence_scout_entered',seconds=240)
            entered=True;session=actors.session_entry(s.fixture)['session'];packets['scout'].session=session
            rows=[r for r in packets['scout'].since(entry_started) if r['name'] in ('CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD')]
            checks={'owned_character':state.get('player')==FRIEND and state.get('level')==1 and state.get('guid')==s.guid,
                'observer_chat_capable':state.get('observer_version',0)>=83,'native_online':online(s)==1,
                'ordinary_login':any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in rows),
                'native_login':any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in rows),
                'spells':known(2)==original_peer['spells'],'actions':saved_actions(2)==original_peer['actions'],
                'skills':skills(2)==original_peer['skills'],'quests':quests(2)==original_peer['quests']}
            checks['position']=original_position(position(2),old['parked_native'])
            s.receipt.update(entry_checks=checks,entry_packets=rows,entry_frame=frame,session=session,
                native_baseline=canonical(capture(s)),original_chat=chat_detail(s,'friend_presence_scout_chat'),
                qualified_scope='Owned scout entry, peer whisper receipt and final parking only; no separate feature qualification.');s.persist()
            if not all(checks.values()):raise RuntimeError('owned scout entry differs from parked source')
        with actor('primary'):presence(p,packets['primary'],entry_started,True,old['parked_native']['zone'])
        send(p,s,packets)
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}'
    finally:
        cleanup_errors=[];stopped=None
        try:
            if entry_started is not None and online(trials['scout'])==1:
                p,s=trials['primary'],trials['scout']
                with actor('scout'):
                    stopped,errors=park(s,old,original_peer);cleanup_errors.extend(errors)
        except Exception as error:cleanup_errors.append(f'{type(error).__name__}: {error}')
        try:
            if stopped is not None:
                with actor('primary'):presence(trials['primary'],packets['primary'],stopped,False,old['parked_native']['zone'])
        except Exception as error:cleanup_errors.append(f'{type(error).__name__}: {error}')
        try:
            if 'primary' in trials and 'original_social' in trials['primary'].receipt:
                with actor('primary'):
                    p=trials['primary'];state,_=p.observe('friend_presence_pending_cleanup_guard')
                    if state.get('chat_edit_open'):
                        token=p.receipt.get('friend_whisper_guard',{}).get('token')
                        if not pending(state,'') and not (token and pending(state,token)):
                            raise RuntimeError('friend cleanup refuses unrelated pending chat')
                        p.execute({'kind':'key','value':'Escape','hold':1.2})
                    close_friends(p);restored(p,p.receipt)
                    if 'original_chat' in p.receipt:
                        current=chat_detail(p,'friend_presence_primary_chat_restored');checks={
                            'original_chat_settings':signature(current)==signature(p.receipt['original_chat'])}
                        p.receipt['chat_restoration']={'checks':checks};p.persist()
                        if not all(checks.values()):raise RuntimeError('original primary chat settings differ')
                    restore(p,p.receipt['native_baseline'])
        except Exception as error:cleanup_errors.append(f'{type(error).__name__}: {error}')
        if cleanup_errors:
            report['cleanup_failures']=cleanup_errors
            if report['failure'] is None:report['failure']=cleanup_errors[0]
        report['completed']=report['failure'] is None;report['finished_at']=time.time()
        for t in trials.values():t.receipt.update(completed=report['completed'],failure=report['failure'],finished_at=report['finished_at']);t.persist()
        lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-scout',type=Path,required=True);p.add_argument('--review',type=Path,required=True);a=p.parse_args()
    run(a.output,a.source_scout,a.review)
