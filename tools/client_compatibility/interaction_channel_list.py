"""List one native-owned disposable channel through its stock slash command."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_chat_channels import run,member
from .interaction_chat_window import detail
from .interaction_keybindings_native import suite as native_suite
from .interaction_macros import require
from .observation.journal import latest,Cursor


def listed(t,name):
    before=detail(t,'owned_channel_list_before');entry=actors.session_entry(t.fixture)
    instance=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('event')=='instance_authenticated' and
        r.get('account_id')==t.fixture['account_id'] and r.get('time',0)>=entry['time']-5)
    if not instance or len(member(before,name))!=1 or member(before,name)[0]['disabled']:
        raise RuntimeError('owned active channel or authenticated instance differs')
    session=entry['session'];started=time.time()
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for packet in cursor.poll():pass
    def outcome(b,a,s):
        after=detail(t,'owned_channel_list_result');path=lab.ROOT/'logs/modern_world.jsonl'
        observed=[r for r in cursor.poll() if r.get('session')==session and r.get('time',0)>=started and
            name.encode() in bytes.fromhex(r.get('body',''))]
        facts={}
        for direction,event,session_id,names in [
            ('from_client','modern_packet',session,{'CMSG_CHAT_CHANNEL_LIST','CMSG_CHAT_CHANNEL_DISPLAY_LIST'}),
            ('from_native','native_packet',session,{'SMSG_CHANNEL_LIST'}),
            ('to_client','modern_packet',instance['session'],{'SMSG_CHANNEL_LIST'})]:
            facts[direction]=latest(path,lambda r:r.get('session')==session_id and r.get('time',0)>=started and
                r.get('event')==event and r.get('direction')==direction and r.get('name') in names)
        checks={'ordinary_list':s=='list','authenticated_native_response':facts['from_native'] is not None,
            'modern_list_response':facts['to_client'] is not None,'stock_list_request':facts['from_client'] is not None,
            'same_enabled_channel':member(before,name)==member(after,name),'new_general_line':after['selected']==1 and
                after['windows'][0]['message_count']>before['windows'][0]['message_count'],
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'owned_channel_list_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'events':facts,'public':after,'native_session':session,
                'authenticated_instance':instance,'name':name,'packets':observed,
                'channel_list_events_before':before.get('channel_list'),'channel_list_events_after':after.get('channel_list')}}
    require(t.step('chat.channel_list','Use stock chatlist for only the enabled owned channel.',
        {'list':{'kind':'chat','value':'/chatlist '+name,'description':'List the exact owned channel through stock chatlist.'}},
        outcome,diagnostic_action='list'),'owned_channel_list_pass')
    state,frame=t.observe('owned_channel_list_rendered');t.receipt['channel_list_rendered']={'state':state,'frame':frame};t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=lambda t:run(t,on_join=listed),preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
