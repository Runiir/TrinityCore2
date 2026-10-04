"""Owned player context menu reached by an observed physical right click."""
import argparse
import json
from pathlib import Path
import time
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,point,click_case
from .interaction_macros import require
from .interaction_groups import conversion_oracle,native_group
from .interaction_social import actor,friend_oracle


def suite(trial):
    trial.clean_panels();state,_=trial.observe('group_fixture')
    if state['group']['members']!=2 or set(state['group']['names'])!={'Harnessone','Harnesstwo'}:
        raise RuntimeError('context-menu trial requires the two-owned-character group')
    rows=controls(trial);player=next((c for c in rows if c['name']=='PlayerFrame'),None)
    if player is None:raise RuntimeError('owned player frame is not observed')
    open_menu(trial,player,'initial')
    rows=controls(trial);lab.private_write(trial.out/'player_menu_controls.json',json.dumps(rows,indent=2)+'\n')
    if state['group']['raid']:
        require(click_case(trial,'raid.convert_to_party','Convert this raid into a party.',lambda c:c['text']=='Convert To Party',
            lambda b,a,s:conversion_oracle(a,s,False)),'group_conversion_pass')
        verify_peer(trial,'party',2,False)
        open_menu(trial,player,'leave')
    require(click_case(trial,'party.leave','Leave the current party.',lambda c:c['text'].lower()=='leave party',
        lambda b,a,s:{'status':'group_leave_pass' if a['group']['members']==0 and native_group() is None else ('controller_failure' if not s else 'client_or_protocol_failure'),
            'oracle':{'native_group':native_group(),'visible_group':a['group']}}),'group_leave_pass')
    verify_peer(trial,'solo',0,False);trial.clean_panels()
    def removed(b,a,s):
        facts=friend_oracle(trial,a,False)
        return {'status':'friend_remove_pass' if facts['matches'] else ('controller_failure' if s!='a' else 'client_or_protocol_failure'),'oracle':facts}
    require(trial.step('friends.remove_friend','Remove Harnesstwo from your friends list.',{
        'a':{'kind':'chat','value':'/removefriend Harnesstwo','description':'Type /removefriend Harnesstwo to remove this owned friend.'},
        'b':{'kind':'chat','value':'/invite Harnesstwo','description':'Type /invite Harnesstwo to invite this owned character to a party.'},
        'c':{'kind':'key','value':'o','description':'Press O to open friends.'}},removed),'friend_remove_pass')


def open_menu(trial,player,label):
    require(trial.step('ui_misc.player_context_menu.'+label,'Open your player portrait context menu.',{
        'a':{'kind':'click','value':point(player),'button':3,'hold':.4,'description':'Right-click your visible player portrait to open its context menu.'},
        'b':{'kind':'key','value':'o','description':'Press O to open friends and social.'},
        'c':{'kind':'key','value':'Escape','description':'Press Escape to open the game menu.'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'ContextMenu' in a['panels'] else ('controller_failure' if s!='a' else 'adapter_observation_missing'),
            'oracle':{'qualified_scope':'visible player context menu'}},diagnostic_action='a',
        await_state=lambda s:'ContextMenu' in s['panels']),'panel_open_pass')


def verify_peer(trial,label,members,raid):
    with actor('scout'):
        peer=Trial(trial.out/('scout_'+label))
        try:
            state,_=peer.observe('group')
            if state['group']['members']!=members or state['group']['raid']!=raid:raise RuntimeError('second client group disagrees')
            peer.receipt.update(group=state['group'],completed=True)
        except Exception as e:peer.receipt['failure']=str(e);raise
        finally:peer.receipt['finished_at']=time.time();peer.persist()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();trial=Trial(a.output)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at']=time.time();trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
