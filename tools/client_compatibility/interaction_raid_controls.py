"""Live raid-frame controls exercised through model-selected physical inputs."""
import argparse
import json
from pathlib import Path
import time
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .interaction_group_state import capture
from .interaction_social import actor


def suite(trial):
    trial.clean_panels();before=capture(trial,'initial')
    if not before['unit_contents_valid'] or not before['visible_health_bars_valid']:
        raise RuntimeError('raid control fixture needs both owned members and rendered health bars')
    if not before['state']['group']['raid'] or not before['state']['group']['leader']:
        raise RuntimeError('raid control fixture requires the owned raid leader')
    if not before['state']['raid_profile']['expanded']:
        require(click_case(trial,'raid.open_main_screen_controls','Expand the main-screen raid controls.',
            lambda c:c['name']=='CompactRaidFrameManagerToggleButton',
            lambda b,a,s:{'status':'panel_open_pass' if a['raid_profile']['expanded'] else 'controller_failure'}),'panel_open_pass')
    rows=controls(trial);lab.private_write(trial.out/'initial_raid_controls.json',json.dumps(rows,indent=2)+'\n')
    expected={'CompactRaidFrameManagerDisplayFrameLockedModeToggle','CompactRaidFrameManagerDisplayFrameHiddenModeToggle'}
    observed=[c for c in rows if c['name'] in expected]
    if len(observed)!=2 or not all(c['text'] in ['Unlock','Lock','Hide','Show'] for c in observed):
        raise RuntimeError('raid control captions are missing before their first click')
    trial.receipt['initial_control_captions']=observed;trial.persist()
    baseline=before['state'];trial.receipt['control_baseline']=baseline;trial.persist()
    assistant=baseline['group']['everyone_assistant']
    for enabled in [not assistant,assistant]:
        def oracle(b,a,correct):
            visible=a['group'].get('everyone_assistant')==enabled
            return {'status':'assistant_change_pass' if visible else ('controller_failure' if not correct else 'client_or_protocol_failure'),
                'oracle':{'everyone_assistant':a['group'].get('everyone_assistant'),'expected':enabled}}
        require(click_case(trial,'raid.everyone_assistant.'+str(enabled).lower(),
            ('Enable' if enabled else 'Disable')+' Make everyone assistant.',
            lambda c:c['name']=='CompactRaidFrameManagerDisplayFrameEveryoneIsAssistButton',oracle),'assistant_change_pass')
        with actor('scout'):
            peer=Trial(trial.out/('scout_assistant_'+str(enabled).lower()))
            try:
                facts=capture(peer,'group')
                if facts['group'].get('everyone_assistant')!=enabled or not all(u['assistant']==enabled for u in facts['group']['units'] if not u['leader']):
                    raise RuntimeError('second client assistant flags disagree')
                peer.receipt.update(completed=True,group_display=facts)
            finally:peer.receipt['finished_at']=time.time();peer.persist()
    for option in ['locked','shown']:
        original=baseline['raid_profile'][option];values=[not original,original]
        control='CompactRaidFrameManagerDisplayFrame'+('Locked' if option=='locked' else 'Hidden')+'ModeToggle'
        for value in values:
            goal=('Unlock' if not value else 'Lock')+' raid-frame positioning.' if option=='locked' else ('Hide' if not value else 'Show')+' the raid health bars.'
            require(click_case(trial,'raid.profile.'+option+'.'+str(value).lower(),goal,lambda c:c['name']==control,
                lambda b,a,s:{'status':'raid_profile_change_pass' if a['raid_profile'].get(option)==value else
                    ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':a['raid_profile']}),'raid_profile_change_pass')
    final=capture(trial,'restored')
    if baseline['raid_profile']['shown'] and not final['visible_health_bars_valid']:
        raise RuntimeError('restored raid health bars are invalid')
    trial.receipt['restored_display']=final


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();trial=Trial(a.output)
    try:suite(trial);trial.receipt['completed']=True
    except BaseException as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at']=time.time();trial.persist()
        print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
