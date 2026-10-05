"""Observe owned peer joins/leaves in the already selected stock channel roster."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_chat_channels import run,member,packets
from .interaction_channel_ui import inspect
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_keybindings_native import suite as native_suite
from .interaction_macros import require
from .observation.journal import Cursor


def roster(t,name,label,expected):
    public=detail(t,label)
    rows=[r for r in public.get('channel_list',{}).get('roster',{}).get('channels',[]) if r['name']==name]
    members=rows[0].get('members',[]) if len(rows)==1 else []
    checks={'one_owned_channel':len(rows)==1,'member_names':sorted(r['name'] for r in members)==sorted(expected),
        'owned_member_guids':sorted(r['guid'] for r in members)==sorted('Player-1-0000000'+str(g) for g in expected.values()),
        'primary_owner':any(r['name']=='Harnessone' and r['owner'] is True for r in members)}
    state,frame=t.observe(label+'_rendered')
    checks.update(stock_panel_visible='ChannelFrame' in state['panels'],clean=not state.get('lua_errors') and not state.get('blocked_actions'))
    return {'checks':checks,'public':public,'state':state,'frame':frame}


def peer(t,name,on_join):
    before=detail(t,'peer_channel_original');session=actors.session_entry(t.fixture)['session']
    if member(before,name):raise RuntimeError('peer already belongs to the disposable channel')
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for p in cursor.poll():pass
    started=time.time();t.receipt.update(owned_channel_name=name,channel_baseline=before,channel_session=session);t.persist()
    try:
        def joined(b,a,s):
            public=detail(t,'peer_join_result');wire=packets(cursor,session,name,started)
            expected={('from_client','CMSG_CHAT_JOIN_CHANNEL'),('to_native','CMSG_JOIN_CHANNEL'),
                ('from_native','SMSG_CHANNEL_NOTIFY'),('to_client','SMSG_CHANNEL_NOTIFY_JOINED')}
            checks={'ordinary_join':s=='join','public_membership':len(member(public,name))==1 and not member(public,name)[0]['disabled'],
                'native_join_roundtrip':expected.issubset({(p['direction'],p['name']) for p in wire}),
                'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'owned_peer_channel_join_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':public,'packets':wire}}
        require(t.step('fixture.peer_channel_join','Join the exact primary-owned disposable channel.',
            {'join':{'kind':'chat','value':'/join '+name}},joined,diagnostic_action='join'),'owned_peer_channel_join_pass')
        on_join()
    finally:
        t.clean_panels();current=detail(t,'peer_cleanup_guard')
        if member(current,name):
            require(t.step('fixture.peer_channel_leave','Leave only the exact shared disposable channel.',
                {'leave':{'kind':'chat','value':'/leave '+name}},
                lambda b,a,s:{'status':'owned_channel_left' if not member(detail(t,'peer_left'),name) else 'client_or_protocol_failure'},
                diagnostic_action='leave'),'owned_channel_left')
        after=detail(t,'peer_channels_restored');checks={'original_channel_membership':after['channels']==before['channels'],
            'original_chat_settings':signature(after)==signature(before)}
        t.receipt['channel_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('peer channel/chat restoration differs')


def suite(out):
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    report={'schema':'client442_channel_peer_v1','completed':False,'failure':None,'started_at':time.time()}
    with actor('primary'):
        primary=Trial(out/'primary',controller='code')
        def shared(t,name):
            inspect(t,name,'ChatFrameChannelButton',True)
            primary_session=actors.session_entry(t.fixture)['session'];cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
            for p in cursor.poll():pass
            started=time.time()
            def check_join():
                with actor('primary'):
                    evidence=roster(primary,name,'peer_join_live_roster',{'Harnessone':1,'Harnesstwo':2})
                    evidence['packets']=packets(cursor,primary_session,name,started)
                    primary.receipt['peer_join_live_roster']=evidence;primary.persist()
                    if not all(evidence['checks'].values()):raise RuntimeError('selected roster did not reflect owned peer join')
            with actor('scout'):
                scout=Trial(out/'scout',controller='code')
                try:
                    native_suite(scout,operations=lambda s:peer(s,name,check_join),preserve_settings=False)
                    scout.receipt['completed']=True
                except Exception as error:scout.receipt['failure']=f'{type(error).__name__}: {error}';raise
                finally:scout.receipt['finished_at']=time.time();scout.persist()
            evidence=roster(primary,name,'peer_leave_live_roster',{'Harnessone':1})
            evidence['packets']=packets(cursor,primary_session,name,started)
            primary.receipt['peer_leave_live_roster']=evidence;primary.persist()
            if not all(evidence['checks'].values()):raise RuntimeError('selected roster did not reflect owned peer leave')
        try:
            native_suite(primary,operations=lambda t:run(t,on_join=shared),preserve_settings=False)
            primary.receipt['completed']=True;report['completed']=True
        except Exception as error:
            primary.receipt['failure']=report['failure']=f'{type(error).__name__}: {error}'
        finally:
            primary.receipt['finished_at']=report['finished_at']=time.time();primary.persist()
            lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output)
