"""Explicitly cancel a binding listener and clear a disposable saved binding."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from . import interaction_keybindings as bindings
from .interaction_operations import click_case,point,controls
from .interaction_macros import require


def suite(t):
    original_suite=bindings.suite
    # Exercise the cancel case before the ordinary assignment/persistence trial.
    t.clean_panels();before,_=t.observe('cancel_fixture')
    if before.get('binding_probe') or len(before.get('fps_keys') or [])!=1:
        raise RuntimeError('requires the unused disposable chord and original binding')
    bindings.open_editor(t)
    require(click_case(t,'keybindings.cancel_listen','Begin listening for the second framerate binding.',
        lambda c:c.get('binding_action')=='TOGGLEFPS' and c.get('binding_slot')==2,
        lambda b,a,s:{'status':'listener_open_pass' if s and a.get('keybind_listening')==
            {'action':'TOGGLEFPS','slot':2} else 'client_or_protocol_failure'}),'listener_open_pass')
    require(t.step('keybindings.cancel','Cancel the binding listener with Escape.',
        {'cancel':{'kind':'key','value':'Escape','hold':.4,'description':'Cancel this binding listener.'}},
        lambda b,a,s:{'status':'binding_cancel_pass' if not a.get('keybind_listening') and
            a.get('fps_keys')==before['fps_keys'] and not a.get('binding_probe') and
            'SettingsPanel' in a['panels'] else 'client_or_protocol_failure'},
        diagnostic_action='cancel'),'binding_cancel_pass')
    t.clean_panels();original_suite(t)
    # Reassign through the same reviewed stock editor, then clear in an explicit case.
    bindings.open_editor(t)
    require(click_case(t,'keybindings.clear_prepare','Listen for a temporary second framerate binding.',
        lambda c:c.get('binding_action')=='TOGGLEFPS' and c.get('binding_slot')==2,
        lambda b,a,s:{'status':'listener_open_pass' if s and a.get('keybind_listening')==
            {'action':'TOGGLEFPS','slot':2} else 'client_or_protocol_failure'}),'listener_open_pass')
    require(t.step('keybindings.clear_assign','Assign the disposable chord before clearing it.',
        {'assign':{'kind':'key','value':'ctrl+shift+F12','description':'Assign the unused chord.'}},
        lambda b,a,s:{'status':'binding_assign_pass' if a.get('binding_probe')=='TOGGLEFPS' else
            'client_or_protocol_failure'},diagnostic_action='assign'),'binding_assign_pass')
    rows=controls(t);button=next(c for c in rows if c.get('binding_action')=='TOGGLEFPS' and c.get('binding_slot')==2)
    require(t.step('keybindings.clear_binding','Right-click the temporary second binding to clear it.',
        {'clear':{'kind':'click','value':point(button),'button':3,'description':'Right-click the bound second slot.'}},
        lambda b,a,s:{'status':'binding_clear_pass' if not a.get('binding_probe') and
            a.get('fps_keys')==before['fps_keys'] and not a.get('keybind_listening') else
            'client_or_protocol_failure'},diagnostic_action='clear'),'binding_clear_pass')
    require(click_case(t,'keybindings.clear_save','Close and save the cleared binding.',lambda c:c['text']=='Close',
        lambda b,a,s:{'status':'binding_clear_save_pass' if s and 'SettingsPanel' not in a['panels'] and
            not a.get('binding_probe') else 'client_or_protocol_failure'}),'binding_clear_save_pass')
    require(t.step('keybindings.clear_reload','Reload to verify the cleared chord stays unbound.',
        {'reload':{'kind':'chat','value':'/reload','description':'Reload the saved bindings.'}},
        lambda b,a,s:{'status':'binding_clear_persistence_pass' if not a.get('binding_probe') and
            all(a.get(k)==before.get(k) for k in ['fps_keys','binding_set','framerate_visible']) else
            'client_or_protocol_failure'},diagnostic_action='reload'),'binding_clear_persistence_pass')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,suite);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
