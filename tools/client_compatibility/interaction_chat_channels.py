"""Probe one owned stock channel join and restore only its exact membership."""
import argparse,hashlib,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_macros import require
from .observation.journal import latest,Cursor


def member(probe,name):
    return [r for r in probe['channels']['rows'] if r['name']==name]


def packets(cursor,session,name,started):
    return [{'name':p['name'],'direction':p['direction'],'time':p['time'],'body':p['body']}
        for p in cursor.poll() if p.get('session')==session and p.get('time',0)>=started and
        name.encode() in bytes.fromhex(p.get('body',''))]


def restore_failed(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
        raise ValueError('requires an owned channel failure receipt')
    old=json.loads(source.read_text());name=old['owned_channel_name']
    if (old.get('completed') or not old.get('finished_at') or old['actor']!=t.fixture or
            not all(old['native_restoration']['checks'].values()) or
            old['failure']!='RuntimeError: operation did not advance: fixture.leave_owned_channel client_or_protocol_failure'):
        raise RuntimeError('closed failed channel source differs')
    current=detail(t,'failed_channel_cleanup_guard')
    if len(member(current,name))>1:raise RuntimeError('exact failed channel entry is ambiguous')
    t.receipt['channel_cleanup_source']={'file':str(source),'sha256':lab.sha256(source),'name':name};t.persist()
    if member(current,name):
        require(t.step('fixture.leave_failed_owned_channel','Remove only the source-attributed disposable channel.',
            {'leave':{'kind':'chat','value':'/leave '+name,'description':'Leave the exact prior owned channel.'}},
            lambda b,a,s:{'status':'owned_channel_left' if not member(detail(t,'failed_owned_channel_left'),name)
                else 'client_or_protocol_failure'},diagnostic_action='leave'),'owned_channel_left')
    else:
        t.receipt['channel_cleanup_source']['already_absent_after_reentry']=True;t.persist()
    after=detail(t,'failed_channel_cleanup_restored')
    # Enabling the formerly dropped built-in joins is part of the bridge repair.
    original=old['channel_baseline']['channels']['rows']
    checks={'original_channel_names':[(r['id'],r['name']) for r in after['channels']['rows']]==
        [(r['id'],r['name']) for r in original],'original_chat_settings':signature(after)==signature(old['channel_baseline'])}
    t.receipt['channel_restoration']={'checks':checks,'public':after};t.persist()
    if not all(checks.values()):raise RuntimeError('prior owned channel cleanup differs')


def run(t,on_join=None):
    before=detail(t,'channel_join_original')
    name='TC442UIChannel'+hashlib.sha256(str(t.out).encode()).hexdigest()[:8]
    if before['selected']!=1 or not before['channels']['available'] or member(before,name):
        raise RuntimeError('requires original General and complete public channels without the owned name')
    session=actors.session_entry(t.fixture)['session'];started=time.time()
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for p in cursor.poll():pass
    t.receipt.update(channel_baseline=before,owned_channel_name=name,channel_session=session);t.persist()
    try:
        def joined(b,a,s):
            after=detail(t,'owned_channel_join_result')
            unmapped=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
                r.get('time',0)>=started and r.get('event')=='unmapped_client_packet' and
                r.get('name')=='CMSG_CHAT_JOIN_CHANNEL')
            observed=packets(cursor,session,name,started)
            expected={('from_client','CMSG_CHAT_JOIN_CHANNEL'),('to_native','CMSG_JOIN_CHANNEL'),
                ('from_native','SMSG_CHANNEL_NOTIFY'),('to_client','SMSG_CHANNEL_NOTIFY_JOINED')}
            checks={'ordinary_join':s=='join','public_membership':len(member(after,name))==1 and
                member(after,name)[0]['disabled'] is False,'translation_present':unmapped is None,
                'native_join_roundtrip':expected.issubset({(p['direction'],p['name']) for p in observed}),
                'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'owned_channel_join_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':after,'unmapped_request':unmapped,'packets':observed}}
        require(t.step('chat.channel_join','Join only the exact disposable channel through ordinary slash input.',
            {'join':{'kind':'chat','value':'/join '+name,'description':'Join the exact owned disposable channel.'}},
            joined,diagnostic_action='join'),'owned_channel_join_pass')
        state,frame=t.observe('owned_channel_join_rendered');t.receipt['channel_rendered']={'state':state,'frame':frame};t.persist()
        if on_join:on_join(t,name)
    finally:
        t.clean_panels();current=detail(t,'owned_channel_cleanup_guard')
        if member(current,name):
            require(t.step('fixture.leave_owned_channel','Leave only the exact channel created by this trial.',
                {'leave':{'kind':'chat','value':'/leave '+name,'description':'Leave only the owned disposable channel.'}},
                lambda b,a,s:{'status':'owned_channel_left' if s=='leave' and not member(detail(t,'owned_channel_left'),name)
                    else 'client_or_protocol_failure'},diagnostic_action='leave'),'owned_channel_left')
        after=detail(t,'owned_channel_restored')
        checks={'original_channel_membership':after['channels']==before['channels'],
            'original_chat_settings':signature(after)==signature(before)}
        t.receipt['channel_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('original channel or chat settings differ')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cleanup-source',type=Path);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:
        native_suite(t,operations=(lambda t:restore_failed(t,a.cleanup_source)) if a.cleanup_source else run,preserve_settings=False)
        t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
