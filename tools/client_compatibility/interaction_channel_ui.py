"""Inspect fresh stock channel buttons and the owned cached roster."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_chat_channels import run
from .interaction_chat_window import detail
from .interaction_operations import controls
from .interaction_control_target import click
from .interaction_keybindings_native import suite as native_suite
from .interaction_macros import require
from .observation.journal import Cursor


def inspect(t,name,button=None,select=False):
    before=detail(t,'channel_ui_roster_before')
    rows=controls(t)
    t.receipt['channel_ui_visible_buttons']=[r for r in rows if any(word in (r.get('name','')+' '+r.get('text','')).lower()
        for word in ['chat','channel','voice'])];t.persist()
    if button:
        require(click(t,'fixture.open_channels_ui','Use the separately reviewed visible stock channel button.',
            lambda c:c['name']==button,
            lambda b,a,s:{'status':'stock_channel_frame_visible' if s and 'ChannelFrame' in a['panels']
                else 'client_or_protocol_failure'}),'stock_channel_frame_visible')
        rows=controls(t);t.receipt['channel_ui_controls']=rows;t.persist()
    if select:
        if not button:raise ValueError('select requires the reviewed stock open button')
        ready=detail(t,'channel_ui_owned_roster_before_select')
        session=actors.session_entry(t.fixture)['session'];cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
        for packet in cursor.poll():pass
        started=time.time()
        def selected(b,a,s):
            after=detail(t,'channel_ui_owned_roster_selected')
            channel_list=after.get('channel_list',{});roster=channel_list.get('roster',{})
            owned=[r for r in roster.get('channels',[]) if r.get('name')==name]
            members=owned[0].get('members',[]) if len(owned)==1 else []
            packets=[p for p in cursor.poll() if p.get('session')==session and p.get('time',0)>=started and
                name.encode() in bytes.fromhex(p.get('body',''))]
            requests={'CMSG_CHAT_CHANNEL_LIST','CMSG_CHAT_CHANNEL_DISPLAY_LIST'}
            checks={'ordinary_owned_row':s,'one_owned_channel':len(owned)==1,'one_public_member':len(members)==1 and
                members[0].get('name')==t.fixture['character_name'] and members[0].get('is_player') is True,
                'native_roster_reply':any(p['direction']=='from_native' and p['name']=='SMSG_CHANNEL_LIST' for p in packets),
                'modern_roster_reply':any(p['direction']=='to_client' and p['name']=='SMSG_CHANNEL_LIST' for p in packets),
                'stock_roster_request':any(p['direction']=='from_client' and p['name'] in requests for p in packets),
                'fresh_roster_event':channel_list.get('received_sequence',0)>ready.get('channel_list',{}).get('received_sequence',0),
                'stock_panel_visible':'ChannelFrame' in a['panels'],'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'owned_stock_channel_roster_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':after,'packets':packets,'name':name,'native_session':session}}
        def exact_row(c):
            text=re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',c.get('text','')).strip()
            return c['kind']=='Button' and text.split('. ',1)[-1]==name
        require(click(t,'chat.channel_list','Select only the observed disposable stock channel row.',exact_row,selected),
            'owned_stock_channel_roster_pass')
        t.receipt['channel_ui_selected_controls']=controls(t);t.persist()
    after=detail(t,'channel_ui_roster_after');state,frame=t.observe('channel_ui_rendered')
    t.receipt['channel_ui_recon']={'name':name,'before':before,'after':after,'frame':frame,'state':state};t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--open-control');p.add_argument('--select-owned',action='store_true');a=p.parse_args();t=Trial(a.output,controller='code')
    try:native_suite(t,operations=lambda t:run(t,on_join=lambda t,name:inspect(t,name,a.open_control,a.select_owned)),preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
