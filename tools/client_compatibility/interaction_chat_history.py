"""Scroll attributable owned chat history through ordinary stock buttons."""
import argparse,hashlib,json,math,re,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_control_target import click
from .interaction_observation import read_current_page
from .interaction_macros import require
from .observation.journal import Cursor


def pending_say(state,token,command):
    return bool(state.get('chat_edit_open') and state.get('chat_edit_focused') and
        state.get('chat_edit_type')=='SAY' and state.get('chat_edit_text') in (token,command))


def seed(t,cursor,session,token):
    if not re.fullmatch(r'TC442UI:scroll_[0-9a-f]{8}_[0-9]{2}',token):
        raise ValueError('history transport requires an exact owned scroll marker')
    command='/s '+token;started=time.time()
    row={'token':token,'command':command,'submitted':False,'input_replayed':False}
    t.receipt.setdefault('chat_history_seeds',[]).append(row);t.persist()
    with owned_input.lease():
        state,frame=read_current_page(t,'history_seed_before','state',lambda s:not s.get('chat_edit_open'))
        if state.get('observer_version',0)<89:raise RuntimeError('history transport requires observer89')
        t.io.key('Return',hold=.4);time.sleep(.2)
        state,frame=read_current_page(t,'history_seed_open','state',lambda s:
            s.get('chat_edit_open') and s.get('chat_edit_focused'))
        row['open_frame']=frame;t.persist();t.io.type(command);time.sleep(.2)
        state,frame=read_current_page(t,'history_seed_pending','state',lambda s:pending_say(s,token,command))
        row.update(pending_frame=frame,observed_type=state['chat_edit_type'],observed_text=state['chat_edit_text']);t.persist()
        t.io.key('Return',hold=.4);row['submitted']=True;t.persist();time.sleep(.8)
        state,frame=read_current_page(t,'history_seed_sent','state',lambda s:not s.get('chat_edit_open') and
            any(p['text']==token and p['event']=='CHAT_MSG_SAY' for p in s.get('chat_probes',[])))
        matches=[]
        for packet in cursor.poll():
            body=bytes.fromhex(packet.get('body',''))
            if packet.get('session')==session and packet.get('time',0)>=started and token.encode() in body:
                matches.append({'name':packet['name'],'direction':packet['direction'],'time':packet['time'],
                    'native_sender_guid':int.from_bytes(body[5:13],'little') if packet['direction']=='from_native' and
                    packet['name']=='SMSG_MESSAGECHAT' and len(body)>=13 else None})
        checks={'ordinary_say_request':any(p['direction']=='from_client' and p['name']=='CMSG_CHAT_MESSAGE_SAY' for p in matches),
            'native_owned_sender':any(p['direction']=='from_native' and p['name']=='SMSG_MESSAGECHAT' and
                p['native_sender_guid']==t.fixture['guid'] for p in matches),'public_say_marker':True}
        row.update(sent_frame=frame,checks=checks,packets=matches);t.persist()
        print(json.dumps({'seed':token,'checks':checks}),flush=True)
        if not all(checks.values()):raise RuntimeError('owned history fixture delivery differs')


def scroll(t,label,name,expected_count,predicate):
    def outcome(b,a,s):
        probe=detail(t,label+'_result');row=probe['windows'][0]
        checks={'ordinary_button':s,'same_general':probe['selected']==1 and row['name']=='General',
            'same_message_count':row['message_count']==expected_count,'scroll_offset':predicate(row['scroll_offset']),
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_chat_scroll_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':probe}}
    require(click(t,label,'Use the observed stock chat-history scroll button.',lambda c:
        c['name']==name,outcome),'stock_chat_scroll_pass')


def run(t):
    before=detail(t,'chat_history_original');row=before['windows'][0]
    if before['selected']!=1 or row['name']!='General' or row['scroll_offset']!=0 or 'SAY' not in before['message_types']:
        raise RuntimeError('requires observed original General selection, Say enabled and bottom scroll position')
    count=math.ceil(before['selected_height']/row['actual_font_size'])+4
    if not 4<=count<=24:raise RuntimeError('visible chat geometry exceeds the bounded fixture')
    t.receipt['chat_history_baseline']=before;t.receipt['chat_history_seed_count']=count;t.persist()
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for packet in cursor.poll():pass
    session=actors.session_entry(t.fixture)['session'];nonce=hashlib.sha256(str(t.out).encode()).hexdigest()[:8]
    try:
        for index in range(count):seed(t,cursor,session,'TC442UI:scroll_'+nonce+'_'+str(index).zfill(2))
        seeded=detail(t,'chat_history_seeded');messages=seeded['windows'][0]['message_count']
        if messages<row['message_count']+count:raise RuntimeError('owned seed history is shorter than attributable deliveries')
        scroll(t,'chat.scroll_history','ChatFrame1ButtonFrameUpButton',messages,lambda offset:offset>0)
        up=detail(t,'chat_history_up');offset=up['windows'][0]['scroll_offset']
        scroll(t,'fixture.scroll_history_down','ChatFrame1ButtonFrameDownButton',messages,lambda value:0<=value<offset)
    finally:
        t.clean_panels();current=detail(t,'chat_history_cleanup_guard')
        if current['selected']!=1:raise RuntimeError('history cleanup refuses an unexpected chat selection')
        if current['windows'][0]['scroll_offset']!=0:
            scroll(t,'fixture.restore_history_bottom','ChatFrame1ButtonFrameBottomButton',
                current['windows'][0]['message_count'],lambda offset:offset==0)
        after=detail(t,'chat_history_restored')
        checks={'original_settings_and_offset':signature(before)==signature(after),
            'same_geometry':all(before[k]==after[k] for k in ['selected_height','selected_width'])}
        t.receipt['chat_history_restoration']={'checks':checks,'public':after,
            'limits':'Owned fixture messages remain in normal history. No ClearMessages setter or byte-identical history rollback.'};t.persist()
        if not all(checks.values()):raise RuntimeError('original chat settings, geometry or scroll offset differ')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=run,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
