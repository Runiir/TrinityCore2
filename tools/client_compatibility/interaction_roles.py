"""Role poll and per-member selection through owned clients' ordinary UI."""
import argparse
import json
from pathlib import Path
import time
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_group_state import capture
from .interaction_social import actor


def run(output):
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    summary={'schema':'client442_role_trial_v1','started_at':time.time(),'completed':False,'failure':None,'actors':{}}
    try:
        with actor('primary'):
            trial=Trial(output/'initiate')
            try:
                trial.clean_panels();state,_=trial.observe('initial')
                if not state['group']['leader'] or state['group']['members']!=2:raise RuntimeError('owned two-member group leader required')
                if not state['raid_profile']['expanded']:
                    require(click_case(trial,'roles.open_controls','Expand the main-screen raid controls.',
                        lambda c:c['name']=='CompactRaidFrameManagerToggleButton',
                        lambda b,a,s:{'status':'panel_open_pass' if a['raid_profile']['expanded'] else 'controller_failure'}),'panel_open_pass')
                require(click_case(trial,'roles.initiate','Start a role check for the group.',
                    lambda c:'RolePoll' in c['name'] and c['kind']=='Button',
                    lambda b,a,s:{'status':'role_poll_pass' if a['role_poll'] else 'client_or_protocol_failure'}),'role_poll_pass')
                trial.receipt['completed']=True
            except BaseException as e:trial.receipt['failure']=f'{type(e).__name__}: {e}';raise
            finally:trial.receipt['finished_at']=time.time();trial.persist()
        for name,role,assigned in [('primary','Tank','TANK'),('scout','DPS','DAMAGER')]:
            with actor(name):
                trial=Trial(output/name)
                try:
                    before,_=trial.observe('role_poll_received')
                    if not before['role_poll']:raise RuntimeError('role check did not open on '+name)
                    if not before['role_poll_checked'][role]:
                        require(click_case(trial,'roles.select.'+role,'Select '+role+' as your group role.',
                            lambda c:c['name']=='RolePollPopupRoleButton'+role,
                            lambda b,a,s:{'status':'role_selection_pass' if a['role_poll_checked'][role] else 'controller_failure'}),'role_selection_pass')
                    require(click_case(trial,'roles.accept','Accept the selected group role.',
                        lambda c:c['name']=='RolePollPopupAcceptButton',
                        lambda b,a,s:{'status':'role_assignment_pass' if not a['role_poll'] and a['role']==assigned else 'client_or_protocol_failure'}),'role_assignment_pass')
                    trial.receipt['completed']=True
                except BaseException as e:trial.receipt['failure']=f'{type(e).__name__}: {e}';raise
                finally:trial.receipt['finished_at']=time.time();trial.persist()
        for name in ['primary','scout']:
            with actor(name):
                trial=Trial(output/(name+'_peer_roles'))
                try:
                    facts=capture(trial,'assigned')
                    roles={u['name']:u['role'] for u in facts['group']['units']}
                    if roles!={'Harnessone':'TANK','Harnesstwo':'DAMAGER'}:raise RuntimeError('peer roles disagree: '+str(roles))
                    trial.receipt.update(completed=True,group_display=facts);summary['actors'][name]=roles
                except BaseException as e:trial.receipt['failure']=f'{type(e).__name__}: {e}';raise
                finally:trial.receipt['finished_at']=time.time();trial.persist()
        summary['completed']=True
    except BaseException as e:summary['failure']=f'{type(e).__name__}: {e}';raise
    finally:
        summary['finished_at']=time.time();lab.private_write(output/'cohort.json',json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)


if __name__=='__main__':main()
