"""Owned player context menu reached by an observed physical right click."""
import argparse
import json
from pathlib import Path
import time
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,point
from .interaction_macros import require


def suite(trial):
    trial.clean_panels();state,_=trial.observe('group_fixture')
    if state['group']['members']!=2 or set(state['group']['names'])!={'Harnessone','Harnesstwo'}:
        raise RuntimeError('context-menu trial requires the two-owned-character group')
    rows=controls(trial);player=next((c for c in rows if c['name']=='PlayerFrame'),None)
    if player is None:raise RuntimeError('owned player frame is not observed')
    require(trial.step('ui_misc.player_context_menu','Open your player portrait context menu.',{
        'a':{'kind':'click','value':point(player),'button':3,'description':'Right-click your visible player portrait to open its context menu.'},
        'b':{'kind':'key','value':'o','description':'Press O to open friends and social.'},
        'c':{'kind':'key','value':'Escape','description':'Press Escape to open the game menu.'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'ContextMenu' in a['panels'] else ('controller_failure' if s!='a' else 'adapter_observation_missing'),
            'oracle':{'qualified_scope':'visible player context menu'}}),'panel_open_pass')
    rows=controls(trial);lab.private_write(trial.out/'player_menu_controls.json',json.dumps(rows,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();trial=Trial(a.output)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at']=time.time();trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
