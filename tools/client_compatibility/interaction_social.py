"""Two-owned-account social trials; no public-player messaging or invitations."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require


@contextmanager
def actor(name):
    previous=os.environ.get('CLIENT442_ACTOR')
    os.environ['CLIENT442_ACTOR']=name
    try:yield
    finally:
        if previous is None:os.environ.pop('CLIENT442_ACTOR',None)
        else:os.environ['CLIENT442_ACTOR']=previous


def friend_oracle(trial,after,present):
    with lab.connection() as con,con.cursor() as cur:
        cur.execute('SELECT flags FROM client442_characters.character_social WHERE guid=%s AND friend=%s',
            (trial.fixture['guid'],2))
        row=cur.fetchone()
    native=bool(row and row[0]&1)
    visible=any(f['name']=='Harnesstwo' for f in (after.get('friends') or []))
    return {'native_friend':native,'visible_friend':visible,'matches':native==present and visible==present}


def suite(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    cohort={'schema':'client442_social_trial_v1','started_at':time.time(),'completed':False,'failure':None}
    trials={}
    try:
        for name in ['primary','scout']:
            with actor(name):
                trials[name]=Trial(out/name);actors.session_entry(trials[name].fixture)
                trials[name].clean_panels();state,_=trials[name].observe('fixture')
                if state['group']['members']:raise RuntimeError('social trial requires an empty owned group fixture')
                friends=state.get('friends') or []
                if friends:
                    if name!='primary' or any(f['name']!='Harnesstwo' for f in friends):
                        raise RuntimeError('social fixture contains an unrelated friend')
                    trials[name].execute({'kind':'chat','value':'/removefriend Harnesstwo'})
                    after,_=trials[name].observe('fixture_friend_removed')
                    if after.get('friends'):raise RuntimeError('owned friend fixture cleanup failed')
                    trials[name].receipt['cleanup'].append({'time':time.time(),'source':'code_fixture_cleanup',
                        'input':'/removefriend Harnesstwo','reason':'restore empty fixture left by the previous failed probe'})
        primary=trials['primary'];scout=trials['scout']
        with actor('primary'):
            def oracle(b,a,s):
                facts=friend_oracle(primary,a,True)
                return {'status':'friend_add_pass' if facts['matches'] else ('controller_failure' if s!='a' else 'client_or_protocol_failure'),'oracle':facts}
            require(primary.step('friends.add_friend','Add Harnesstwo to the friends list.',{
                'a':{'kind':'chat','value':'/friend Harnesstwo','description':'Type /friend Harnesstwo to add this owned character as a friend.'},
                'b':{'kind':'chat','value':'/invite Harnesstwo','description':'Type /invite Harnesstwo to invite this owned character to a party.'},
                'c':{'kind':'chat','value':'/removefriend Harnesstwo','description':'Type /removefriend Harnesstwo to remove this owned friend.'}},oracle),'friend_add_pass')
            require(primary.step('party.invite','Invite Harnesstwo to a party.',{
                'a':{'kind':'chat','value':'/invite Harnesstwo','description':'Type /invite Harnesstwo to invite this owned character to a party.'},
                'b':{'kind':'chat','value':'/friend Harnesstwo','description':'Type /friend Harnesstwo to add this owned character as a friend.'},
                'c':{'kind':'chat','value':'/removefriend Harnesstwo','description':'Type /removefriend Harnesstwo to remove this owned friend.'}},
                lambda b,a,s:{'status':'invitation_submitted' if s=='a' else 'controller_failure',
                    'oracle':{'qualified_scope':'input submitted; acceptance checked on the other client'}}),'invitation_submitted')
        with actor('scout'):
            require(click_case(scout,'party.accept','Accept Harnessone\'s party invitation.',
                lambda c:c['name']=='StaticPopup1Button1' and c['text']=='Accept',
                lambda b,a,s:{'status':'party_accept_pass' if a['group']['members']==2 and 'Harnessone' in a['group']['names'] else ('controller_failure' if not s else 'client_or_protocol_failure'),
                    'oracle':{'group':a['group']}}),'party_accept_pass')
        with actor('primary'):
            state,_=primary.observe('accepted_roster')
            if state['group']['members']!=2 or not state['group']['leader']:raise RuntimeError('leader roster disagrees after acceptance')
            primary.receipt['roster_after_accept']=state['group']
            require(primary.step('friends.open','Open the friends and social window.',{
                'a':{'kind':'key','value':'o','description':'Press O to open the friends and social window.'},
                'b':{'kind':'key','value':'c','description':'Press C to open equipment.'},
                'c':{'kind':'key','value':'m','description':'Press M to open the world map.'}},
                lambda b,a,s:{'status':'panel_open_pass' if 'FriendsFrame' in a['panels'] else 'controller_failure'}),'panel_open_pass')
            rows=controls(primary);lab.private_write(primary.out/'social_controls.json',json.dumps(rows,indent=2)+'\n')
        cohort['completed']=True
    except Exception as e:cohort['failure']=f'{type(e).__name__}: {e}'
    finally:
        for trial in trials.values():
            trial.receipt.update(finished_at=time.time(),completed=cohort['completed'],failure=cohort['failure']);trial.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n')
        print(json.dumps(cohort),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();suite(a.output)


if __name__=='__main__':main()
