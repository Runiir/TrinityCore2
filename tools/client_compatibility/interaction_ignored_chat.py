"""Compare owned whisper delivery before, during and after one stock Ignore flag."""
import argparse,hashlib,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_friend_presence import run
from .interaction_reply_chat import WhisperTrial,delivered
from .interaction_ignore import ignore_tab,ignore_rows,source_matches
from .interaction_ignore_friend import mutation,restore_ignore
from .interaction_operations import controls
from .interaction_chat_window import detail
from .world.buffer import Reader
from .interaction_friends import HIGH


def feedback_checks(rows):
    modern=[];native=[]
    for row in rows:
        body=bytes.fromhex(row.get('body',''))
        if row['name']=='CMSG_CHAT_REPORT_IGNORED' and row['direction']=='from_client':
            r=Reader(body);modern.append((r.guid(),r.unpack('B')[0]));r.end()
        elif row['name']=='CMSG_CHAT_IGNORED' and row['direction']=='to_native':native.append(body)
    # Modern pinned ChatReportIgnored::Read is packed GUID then Reason.
    # Native ChatHandler reads Reason, presence bits[5,2,6,4,7,0,1,3],
    # then XOR bytes[0,6,5,1,4,3,7,2]. Owned sender is exactly GUID2.
    return {'exact_modern_ignore_feedback':modern==[((2,HIGH),0)],
        'exact_native_ignore_feedback':native==[bytes([0,4,3])]}


def general_count(probe):
    if probe.get('selected')!=1 or not probe.get('message_types_available') or 'WHISPER' not in probe.get('message_types',[]):
        return None
    rows=[r for r in probe.get('windows',[]) if r.get('id')==1 and r.get('name')=='General' and r.get('frame_visible') is True]
    value=rows[0].get('message_count') if len(rows)==1 else None
    return value if type(value) is int and value>=0 else None


def negative_checks(primary_rows,scout_rows,token,states,before,after):
    native=[];modern=[];ignored=[];modern_ignored=[]
    for row in primary_rows:
        body=bytes.fromhex(row.get('body',''))
        if token.encode() not in body:continue
        if row['name']=='SMSG_MESSAGECHAT' and row['direction']=='from_native':native.append(body)
        elif row['name']=='SMSG_CHAT' and row['direction']=='to_client':modern.append(body)
    for row in scout_rows:
        body=bytes.fromhex(row.get('body',''))
        if body[:1]!=b'\x19':continue # Native SharedDefines CHAT_MSG_IGNORED.
        if row['name']=='SMSG_MESSAGECHAT' and row['direction']=='from_native':ignored.append(body)
        elif row['name']=='SMSG_CHAT' and row['direction']=='to_client':modern_ignored.append(body)
    checks=feedback_checks(primary_rows)
    checks.update(native_owned_whisper=(len(native)==1 and len(native[0])>=13 and native[0][0]==7 and
        int.from_bytes(native[0][5:13],'little')==2),modern_owned_whisper=len(modern)==1 and modern[0][:1]==b'\x07',
        no_public_whisper=(len(states)>=3 and all(not any(p.get('text')==token and
            p.get('event')=='CHAT_MSG_WHISPER' for p in s.get('chat_probes',[])) for s in states)),
        stable_general_count=general_count(before) is not None and general_count(before)==general_count(after),
        exact_native_ignore_notice=(len(ignored)==1 and len(ignored[0])>=13 and
            int.from_bytes(ignored[0][5:13],'little')==1 and b'Harnessone\0' in ignored[0]),
        modern_ignore_notice=len(modern_ignored)==1,
        clean_samples=(len(states)>=3 and all(not s.get('chat_edit_open') and
            not s.get('lua_errors') and not s.get('blocked_actions') for s in states)))
    return checks


def send_peer(primary,scout,packets,token,label,negative=False):
    started=time.time()
    with actor('scout'):
        scout.execute({'kind':'chat','value':'/w Harnessone '+token})
        sent=delivered(scout,actors.session_entry(scout.fixture)['session'],started,token,
            'CHAT_MSG_WHISPER_INFORM',label+'_sent',1,request=True,packet_rows=packets['scout'].since(started))
    if not negative:
        with actor('primary'):
            received=delivered(primary,actors.session_entry(primary.fixture)['session'],started,token,
                'CHAT_MSG_WHISPER',label+'_received',2,packet_rows=packets['primary'].since(started))
        return {'sent':sent,'received':received,'checks':{'sent':all(sent['checks'].values()),
            'received':all(received['checks'].values())}}
    return started,sent


def phase(primary,scout,packets,source):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned stock Ignore probe')
    probe=json.loads(source.read_text());outcomes={};error=None
    tokens={label:'TC442UI:reply_seed_'+hashlib.sha256((str(primary.out)+label).encode()).hexdigest()[:8]
        for label in ['before','ignored','after']}
    primary.receipt['ignored_chat_source']={'path':str(source),'sha256':lab.sha256(source)};primary.persist()
    try:
        with actor('primary'):
            if not source_matches(probe,primary.receipt):raise RuntimeError('current closed empty Ignore probe differs')
            ignore_tab(primary,'fixture.ignored_chat.tab')
            if ignore_rows(controls(primary)):raise RuntimeError('original stock Ignore list is not empty')
        outcomes['before']=send_peer(primary,scout,packets,tokens['before'],'ignored_chat_positive_before')
        with actor('primary'):
            mutation(primary,packets['primary'],'fixture.ignored_chat.add',probe)
            before=detail(primary,'ignored_chat_general_before')
        started,sent=send_peer(primary,scout,packets,tokens['ignored'],'ignored_chat_negative',negative=True)
        states=[];frames=[]
        with actor('primary'):
            for index in range(3):
                state,frame=primary.observe('ignored_chat_negative_sample_'+str(index),seconds=60)
                states.append(state);frames.append(frame)
                if index<2:time.sleep(1)
            after=detail(primary,'ignored_chat_general_after')
        rows=packets['primary'].since(started);peer=packets['scout'].since(started)
        checks=negative_checks(rows,peer,tokens['ignored'],states,before,after)
        outcomes['ignored']={'checks':checks,'sent':sent,'frames':frames,'states':states,
            'general_before':before,'general_after':after,
            'primary_packets':[r for r in rows if r['name'] in ('CMSG_CHAT_REPORT_IGNORED','CMSG_CHAT_IGNORED') or
                tokens['ignored'].encode() in bytes.fromhex(r.get('body',''))],
            'scout_packets':[r for r in peer if r['name']=='SMSG_MESSAGECHAT' and r['direction']=='from_native' and
                bytes.fromhex(r.get('body',''))[:1]==b'\x19' or r['name']=='SMSG_CHAT' and
                r['direction']=='to_client' and bytes.fromhex(r.get('body',''))[:1]==b'\x19']}
    except Exception as failure:error=f'{type(failure).__name__}: {failure}'
    finally:
        with actor('primary'):restore_ignore(primary,packets['primary'],probe)
    if outcomes.get('before'):
        try:outcomes['after']=send_peer(primary,scout,packets,tokens['after'],'ignored_chat_positive_after')
        except Exception as failure:error=f'{type(failure).__name__}: {failure}'
    passed=error is None and set(outcomes)=={'before','ignored','after'} and all(
        all(o['checks'].values()) for o in outcomes.values())
    primary.receipt['cases'].append({'id':'friends.ignored_chat','status':'owned_ignored_chat_pass' if passed else
        'client_or_protocol_failure','time':time.time(),'oracle':{'tokens':tokens,'outcomes':outcomes,'phase_failure':error}})
    primary.persist()
    if not passed:raise RuntimeError('owned ignored-chat outcomes differ')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-scout',type=Path,required=True);p.add_argument('--review',type=Path,required=True)
    p.add_argument('--source-probe',type=Path,required=True);a=p.parse_args()
    run(a.output,a.source_scout,a.review,trial_class=WhisperTrial,
        operations=lambda primary,scout,packets:phase(primary,scout,packets,a.source_probe))
