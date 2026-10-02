"""Observe the installed keybinding editor through model-selected normal inputs."""
import argparse
import json
from pathlib import Path
import time
from .interaction_trial import Trial
from .interaction_operations import click_case,controls,point
from .interaction_macros import require,edit_case


def open_editor(trial):
    trial.clean_panels()
    require(trial.step('menu.open','Open the game menu.',{
        'a':{'kind':'key','value':'Escape','description':'Press Escape to open the game menu.'},
        'b':{'kind':'key','value':'c','description':'Press C to open equipment.'},
        'c':{'kind':'key','value':'m','description':'Press M to open the world map.'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'GameMenuFrame' in a['panels'] else 'controller_failure'},diagnostic_action='a'),'panel_open_pass')
    rows=controls(trial);(trial.out/'menu_controls.json').write_text(json.dumps(rows,indent=2)+'\n')
    require(click_case(trial,'settings.open','Open the game options.',lambda c:c['text']=='Options',
        lambda b,a,s:{'status':'panel_open_pass' if 'KeyBindingFrame' in a['panels'] or 'SettingsPanel' in a['panels'] else ('controller_failure' if not s else 'client_or_protocol_failure')}),'panel_open_pass')
    rows=controls(trial);(trial.out/'options_controls.json').write_text(json.dumps(rows,indent=2)+'\n')
    require(click_case(trial,'keybindings.open','Open the Keybindings options category.',lambda c:c['text']=='Keybindings',
        lambda b,a,s:{'status':'panel_open_pass' if s and 'SettingsPanel' in a['panels'] else 'controller_failure'}),'panel_open_pass')
    rows=controls(trial);(trial.out/'keybinding_controls.json').write_text(json.dumps(rows,indent=2)+'\n')
    require(edit_case(trial,'keybindings.search','Search settings for Framerate.',
        lambda c:not c['name'],'Framerate'),'ui_edit_pass')
    rows=controls(trial);(trial.out/f'binding_controls_{len(trial.receipt["cases"]):03}.json').write_text(json.dumps(rows,indent=2)+'\n')
    return rows


def toggle(trial,case_id,expected):
    require(trial.step(case_id,'Toggle the framerate counter using its new Control Shift F12 binding.',{
        'binding':{'kind':'key','value':'ctrl+shift+F12','description':'Press Control Shift F12 to toggle the bound framerate counter.'},
        'character':{'kind':'key','value':'c','description':'Press C to open equipment.'},
        'friends':{'kind':'key','value':'o','description':'Press O to open friends.'}},
        lambda b,a,s:{'status':'binding_execute_pass' if a.get('framerate_visible')==expected else
            ('controller_failure' if s!='binding' else 'client_or_protocol_failure')},diagnostic_action='binding'),'binding_execute_pass')


def suite(trial):
    trial.clean_panels();initial,_=trial.observe('binding_fixture')
    if initial.get('binding_probe') or len(initial.get('fps_keys') or [])!=1:
        raise RuntimeError('requires an unused test chord and one existing framerate binding')
    trial.receipt['binding_baseline']={k:initial.get(k) for k in ['fps_keys','binding_probe','binding_set','framerate_visible']}
    trial.persist()
    open_editor(trial)
    require(click_case(trial,'keybindings.listen','Assign a second binding for Toggle Framerate Display.',
        lambda c:c.get('binding_action')=='TOGGLEFPS' and c.get('binding_slot')==2,
        lambda b,a,s:{'status':'binding_listener_pass' if a.get('keybind_listening')=={'action':'TOGGLEFPS','slot':2} else
            ('controller_failure' if not s else 'client_or_protocol_failure')}),'binding_listener_pass')
    require(trial.step('keybindings.assign','Set the new framerate binding to Control Shift F12.',{
        'chord':{'kind':'key','value':'ctrl+shift+F12','description':'Press Control Shift F12 to assign that chord.'},
        'escape':{'kind':'key','value':'Escape','description':'Cancel the binding listener.'},
        'tab':{'kind':'key','value':'Tab','description':'Assign Tab instead.'}},
        lambda b,a,s:{'status':'binding_assign_pass' if a.get('binding_probe')=='TOGGLEFPS' and not a.get('keybind_listening') else
            ('controller_failure' if s!='chord' else 'client_or_protocol_failure')},diagnostic_action='chord'),'binding_assign_pass')
    require(click_case(trial,'keybindings.save','Close settings and save the binding.',lambda c:c['text']=='Close',
        lambda b,a,s:{'status':'binding_save_pass' if 'SettingsPanel' not in a.get('panels',[]) and a.get('binding_probe')=='TOGGLEFPS' else
            ('controller_failure' if not s else 'client_or_protocol_failure')}),'binding_save_pass')
    trial.clean_panels()
    require(trial.step('keybindings.reload','Reload the interface to verify the saved binding.',{
        'reload':{'kind':'chat','value':'/reload','description':'Type /reload to reload the interface.'},
        'character':{'kind':'key','value':'c','description':'Press C to open equipment.'}},
        lambda b,a,s:{'status':'binding_reload_pass' if s=='reload' and a.get('binding_probe')=='TOGGLEFPS' else
            ('controller_failure' if s!='reload' else 'client_or_protocol_failure')},diagnostic_action='reload'),'binding_reload_pass')
    toggle(trial,'keybindings.execute',not initial.get('framerate_visible',False))
    toggle(trial,'keybindings.toggle_back',initial.get('framerate_visible',False))
    restore(trial,initial)


def restore(trial,initial):
    # Restore through the same ordinary editor; cleanup does not count as Laya qualification.
    saved_controller=trial.controller;trial.controller='code'
    try:
        state,_=trial.observe('binding_cleanup_check')
        if state.get('framerate_visible')!=initial.get('framerate_visible',False):
            trial.execute({'kind':'key','value':'ctrl+shift+F12'})
        open_editor(trial);rows=controls(trial)
        button=next(c for c in rows if c.get('binding_action')=='TOGGLEFPS' and c.get('binding_slot')==2)
        trial.execute({'kind':'click','value':point(button),'button':3})
        rows=controls(trial);trial.execute({'kind':'click','value':point(next(c for c in rows if c['text']=='Close'))})
        trial.clean_panels();trial.execute({'kind':'chat','value':'/reload'})
        state,frame=trial.observe('binding_restored')
        if state.get('binding_probe') or state.get('fps_keys')!=initial['fps_keys'] or state.get('binding_set')!=initial['binding_set']:
            raise RuntimeError('keybinding fixture restoration failed')
        trial.receipt['cleanup'].append({'source':'code_fixture_cleanup','binding_restored':True,'state':state,'frame':frame})
    finally:trial.controller=saved_controller


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--controller',choices=['laya','code'],default='laya');a=p.parse_args()
    trial=Trial(a.output,a.controller)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        baseline=trial.receipt.get('binding_baseline')
        if baseline:
            try:
                state,_=trial.observe('final_binding_check')
                if state.get('binding_probe')=='TOGGLEFPS':restore(trial,baseline)
            except Exception as e:
                trial.receipt['cleanup_failure']=f'{type(e).__name__}: {e}';trial.receipt['completed']=False
        trial.receipt['finished_at']=time.time();trial.persist()
        print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
