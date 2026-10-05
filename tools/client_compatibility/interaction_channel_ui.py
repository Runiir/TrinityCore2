"""Inspect fresh stock channel buttons and the owned cached roster."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_chat_channels import run
from .interaction_chat_window import detail
from .interaction_operations import controls
from .interaction_control_target import click
from .interaction_keybindings_native import suite as native_suite
from .interaction_macros import require


def inspect(t,name,button=None):
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
    after=detail(t,'channel_ui_roster_after');state,frame=t.observe('channel_ui_rendered')
    t.receipt['channel_ui_recon']={'name':name,'before':before,'after':after,'frame':frame,'state':state};t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--open-control');a=p.parse_args();t=Trial(a.output,controller='code')
    try:native_suite(t,operations=lambda t:run(t,on_join=lambda t,name:inspect(t,name,a.open_control)),preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
