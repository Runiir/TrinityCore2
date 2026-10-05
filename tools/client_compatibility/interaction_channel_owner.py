"""Query the owner of one disposable channel through stock slash input."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_chat_channels import run,member
from .interaction_chat_window import detail
from .interaction_keybindings_native import suite as native_suite
from .interaction_macros import require
from .observation.journal import latest,Cursor


def owner(t,name):
    before=detail(t,'owned_channel_owner_before');entry=actors.session_entry(t.fixture)
    if len(member(before,name))!=1 or member(before,name)[0]['disabled']:
        raise RuntimeError('owned active channel differs')
    session=entry['session'];started=time.time()
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for packet in cursor.poll():pass
    def outcome(b,a,s):
        after=detail(t,'owned_channel_owner_result');path=lab.ROOT/'logs/modern_world.jsonl'
        dropped=latest(path,lambda r:r.get('session')==session and r.get('time',0)>=started and
            r.get('event')=='unmapped_client_packet' and r.get('name')=='CMSG_CHAT_CHANNEL_OWNER')
        native=latest(path,lambda r:r.get('session')==session and r.get('time',0)>=started and
            r.get('event')=='native_packet' and r.get('direction')=='from_native' and r.get('name')=='SMSG_CHANNEL_NOTIFY')
        observed=[r for r in cursor.poll() if r.get('session')==session and r.get('time',0)>=started and
            name.encode() in bytes.fromhex(r.get('body',''))]
        native_owner=[r for r in observed if r['direction']=='from_native' and r['name']=='SMSG_CHANNEL_NOTIFY' and
            bytes.fromhex(r['body'])==b'\x0b'+name.encode()+b'\0'+t.fixture['character_name'].encode()+b'\0']
        required={('from_client','CMSG_CHAT_CHANNEL_OWNER'),('to_native','CMSG_CHAT_CHANNEL_OWNER'),
            ('from_native','SMSG_CHANNEL_NOTIFY'),('to_client','SMSG_CHANNEL_NOTIFY')}
        checks={'ordinary_owner_query':s=='owner','request_translated':dropped is None,'native_notice':native is not None,
            'native_exact_owner':len(native_owner)==1,'all_wire_directions':required.issubset({(r['direction'],r['name']) for r in observed}),
            'same_enabled_channel':member(before,name)==member(after,name),'new_general_line':after['selected']==1 and
                after['windows'][0]['message_count']>before['windows'][0]['message_count'],
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'owned_channel_owner_query_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native_notice':native,'unmapped_request':dropped,'packets':observed,'public':after,'name':name}}
    require(t.step('chat.channel_owner','Query only the disposable channel owner through ordinary slash input.',
        {'owner':{'kind':'chat','value':'/owner '+name,'description':'Display the exact owned channel owner.'}},
        outcome,diagnostic_action='owner'),'owned_channel_owner_query_pass')
    state,frame=t.observe('owned_channel_owner_rendered');t.receipt['channel_owner_rendered']={'state':state,'frame':frame};t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=lambda t:run(t,on_join=owner),preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
