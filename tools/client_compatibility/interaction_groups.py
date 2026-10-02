"""Continue a verified two-owned-character group through its ordinary raid UI."""
import argparse
import json
from pathlib import Path
import time
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import click_case,controls
from .interaction_macros import require


def suite(trial):
    actors.session_entry(trial.fixture);trial.clean_panels();state,_=trial.observe('group_fixture')
    if state['group']['members']!=2 or set(state['group']['names'])!={'Harnessone','Harnesstwo'} or not state['group']['leader']:
        raise RuntimeError('group fixture is not the two owned characters with the owned leader')
    require(trial.step('friends.open','Open the friends and social window.',{
        'a':{'kind':'key','value':'o','description':'Press O to open friends and social.'},
        'b':{'kind':'key','value':'m','description':'Press M to open the world map.'},
        'c':{'kind':'key','value':'c','description':'Press C to open equipment.'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'FriendsFrame' in a['panels'] else 'controller_failure'}),'panel_open_pass')
    require(click_case(trial,'raid.raid_panel','Open the Raid tab.',lambda c:c['name']=='FriendsFrameTab4',
        lambda b,a,s:{'status':'panel_open_pass' if 'RaidFrame' in a['panels'] else ('controller_failure' if not s else 'client_or_protocol_failure')}),'panel_open_pass')
    rows=controls(trial);lab.private_write(trial.out/'raid_controls.json',json.dumps(rows,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();trial=Trial(a.output)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at']=time.time();trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
