"""Observe the installed keybinding editor through model-selected normal inputs."""
import argparse
import json
from pathlib import Path
import time
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require


def suite(trial):
    trial.clean_panels()
    require(trial.step('menu.open','Open the game menu.',{
        'a':{'kind':'key','value':'Escape','description':'Press Escape to open the game menu.'},
        'b':{'kind':'key','value':'c','description':'Press C to open equipment.'},
        'c':{'kind':'key','value':'m','description':'Press M to open the world map.'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'GameMenuFrame' in a['panels'] else 'controller_failure'}),'panel_open_pass')
    rows=controls(trial);(trial.out/'menu_controls.json').write_text(json.dumps(rows,indent=2)+'\n')
    require(click_case(trial,'settings.open','Open the game options.',lambda c:c['text']=='Options',
        lambda b,a,s:{'status':'panel_open_pass' if 'KeyBindingFrame' in a['panels'] or 'SettingsPanel' in a['panels'] else ('controller_failure' if not s else 'client_or_protocol_failure')}),'panel_open_pass')
    rows=controls(trial);(trial.out/'options_controls.json').write_text(json.dumps(rows,indent=2)+'\n')
    require(click_case(trial,'keybindings.open','Open the Keybindings options category.',lambda c:c['text']=='Keybindings',
        lambda b,a,s:{'status':'panel_open_pass' if s and 'SettingsPanel' in a['panels'] else 'controller_failure'}),'panel_open_pass')
    rows=controls(trial);(trial.out/'keybinding_controls.json').write_text(json.dumps(rows,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    trial=Trial(a.output)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at']=time.time();trial.persist()
        print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
