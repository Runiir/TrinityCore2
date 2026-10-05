"""Inspect ordinary stock chat settings with exact local and native restoration."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_window import detail,menu,option
from .interaction_control_target import click,target
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


def say_control(c):
    return c['name']=='ChatConfigChatSettingsLeftCheckbox1Check' and c['text']=='Say' and c['kind']=='CheckButton'


def set_say(t,enabled,label,expected):
    control=target(t,label+'_guard',say_control)
    if control.get('checked')==enabled:raise RuntimeError('Say checkbox already has the requested state')
    def outcome(b,a,s):
        probe=detail(t,label+'_result')
        checks={'ordinary_click':s,'same_general_window':probe['settings_visible'] and probe['config_window_id']==1,
            'exact_message_types':probe['message_types_available'] and probe['message_types']==expected,
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_chat_filter_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':probe}}
    require(click(t,label,'Use the observed stock Say checkbox.',say_control,outcome),'stock_chat_filter_pass')
    observed=target(t,label+'_checked',say_control)
    t.receipt.setdefault('chat_filter_checks',[]).append({'label':label,'control':observed,'expected_checked':enabled});t.persist()
    if observed.get('checked')!=enabled:raise RuntimeError('visible Say checkmark differs from public filters')


def close_settings(t,label):
    require(click(t,label,'Close the stock chat settings with its observed Okay button.',lambda c:
        c['name']=='ChatConfigFrameOkayButton' and c['text']=='Okay',lambda b,a,s:{'status':'chat_settings_closed'
        if s and 'ChatConfigFrame' not in a['panels'] else 'client_or_protocol_failure'}),'chat_settings_closed')


def mutate(t):
    before=detail(t,'chat_filter_original')
    if before['selected']!=1 or before['windows'][0]['name']!='General' or not before['message_types_available'] or 'SAY' not in before['message_types']:
        raise RuntimeError('requires original General selection with the observed Say filter enabled')
    expected=[v for v in before['message_types'] if v!='SAY']
    t.receipt['chat_filter_baseline']=before;t.persist()
    try:
        open_settings(t);set_say(t,False,'chat.chat_settings',expected)
        close_settings(t,'fixture.close_changed_chat_settings');open_settings(t)
        current=detail(t,'chat_filter_reopened')
        checks={'same_window':current['settings_visible'] and current['config_window_id']==1,
            'exact_filter_persisted_across_panel_reopen':current['message_types']==expected}
        t.receipt['chat_filter_reopen']={'checks':checks,'public':current};t.persist()
        if not all(checks.values()):raise RuntimeError('exact Say-only change did not survive panel reopening')
        set_say(t,True,'fixture.restore_say_filter',before['message_types'])
        close_settings(t,'fixture.close_restored_chat_settings')
    finally:
        current=detail(t,'chat_filter_cleanup_guard')
        if current['selected']!=1:raise RuntimeError('cleanup refuses an unexpected chat selection')
        if current['message_types']!=before['message_types']:
            if current['message_types']!=expected:raise RuntimeError('cleanup refuses an unrelated filter change')
            if not current['settings_visible']:open_settings(t)
            set_say(t,True,'fixture.recover_original_say_filter',before['message_types'])
        t.clean_panels();after=detail(t,'chat_filter_restored')
        checks={'local_settings_exact':signature(before)==signature(after),'settings_closed':not after['settings_visible']}
        t.receipt['chat_filter_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('original chat settings or filters differ after cleanup')


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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mutate',action='store_true');a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=mutate if a.mutate else recon,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
