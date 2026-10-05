"""Inspect the stock Ignore tab without changing the original social rows."""
import argparse,json,re,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_friend_notes import baseline
from .interaction_friends import social,open_friends,close_friends,restored
from .interaction_control_target import click
from .interaction_operations import controls
from .interaction_macros import require


def ignore_rows(rows):
    return [c for c in rows if re.fullmatch(r'FriendsFrameIgnoreButton\d+',c['name']) and
        c['kind']=='Button' and c['text']]


def ignore_tab(t,label):
    def outcome(b,a,s):
        rows=controls(t);state,frame=t.observe(label.replace('.','_')+'_rendered')
        checks={'ordinary_input':bool(s),'stock_friends':'FriendsFrame' in a['panels'],
            'ignore_add_control':any(c['name']=='FriendsFrameIgnorePlayerButton' and c['enabled'] for c in rows),
            'ignore_remove_control':any(c['name']=='FriendsFrameUnsquelchButton' for c in rows)}
        t.receipt.setdefault('ignore_tabs',[]).append({'checks':checks,'controls':rows,'state':state,'frame':frame})
        t.persist()
        return {'status':'ignore_tab_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks}}
    require(click(t,label,'Select the observed stock Ignore tab.',
        lambda c:c['name']=='FriendsTabHeaderTab2' and c['text']=='Ignore',outcome),'ignore_tab_pass')


def add_dialog(t,label):
    require(click(t,label,'Open the stock Ignore Player name dialog.',
        lambda c:c['name']=='FriendsFrameIgnorePlayerButton',lambda b,a,s:
        {'status':'ignore_dialog_open' if s and 'StaticPopup1' in a['panels'] else
            'client_or_protocol_failure'},await_state=lambda a:'StaticPopup1' in a['panels']),
        'ignore_dialog_open')
    rows=controls(t);state,frame=t.observe(label.replace('.','_')+'_rendered')
    contract=[c for c in rows if c['name'].startswith('StaticPopup1')]
    t.receipt.setdefault('ignore_dialogs',[]).append({'controls':contract,'state':state,'frame':frame})
    t.persist();return contract


def cleanup(t):
    state,_=t.observe('ignore_cleanup_guard')
    if 'StaticPopup1' in state['panels']:
        require(click(t,'fixture.ignore.cancel','Cancel the observed Ignore Player dialog.',
            lambda c:c['name']=='StaticPopup1Button2' and c['text']=='Cancel',lambda b,a,s:
            {'status':'ignore_dialog_cancelled' if s and 'StaticPopup1' not in a['panels'] else
                'client_or_protocol_failure'},await_state=lambda a:'StaticPopup1' not in a['panels']),
            'ignore_dialog_cancelled')
    if 'FriendsFrame' in state['panels']:
        require(click(t,'fixture.ignore.friends_tab','Restore the stock Friends subtab before closing.',
            lambda c:c['name']=='FriendsTabHeaderTab1' and c['text']=='Friends',lambda b,a,s:
            {'status':'friend_tab_restored' if s and any(c['name']=='FriendsFrameAddFriendButton'
                for c in controls(t)) else 'client_or_protocol_failure'}),'friend_tab_restored')
    close_friends(t)


def probe(t):
    baseline(t);t.receipt['qualified_scope']='Stock Ignore tab and name-dialog inspection/cancel only; no gameplay qualification.'
    t.persist()
    try:
        open_friends(t,'fixture.ignore.open');ignore_tab(t,'fixture.ignore.tab')
        rows=ignore_rows(t.receipt['ignore_tabs'][-1]['controls'])
        if rows or social()!=t.receipt['original_social']:
            raise RuntimeError('requires the preserved empty stock Ignore list')
        add_dialog(t,'fixture.ignore.dialog')
    finally:cleanup(t);restored(t,t.receipt)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:probe(t);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
