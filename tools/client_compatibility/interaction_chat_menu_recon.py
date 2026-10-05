"""Inspect owned stock chat shortcuts without selecting a message or language."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_control_target import click,target
from .interaction_operations import controls,point
from .interaction_keybindings_native import suite as native_suite
from .interaction_macros import require


def visible(state):
    return any(p in (state.get('panels') or []) for p in ['ContextMenu','DropDownList1'])


def inspect(t,languages=False,language_click=False):
    before=detail(t,'chat_shortcuts_original')
    if before['selected']!=1:raise RuntimeError('requires the original General chat window')
    try:
        require(click(t,'fixture.open_chat_shortcuts','Inspect the observed stock chat shortcut menu.',
            lambda c:c.get('name')=='ChatFrameMenuButton',
            lambda b,a,s:{'status':'stock_chat_shortcuts_visible' if s and visible(a) else 'client_or_protocol_failure'},
            await_state=visible),'stock_chat_shortcuts_visible')
        rows=controls(t);state,frame=t.observe('chat_shortcuts_rendered')
        t.receipt['chat_shortcuts']={'controls':rows,'state':state,'frame':frame};t.persist()
        if languages or language_click:
            c=target(t,'chat_language_submenu',lambda c:c.get('text')=='Language' and c.get('enabled'))
            action='click' if language_click else 'hover'
            require(t.step('fixture.'+action+'_chat_languages','Inspect the observed language submenu without selecting a language.',
                {action:{'kind':action,'value':point(c)}},
                lambda b,a,s:{'status':'stock_chat_language_input' if s==action and visible(a) else 'client_or_protocol_failure'},
                diagnostic_action=action,await_state=visible),'stock_chat_language_input')
            rows=controls(t);state,frame=t.observe('chat_languages_rendered')
            t.receipt['chat_languages']={'controls':rows,'state':state,'frame':frame};t.persist()
    finally:
        t.clean_panels();after=detail(t,'chat_shortcuts_restored')
        checks={'original_chat_settings':signature(after)==signature(before),
            'original_channels':after['channels']==before['channels']}
        t.receipt['chat_shortcuts_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('chat shortcut inspection changed settings')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--languages',action='store_true')
    mode.add_argument('--language-click',action='store_true');a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:
        native_suite(t,operations=lambda t:inspect(t,a.languages,a.language_click),preserve_settings=False)
        t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist()
