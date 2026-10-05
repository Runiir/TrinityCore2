"""Reply to one exact owned incoming whisper and verify both native deliveries."""
import argparse,hashlib,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_keybindings_native import suite as native_suite
from .interaction_actionbar_pages import detail as bindings
from .interaction_macros import require
from .observation.journal import entries,Cursor
from .interaction_observation import read_current_page


def pending(state,target,token,command=None):
    focused=state.get('chat_edit_open') and state.get('chat_edit_focused')
    addressed=state.get('chat_edit_type')=='WHISPER' and state.get('chat_edit_target')==target
    text=state.get('chat_edit_text')
    return bool(focused and ((addressed and text==token) or (command is not None and text==command)))


class WhisperTrial(Trial):
    def execute(self,action):
        if action['kind']!='chat' or not action['value'].startswith('/w '):return super().execute(action)
        match=re.fullmatch(r'/w (Harnessone|Harnesstwo) (TC442UI:reply_seed_[0-9a-f]{8})',action['value'])
        if not match:raise ValueError('whisper transport accepts only its exact owned seed marker')
        target,token=match.groups()
        with owned_input.lease():
            before,_=self.observe('seed_chat_before')
            if before.get('observer_version',0)<83 or before.get('chat_edit_open'):
                raise RuntimeError('requires observer83 and a closed owned chat box')
            self.io.key('Return',hold=1.2);time.sleep(.2)
            opened,frame=read_current_page(self,'seed_chat_open','state',lambda s:
                s.get('chat_edit_open') and s.get('chat_edit_focused'))
            if not opened.get('chat_edit_open') or not opened.get('chat_edit_focused'):
                raise RuntimeError('owned seed chat did not gain keyboard focus')
            self.io.type(action['value']);time.sleep(.2)
            state,frame=read_current_page(self,'seed_chat_pending','state',lambda s:
                pending(s,target,token,action['value']))
            exact=pending(state,target,token,action['value'])
            guard={'frame':frame,'selected_command':action['value'],'expected_target':target,
                'expected_token':token,'observed_text':state.get('chat_edit_text'),
                'observed_target':state.get('chat_edit_target'),'observed_type':state.get('chat_edit_type'),
                'exact':exact,'submitted':False}
            self.receipt.setdefault('owned_whisper_guards',[]).append(guard);self.persist()
            if not exact:raise RuntimeError('owned whisper text or target differs; refusing submission')
            self.io.key('Return',hold=1.2);guard['submitted']=True;self.persist();time.sleep(.8)
            after,frame=read_current_page(self,'seed_chat_submitted','state',lambda s:not s.get('chat_edit_open'))
            guard['after_frame']=frame;self.persist()
            if after.get('chat_edit_open'):raise RuntimeError('owned seed remained pending; refusing input replay')
            return []


def delivered(t,session,since,token,event,label,expected_guid,request=False,packet_rows=None):
    state,frame=t.observe(label,seconds=60);rows=[]
    visible=[r for r in state.get('chat_probes',[]) if r['text']==token and r['event']==event]
    authors=[]
    for row in entries(lab.ROOT/'evidence/world_packets.jsonl') if packet_rows is None else packet_rows:
        if row.get('session')!=session or row.get('time',0)<since:continue
        body=bytes.fromhex(row.get('body',''))
        if token.encode() not in body:continue
        rows.append({k:row[k] for k in ['time','direction','name']})
        if (row.get('session')==session and row.get('time',0)>=since and row.get('direction')=='from_native' and
                row.get('name')=='SMSG_MESSAGECHAT'):
            if token.encode() in body and len(body)>=13:authors.append(int.from_bytes(body[5:13],'little'))
    checks={'native_delivery':any(r['direction']=='from_native' and r['name']=='SMSG_MESSAGECHAT' for r in rows),
        'public_message':len(visible)==1,'exact_native_chat_guid':bool(authors) and all(a==expected_guid for a in authors),
        'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    if request:checks['ordinary_request']=any(r['direction']=='from_client' and r['name']=='CMSG_CHAT_MESSAGE_WHISPER' for r in rows)
    record={'token':token,'checks':checks,'packets':rows,'frame':frame,
        'native_chat_guids':authors,'expected_native_guid':expected_guid,
        'native_guid_role':'recipient_in_inform' if event=='CHAT_MSG_WHISPER_INFORM' else 'incoming_sender',
        'observed_sender':visible[0]['sender'] if visible else None}
    t.receipt.setdefault('reply_deliveries',[]).append(record);t.persist()
    if not all(checks.values()):raise RuntimeError('owned whisper delivery differs: '+label)
    return record


def phase(primary,scout,seed_only=False,after_seed=None):
    sessions={}
    for name,t in [('primary',primary),('scout',scout)]:
        with actor(name):
            state,_=t.observe('reply_owned_fixture')
            if (state['player']!=('Harnessone' if name=='primary' else 'Harnesstwo') or
                state.get('observer_version',0)<83 or state.get('chat_edit_open')):
                raise RuntimeError('reply cohort is not the exact owned closed-chat fixture')
            sessions[name]=actors.session_entry(t.fixture)['session']
    nonce=hashlib.sha256(str(primary.out.parent).encode()).hexdigest()[:8]
    seed='TC442UI:reply_seed_'+nonce;reply='TC442UI:reply_'+nonce
    cursor=None;fresh=None
    if seed_only:
        cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
        for row in cursor.poll():pass
    started=time.time()
    with actor('scout'):
        scout.execute({'kind':'chat','value':'/w Harnessone '+seed})
        if cursor:
            fresh=[]
            for row in cursor.poll():
                if row.get('time',0)>=started and seed.encode() in bytes.fromhex(row.get('body','')):
                    fresh.append(row)
                    if len(fresh)>32:raise RuntimeError('owned seed packet count exceeds bound')
        delivered(scout,sessions['scout'],started,seed,'CHAT_MSG_WHISPER_INFORM','seed_sent',expected_guid=1,
            request=True,packet_rows=fresh)
    with actor('primary'):
        received_seed=delivered(primary,sessions['primary'],started,seed,'CHAT_MSG_WHISPER','seed_received',expected_guid=2,
            packet_rows=fresh)
        if seed_only:
            primary.receipt['player_link_seed']=received_seed
            primary.receipt['cases'].append({'id':'fixture.player_link_seed','status':'owned_peer_chat_seed_pass',
                'time':time.time(),'oracle':{'received':received_seed}});primary.persist()
            if after_seed:after_seed(primary,scout,received_seed)
            return
        destination=received_seed['observed_sender']
        if not isinstance(destination,str) or destination.split('-',1)[0]!=scout.fixture['character_name']:
            raise RuntimeError('native-attributed incoming sender does not name the owned scout')
        detail=bindings(primary,'reply_installed_binding');keys=detail['keys'].get('REPLY') or []
        if not keys:raise RuntimeError('installed Chat Reply binding is absent')
        require(primary.step('chat.reply_open','Open reply to the exact owned incoming whisper.',
            {'reply':{'kind':'key','value':binding_key(keys[0]),'hold':.4,'description':'Press the observed stock Chat Reply binding.'}},
            lambda b,a,s:{'status':'owned_reply_open' if s=='reply' and pending(a,destination,'') else
                'client_or_protocol_failure'},diagnostic_action='reply'),'owned_reply_open')
        state,frame=primary.observe('reply_before_typing')
        if not pending(state,destination,''):raise RuntimeError('owned reply focus or destination differs')
        primary.io.type(reply);time.sleep(.2);deadline=time.monotonic()+12
        while True:
            state,frame=primary.observe('reply_pending')
            primary.receipt.setdefault('reply_text_settling',[]).append({'frame':frame,
                'observed_text':state.get('chat_edit_text'),'input_replayed':False});primary.persist()
            if pending(state,destination,reply):break
            text=state.get('chat_edit_text')
            if (not state.get('chat_edit_open') or not state.get('chat_edit_focused') or
                    state.get('chat_edit_type')!='WHISPER' or state.get('chat_edit_target')!=destination or
                    not isinstance(text,str) or not reply.startswith(text)):
                raise RuntimeError('reply focus, recipient or text differs while settling; refusing submission')
            if time.monotonic()>deadline:raise RuntimeError('owned reply text did not settle; refusing input replay')
            time.sleep(.2)
        exact=pending(state,destination,reply)
        guard={'frame':frame,'target':destination,'token':reply,'exact':exact,'submitted':False,
            'destination_source':received_seed}
        primary.receipt['reply_submission_guard']=guard;primary.persist()
        if not exact:raise RuntimeError('exact owned reply text or destination differs; refusing submission')
        started=time.time();primary.io.key('Return',hold=.4);guard['submitted']=True;primary.persist();time.sleep(.8)
        sent=delivered(primary,sessions['primary'],started,reply,'CHAT_MSG_WHISPER_INFORM','reply_sent',expected_guid=2,request=True)
    with actor('scout'):
        received=delivered(scout,sessions['scout'],started,reply,'CHAT_MSG_WHISPER','reply_received',expected_guid=1)
    primary.receipt['cases'].append({'id':'chat.reply','status':'owned_reply_delivery_pass','time':time.time(),
        'oracle':{'sent':sent,'received':received,'exact_target_guard':guard}});primary.persist()


def run(out,seed_only=False,after_seed=None):
    out.mkdir(mode=0o700,parents=True,exist_ok=False);trials={};report={'completed':False,'failure':None}
    try:
        for name in ['primary','scout']:
            with actor(name):trials[name]=WhisperTrial(out/name,controller='code')
        def primary_work(t):
            with actor('scout'):
                native_suite(trials['scout'],operations=lambda peer:phase(t,peer,seed_only,after_seed),preserve_settings=False)
        with actor('primary'):native_suite(trials['primary'],operations=primary_work,preserve_settings=False)
        report['completed']=True
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}'
    finally:
        for t in trials.values():
            t.receipt.update(completed=report['completed'],failure=report['failure'],finished_at=time.time());t.persist()
        report['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seed-only',action='store_true',help='Prepare one attributable owned player chat link without a reply action')
    a=p.parse_args();run(a.output,a.seed_only)
