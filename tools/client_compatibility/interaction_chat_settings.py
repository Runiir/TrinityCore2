"""Inspect ordinary stock chat settings with exact local and native restoration."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_window import detail,menu,option
from .interaction_control_target import click
from .interaction_operations import controls
from .interaction_macros import require


FIELDS=['id','name','font_size','color','alpha','shown','locked','docked','uninteractable',
    'frame_visible','tab_visible','actual_font','actual_font_size','font_flags','scroll_offset']


def signature(probe):
    return {'windows':[{k:r.get(k) for k in FIELDS} for r in probe['windows']],
        'selected':probe['selected'],'message_types':probe['message_types']}


def open_settings(t):
    menu(t,1,'fixture.chat_settings_menu')
    require(option(t,'fixture.open_chat_settings','Settings',lambda b,a,s:{'status':'stock_chat_settings_visible'
        if s and 'ChatConfigFrame' in a['panels'] else 'client_or_protocol_failure'}),
        'stock_chat_settings_visible')


def recon(t):
    before=detail(t,'chat_settings_original')
    if before['selected']!=1 or before['windows'][0]['name']!='General' or not before['message_types_available']:
        raise RuntimeError('requires observed original General selection and public message filters')
    t.receipt['chat_settings_baseline']=before;t.persist()
    try:
        open_settings(t);rows=controls(t);state,frame=t.observe('chat_settings_rendered')
        probe=detail(t,'chat_settings_open')
        if not probe['settings_visible'] or probe['config_window_id']!=1:
            raise RuntimeError('chat settings are not editing the observed General window')
        t.receipt['chat_settings_recon']={'controls':rows,'frame':frame,'public':probe};t.persist()
    finally:
        t.clean_panels();after=detail(t,'chat_settings_restored')
        if after['selected']!=before['selected']:
            require(click(t,'fixture.restore_chat_selection','Restore the original observed chat tab.',
                lambda c:c['name']=='ChatFrame'+str(before['selected'])+'Tab',lambda b,a,s:{'status':
                'chat_selection_restored' if s and detail(t,'restored_selection')['selected']==before['selected']
                else 'client_or_protocol_failure'}),'chat_selection_restored')
            after=detail(t,'chat_settings_selection_restored')
        checks={'local_settings_exact':signature(before)==signature(after),'settings_closed':not after['settings_visible']}
        t.receipt['chat_settings_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('original chat window settings or filters differ')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=recon,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
