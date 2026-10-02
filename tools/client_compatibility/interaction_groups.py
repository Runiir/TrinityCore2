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


def native_group():
    with lab.connection() as con,con.cursor() as q:
        q.execute('SELECT g.guid,g.leaderGuid,g.groupType FROM client442_characters.groups g JOIN client442_characters.group_member m ON m.guid=g.guid WHERE m.memberGuid=1')
        group=q.fetchone()
        if group:
            q.execute('SELECT memberGuid FROM client442_characters.group_member WHERE guid=%s',(group[0],))
            return {'guid':group[0],'leader':group[1],'type':group[2],'members':sorted(x[0] for x in q.fetchall())}
    return None


def conversion_oracle(after,correct,raid):
    group=native_group();native=bool(group and bool(group['type']&2)==raid and group['members']==[1,2])
    visible=after['group']['raid']==raid and after['group']['members']==2
    return {'status':'group_conversion_pass' if visible and native else ('controller_failure' if not correct else 'client_or_protocol_failure'),
        'oracle':{'native_group':group,'visible_group':after['group']}}


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
    for raid,label in [(True,'Raid'),(False,'Party')]:
        require(click_case(trial,'raid.convert_'+('from_party' if raid else 'to_party'),'Convert this group to a '+label+'.',
            lambda c:c['name']=='RaidFrameConvertToRaidButton',lambda b,a,s:conversion_oracle(a,s,raid)),'group_conversion_pass')
        with actor('scout'):
            peer=Trial(trial.out/('scout_'+label.lower()))
            try:
                peer_state,_=peer.observe('conversion_roster')
                if peer_state['group']['raid']!=raid or peer_state['group']['members']!=2:raise RuntimeError('second client group disagrees after conversion')
                peer.receipt['group']=peer_state['group'];peer.receipt['completed']=True
            except Exception as e:peer.receipt['failure']=str(e);raise
            finally:peer.receipt['finished_at']=time.time();peer.persist()
    trial.receipt['native_after_conversions']=native_group()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();trial=Trial(a.output)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        trial.receipt['finished_at']=time.time();trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
