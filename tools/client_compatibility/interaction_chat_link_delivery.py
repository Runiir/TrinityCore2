"""Deliver one stock-generated owned item link through normal Say chat."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_links import bag
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_observation import read_current_page
from .observation.journal import Cursor


def pending_item_link(state,text,id):
    exact=re.fullmatch(r'\|cffffffff\|Hitem:49778:[0-9:-]*\|h\[Worn Greatsword\]\|h\|r',text)
    return bool(id==49778 and exact and state.get('chat_edit_open') and state.get('chat_edit_focused') and
        state.get('chat_edit_type')=='SAY' and state.get('chat_edit_text')==text)


def run(t):
    before=detail(t,'item_chat_delivery_original')
    if before['selected']!=1 or 'SAY' not in before['message_types'] or before['windows'][0]['scroll_offset']!=0:
        raise RuntimeError('requires original General selection, Say and bottom scroll position')
    session=actors.session_entry(t.fixture)['session'];cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for packet in cursor.poll():pass
    t.receipt['chat_link_delivery_baseline']=before;t.persist()
    def send(t,text,id):
        with owned_input.lease():
            state,frame=read_current_page(t,'owned_item_link_send_guard','state',lambda s:pending_item_link(s,text,id))
            if not pending_item_link(state,text,id):raise RuntimeError('exact stock-generated owned Say link differs')
            row={'id':'chat.chat_links','goal':'Submit the exact observed owned item link through normal Say.',
                'time':time.time(),'status':'started','pending_text':text,'guard_frame':frame,
                'submitted':False,'input_replayed':False}
            t.receipt['cases'].append(row);t.persist()
            t.io.key('Return',hold=.4);row['submitted']=True;t.persist()
            state,frame=read_current_page(t,'owned_item_link_sent','state',lambda s:not s.get('chat_edit_open'))
            packets=[];deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                for packet in cursor.poll():
                    body=bytes.fromhex(packet.get('body',''))
                    if packet.get('session')!=session or packet.get('time',0)<row['time'] or text.encode() not in body:continue
                    packets.append({'name':packet['name'],'direction':packet['direction'],'time':packet['time'],
                        'native_sender_guid':int.from_bytes(body[5:13],'little') if packet['direction']=='from_native' and
                        packet['name']=='SMSG_MESSAGECHAT' and len(body)>=13 else None})
                if any(p['name']=='SMSG_CHAT' and p['direction']=='to_client' for p in packets):break
                time.sleep(.25)
            after=detail(t,'owned_item_link_delivered_chat')
            checks={'exact_owned_say_guard':True,'ordinary_say_request':any(p['direction']=='from_client' and
                p['name']=='CMSG_CHAT_MESSAGE_SAY' for p in packets),'native_owned_sender':any(p['direction']=='from_native' and
                p['name']=='SMSG_MESSAGECHAT' and p['native_sender_guid']==t.fixture['guid'] for p in packets),
                'modern_delivery':any(p['direction']=='to_client' and p['name']=='SMSG_CHAT' for p in packets),
                'new_general_message':after['selected']==1 and after['windows'][0]['message_count']>before['windows'][0]['message_count'],
                'chat_edit_closed':not state.get('chat_edit_open'),'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
            row.update(status='owned_item_chat_delivery_pass' if all(checks.values()) else 'client_or_protocol_failure',
                oracle={'checks':checks,'packets':packets,'session':session,'public':after,'frame':frame});t.persist()
            scene,frame=t.observe('owned_item_link_rendered');t.receipt['chat_link_delivery_rendered']={'state':scene,'frame':frame};t.persist()
            if not all(checks.values()):raise RuntimeError('owned item chat-link delivery differs')
    try:bag(t,on_insert=send)
    finally:
        t.clean_panels();after=detail(t,'item_chat_delivery_restored')
        checks={'original_chat_settings':signature(before)==signature(after),
            'same_geometry':all(before[k]==after[k] for k in ['selected_height','selected_width'])}
        t.receipt['chat_link_delivery_restoration']={'checks':checks,'public':after,
            'limits':'The owned Say link remains in ordinary history. Link clicks, peer delivery and other link types remain open.'};t.persist()
        if not all(checks.values()):raise RuntimeError('original chat settings differ after item link')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=run,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
