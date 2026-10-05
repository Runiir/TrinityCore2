"""Inspect the stock chat tab menu before choosing reversible window controls."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_observation import read_page
from .interaction_operations import command,controls,point
from .interaction_control_target import target
from .interaction_macros import require


def detail(t,label):
    try:
        state,frame=read_page(t,label,'chat','/tcui chat')
        t.receipt.setdefault('chat_window_details',{})[label]={'state':state,'frame':frame};t.persist()
        probe=state['chat_window_probe']
        if not probe['available']:raise RuntimeError('public chat-window info API is unavailable')
        return probe
    finally:command(t,'/tcui state')


def recon(t):
    before=detail(t,'chat_windows_original');t.receipt['chat_window_baseline']=before;t.persist()
    control=target(t,'stock_general_chat_tab',lambda c:c['name']=='ChatFrame1Tab')
    require(t.step('fixture.chat_tab_menu','Inspect the observed General chat-tab context menu.',
        {'menu':{'kind':'click','value':point(control),'button':3,'description':'Right-click the observed General chat tab.'}},
        lambda b,a,s:{'status':'stock_chat_menu_visible' if s=='menu' and
            any(p in a['panels'] for p in ['DropDownList1','ContextMenu']) else 'client_or_protocol_failure'},
        diagnostic_action='menu'),'stock_chat_menu_visible')
    rows=controls(t);t.receipt['chat_menu_observed_controls']=rows;t.persist();t.clean_panels()
    after=detail(t,'chat_windows_recon_restored')
    fields=['id','name','font_size','color','alpha','shown','locked','docked','uninteractable',
        'frame_visible','actual_font','actual_font_size','font_flags','scroll_offset']
    signature=lambda probe:[{k:row.get(k) for k in fields} for row in probe['windows']]
    same=signature(before)==signature(after) and before['selected']==after['selected']
    t.receipt['chat_window_recon_restored']=same;t.persist()
    if not same:raise RuntimeError('chat-window settings changed during read-only menu inspection')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=recon,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
