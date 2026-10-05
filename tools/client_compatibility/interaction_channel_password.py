"""Set/clear one disposable native channel password and verify owned peer gates."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_chat_channels import run,member,packets
from .interaction_channel_ui import inspect
from .interaction_channel_peer import roster
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_keybindings_native import suite as native_suite
from .interaction_macros import require
from .observation.journal import Cursor
from .world.buffer import Reader,player_high

PASSWORD='TC442TestPass1'


def terminated(r):
    value=bytearray()
    while (c:=r.raw(1))!=b'\0':value.extend(c)
    return value.decode()


def notice(rows,name,kind,guid):
    decoded=[]
    for row in rows:
        if row['name']!='SMSG_CHANNEL_NOTIFY' or row['direction'] not in ['from_native','to_client']:continue
        r=Reader(bytes.fromhex(row['body']));native=row['direction']=='from_native'
        value=r.unpack('B')[0] if native else r.bits(6)
        if value!=kind:continue
        if native:
            channel=terminated(r);sender=r.unpack('Q')[0] if kind==7 else 0
        else:
            size=r.bits(7);sender_size=r.bits(6);sender,high=r.guid();account=r.guid();realm=r.unpack('I')[0]
            target=r.guid();target_realm,channel_id=r.unpack('II');channel=r.raw(size).decode();r.raw(sender_size)
            assert high==(player_high() if guid else 0) and account==target==(0,0)
            assert realm==target_realm==0x01010001 and channel_id==0 and sender_size==0
        r.end();decoded.append({'direction':row['direction'],'kind':value,'channel':channel,'sender':sender})
    return {'decoded':decoded,'matches':{r['direction'] for r in decoded if r['channel']==name and r['sender']==guid}=={'from_native','to_client'}}


def change(t,name,password,label):
    before=detail(t,label+'_before');session=actors.session_entry(t.fixture)['session']
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for p in cursor.poll():pass
    started=time.time()
    def changed(b,a,s):
        after=detail(t,label+'_after');wire=packets(cursor,session,name,started)
        decoded=notice(wire,name,7,t.fixture['guid'])
        checks={'ordinary_password_command':s=='submit','native_password_changed':decoded['matches'],
            'same_enabled_membership':member(before,name)==member(after,name) and bool(member(after,name)) and not member(after,name)[0]['disabled'],
            'new_general_line':after['windows'][0]['message_count']>before['windows'][0]['message_count'],
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        for direction,width in [('from_client',7),('to_native',8)]:
            requests=[p for p in wire if p['direction']==direction and p['name']=='CMSG_CHAT_CHANNEL_PASSWORD']
            valid=False
            for p in requests:
                r=Reader(bytes.fromhex(p['body']));size,pass_size=r.bits(width),r.bits(7)
                channel,value=r.raw(size).decode(),r.raw(pass_size).decode();r.end()
                valid=valid or (channel==name and value==password)
            checks[direction+'_exact_password']=valid
        return {'status':'owned_native_password_changed' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':after,'packets':wire,'notification':decoded}}
    require(t.step('chat.channel_password','Change only the exact disposable owned channel password.',
        {'submit':{'kind':'chat','value':'/password '+name+(' '+password if password else '')}},
        changed,diagnostic_action='submit'),'owned_native_password_changed')
    state,frame=t.observe(label+'_rendered');t.receipt.setdefault('password_rendered',{})[label]={'state':state,'frame':frame};t.persist()


def join(t,name,password,rejected=False):
    before=detail(t,'password_join_before');session=actors.session_entry(t.fixture)['session']
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for p in cursor.poll():pass
    started=time.time()
    def result(b,a,s):
        after=detail(t,'password_join_result');wire=packets(cursor,session,name,started);rows=member(after,name)
        expected={('from_client','CMSG_CHAT_JOIN_CHANNEL'),('to_native','CMSG_JOIN_CHANNEL')}
        checks={'ordinary_join':s=='join','native_join_request':expected.issubset({(p['direction'],p['name']) for p in wire}),
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        if rejected:
            decoded=notice(wire,name,4,0);checks.update(native_wrong_password=decoded['matches'],
                no_enabled_membership=not any(not r['disabled'] for r in rows),
                new_general_line=after['windows'][0]['message_count']>before['windows'][0]['message_count'])
        else:
            decoded={};checks.update(public_enabled_membership=len(rows)==1 and not rows[0]['disabled'],
                native_join_response=any(p['direction']=='from_native' and p['name']=='SMSG_CHANNEL_NOTIFY' and bytes.fromhex(p['body'])[0]==2 for p in wire),
                modern_join_response=any(p['direction']=='to_client' and p['name']=='SMSG_CHANNEL_NOTIFY_JOINED' for p in wire))
        return {'status':('owned_password_rejection_pass' if rejected else 'owned_password_join_pass') if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':after,'packets':wire,'rejection':decoded,'password_case':'absent' if not password else 'public_disposable'}}
    status='owned_password_rejection_pass' if rejected else 'owned_password_join_pass'
    require(t.step('fixture.reject_without_password' if rejected else 'fixture.join_with_disposable_password' if password else 'fixture.join_after_password_clear',
        'Exercise the native password gate using only the owned peer.',
        {'join':{'kind':'chat','value':'/join '+name+(' '+password if password else '')}},result,diagnostic_action='join'),status)
    state,frame=t.observe(('password_rejected' if rejected else 'password_joined')+'_rendered')
    t.receipt.setdefault('password_gate_rendered',[]).append({'state':state,'frame':frame});t.persist()


def leave(t,name,label):
    require(t.step(label,'Leave only the exact disposable shared channel.',
        {'leave':{'kind':'chat','value':'/leave '+name}},
        lambda b,a,s:{'status':'owned_channel_left' if not member(detail(t,label+'_result'),name) else 'client_or_protocol_failure'},
        diagnostic_action='leave'),'owned_channel_left')


def suite(out):
    out.mkdir(mode=0o700,parents=True,exist_ok=False);report={'schema':'client442_channel_password_v1','completed':False,'failure':None,'started_at':time.time()}
    with actor('primary'):
        primary=Trial(out/'primary',controller='code')
        def shared(t,name):
            inspect(t,name,'ChatFrameChannelButton',True);cleared=False;attempted=False
            def primary_roster(label,expected):
                with actor('primary'):
                    evidence=roster(primary,name,label,expected);primary.receipt.setdefault('password_peer_rosters',{})[label]=evidence;primary.persist()
                    if not all(evidence['checks'].values()):raise RuntimeError('owned password peer roster differs')
            try:
                attempted=True;change(primary,name,PASSWORD,'password_set')
                with actor('scout'):
                    scout=Trial(out/'scout',controller='code')
                    def gates(s):
                        nonlocal cleared
                        before=detail(s,'password_peer_original');s.receipt.update(channel_baseline=before,owned_channel_name=name);s.persist()
                        if member(before,name):raise RuntimeError('password peer already belongs to the disposable channel')
                        try:
                            join(s,name,'',True);join(s,name,PASSWORD)
                            primary_roster('password_correct_roster',{'Harnessone':1,'Harnesstwo':2})
                            leave(s,name,'fixture.peer_leave_password_channel')
                            with actor('primary'):change(primary,name,'','password_clear');cleared=True
                            join(s,name,'');primary_roster('password_cleared_roster',{'Harnessone':1,'Harnesstwo':2})
                        finally:
                            s.clean_panels()
                            if member(detail(s,'password_peer_cleanup_guard'),name):leave(s,name,'fixture.peer_password_cleanup')
                            after=detail(s,'password_peer_restored');checks={'original_channel_membership':after['channels']==before['channels'],
                                'original_chat_settings':signature(after)==signature(before)}
                            s.receipt['channel_restoration']={'checks':checks,'public':after};s.persist()
                            if not all(checks.values()):raise RuntimeError('password peer channel/chat restoration differs')
                    try:native_suite(scout,operations=gates,preserve_settings=False);scout.receipt['completed']=True
                    except Exception as error:scout.receipt['failure']=f'{type(error).__name__}: {error}';raise
                    finally:scout.receipt['finished_at']=time.time();scout.persist()
                primary_roster('password_peer_left_roster',{'Harnessone':1})
            finally:
                if attempted and not cleared:change(primary,name,'','password_failure_clear')
        try:native_suite(primary,operations=lambda t:run(t,on_join=shared),preserve_settings=False);primary.receipt['completed']=report['completed']=True
        except Exception as error:primary.receipt['failure']=report['failure']=f'{type(error).__name__}: {error}'
        finally:
            primary.receipt['finished_at']=report['finished_at']=time.time();primary.persist()
            lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);suite(p.parse_args().output)
