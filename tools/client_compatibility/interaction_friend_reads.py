"""Check one owned offline friend list and open the stock Who pane without searching."""
import argparse,json,re,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_friend_notes import baseline
from .interaction_friends import social,public,open_friends,close_friends,restored
from .interaction_control_target import click,target
from .interaction_operations import controls,point
from .interaction_macros import require
from .interaction_lifecycle import Packets


def native_friend():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT s.friend,s.flags,s.note,p.name,p.level,p.online,p.account '
            'FROM client442_characters.character_social s JOIN client442_characters.characters p '
            'ON p.guid=s.friend WHERE s.guid=1 AND s.flags&1 ORDER BY s.friend')
        rows=q.fetchall()
    return json.loads(json.dumps(rows))


def friend_controls(t):
    rows=controls(t)
    return [c for c in rows if c['kind']=='Button' and
        re.fullmatch(r'FriendsFrameFriendsScrollFrameButton\d+',c['name'])]


def inspect_friend(t,label,hover=False):
    row=target(t,label+'.row',lambda c:c['kind']=='Button' and
        re.fullmatch(r'FriendsFrameFriendsScrollFrameButton\d+',c['name']) and c['text']=='Harnesstwo')
    def outcome(b,a,s):
        rows=friend_controls(t);native=native_friend()
        checks={'ordinary_pointer_input':s=='inspect',
            'owned_native_friend':native==[[2,1,'','Harnesstwo',1,0,2]],
            'public_exact_friend':public(a.get('friends'))==t.receipt['original_public_friends'],
            'friend_api_ready':a.get('friends_ready') is True,
            'one_stock_named_row':len(rows)==1 and rows[0]['text']=='Harnesstwo',
            'stock_window':'FriendsFrame' in a['panels'],'chat_closed':not a.get('chat_edit_open'),
            'original_social_unchanged':social()==t.receipt['original_social'],
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        if hover:checks['native_offline_and_public_disconnected']=(native[0][5]==0 and
            a['friends'][0]['connected'] is False and a['friends'][0]['level']==0)
        return {'status':'owned_offline_friend_read_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native_friend':native,'stock_rows':rows,
                'limits':'One current owned offline game-character entry. No online/offline transition, BNet account presence or server list refresh acceptance.'}}
    require(t.step(label,'Inspect only the current original owned offline friend.',
        {'inspect':{'kind':'hover','value':point(row) if hover else [1000,360]}},outcome,
        diagnostic_action='inspect'),'owned_offline_friend_read_pass')
    state,frame=t.observe(label.replace('.','_')+'_rendered')
    t.receipt.setdefault('friend_read_frames',[]).append({'case':label,'state':state,'frame':frame});t.persist()


def who_open(t,packets):
    started=time.time()
    def outcome(b,a,s):
        rows=controls(t);trace=[r for r in packets.since(started) if r['name'] in ('CMSG_WHO','SMSG_WHO')]
        checks={'ordinary_tab_click':bool(s),'stock_window':'FriendsFrame' in a['panels'],
            'who_edit_box':any(c['name']=='WhoFrameEditBox' and c['kind']=='EditBox' for c in rows),
            'who_refresh_button':any(c['name']=='WhoFrameWhoButton' and c['text']=='Refresh' and c['enabled'] for c in rows),
            'friends_list_hidden':not any(c['name']=='FriendsFrameAddFriendButton' for c in rows),
            'social_unchanged':social()==t.receipt['original_social'],
            'chat_closed':not a.get('chat_edit_open'),'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        t.receipt['who_open_controls']=rows;t.persist()
        return {'status':'stock_who_open_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':trace,'search_input_sent':False,'search_or_results_qualified':False}}
    require(click(t,'friends.who_open','Open the observed stock Who tab without entering a search.',
        lambda c:c['name']=='FriendsFrameTab2' and c['text']=='Who',outcome),'stock_who_open_pass')
    state,frame=t.observe('friends_who_open_rendered')
    t.receipt['who_open_frame']={'state':state,'frame':frame};t.persist()


def cleanup(t):
    state,_=t.observe('friend_read_cleanup_guard')
    if 'FriendsFrame' in state['panels']:
        require(click(t,'fixture.friend_reads.friends_tab','Restore the observed bottom Friends tab.',
            lambda c:c['name']=='FriendsFrameTab1' and c['text']=='Friends',lambda b,a,s:
            {'status':'friend_tab_restored' if s and any(c['name']=='FriendsFrameAddFriendButton'
                for c in controls(t)) else 'client_or_protocol_failure'}),'friend_tab_restored')
    close_friends(t)


def suite(t):
    baseline(t);t.receipt['qualified_scope']='One exact original offline friend list/current offline display, and stock Who pane opening only. No presence transition, Who search/results or other social qualification.'
    t.persist();packets=Packets(t.receipt['session'])
    try:
        open_friends(t,'fixture.friend_reads.open')
        inspect_friend(t,'friends.list');inspect_friend(t,'friends.offline_presence',hover=True)
        t.execute({'kind':'hover','value':[1000,360]});who_open(t,packets)
    finally:cleanup(t);restored(t,t.receipt)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
