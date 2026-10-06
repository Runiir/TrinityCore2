"""Send one exact owned whisper using the stock Friends Send Message control."""
import hashlib,time
from . import actors,owned_input
from .interaction_social import actor
from .interaction_control_target import click,target
from .interaction_operations import controls
from .interaction_macros import require
from .interaction_reply_chat import delivered

FRIEND='Harnesstwo'


def pending(state,text):
    return bool(state.get('chat_edit_open') and state.get('chat_edit_focused') and
        state.get('chat_edit_type')=='WHISPER' and
        state.get('chat_edit_target') in (FRIEND,FRIEND+'-Client442Lab') and state.get('chat_edit_text')==text)


def send(primary,scout,packets):
    token='TC442UI:friend_'+hashlib.sha256(str(primary.out).encode()).hexdigest()[:8]
    with actor('primary'):
        row=target(primary,'fixture.friend_whisper.row',lambda c:c['kind']=='Button' and
            c['name'].startswith('FriendsFrameFriendsScrollFrameButton') and c['text']==FRIEND)
        require(click(primary,'fixture.friend_whisper.select','Select only the owned online friend row.',
            lambda c:c['name']==row['name'] and c['text']==FRIEND,lambda b,a,s:
            {'status':'friend_whisper_selected' if s and any(c['name']=='FriendsFrameSendMessageButton' and
                c['enabled'] for c in controls(primary)) else 'client_or_protocol_failure'}),'friend_whisper_selected')
        require(click(primary,'fixture.friend_whisper.open','Open the stock Send Message edit for the owned friend.',
            lambda c:c['name']=='FriendsFrameSendMessageButton' and c['text']=='Send Message',lambda b,a,s:
            {'status':'friend_whisper_open' if s and pending(a,'') else 'client_or_protocol_failure'},
            await_state=lambda a:pending(a,'')),'friend_whisper_open')
        with owned_input.lease():
            state,frame=primary.observe('friend_whisper_before_text')
            if not pending(state,''):raise RuntimeError('owned friend whisper focus or recipient differs')
            primary.io.type(token);time.sleep(.2)
            state,frame=primary.observe('friend_whisper_pending')
            guard={'frame':frame,'target':state.get('chat_edit_target'),'token':token,
                'exact':pending(state,token),'submitted':False,'input_replayed':False}
            primary.receipt['friend_whisper_guard']=guard;primary.persist()
            if not guard['exact']:raise RuntimeError('exact owned friend whisper text or target differs')
            started=time.time();primary.io.key('Return',hold=1.2);guard['submitted']=True;primary.persist()
        sent=delivered(primary,actors.session_entry(primary.fixture)['session'],started,token,
            'CHAT_MSG_WHISPER_INFORM','friend_whisper_sent',2,request=True,packet_rows=packets['primary'].since(started))
    with actor('scout'):
        received=delivered(scout,actors.session_entry(scout.fixture)['session'],started,token,
            'CHAT_MSG_WHISPER','friend_whisper_received',1,packet_rows=packets['scout'].since(started))
    checks={'exact_owned_pending_guard':guard['exact'],'ordinary_send':guard['submitted'],
        'sent_delivery':all(sent['checks'].values()),'received_delivery':all(received['checks'].values()),
        'modern_sender_echo':any(r['name']=='SMSG_CHAT' and r['direction']=='to_client' for r in sent['packets']),
        'modern_peer_delivery':any(r['name']=='SMSG_CHAT' and r['direction']=='to_client' for r in received['packets']),
        'owned_peer_sender':isinstance(received['observed_sender'],str) and
            received['observed_sender'].split('-',1)[0]=='Harnessone'}
    primary.receipt['cases'].append({'id':'friends.whisper','status':'owned_friend_whisper_pass' if
        all(checks.values()) else 'client_or_protocol_failure','time':started,
        'oracle':{'checks':checks,'sent':sent,'received':received,'guard':guard}});primary.persist()
    if not all(checks.values()):raise RuntimeError('stock owned friend whisper delivery differs')
