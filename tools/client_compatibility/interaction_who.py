"""Trace one stock owned-name Who search, then restore the original empty field."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_friend_notes import baseline
from .interaction_friends import open_friends,restored,social
from .interaction_friend_reads import who_open,cleanup
from .interaction_control_target import target,edit,click
from .interaction_macros import require
from .interaction_lifecycle import Packets
from .observation.journal import Cursor

QUERY='n-Harnessone'


class WhoMetadata:
    def __init__(self):
        self.cursor=Cursor(lab.ROOT/'logs/modern_world.jsonl');self.rows=[]
        for _ in self.cursor.poll():pass

    def since(self,started):
        # WHO metadata is public. Keep all observed session IDs so a separate
        # instance-channel ID cannot silently masquerade as a missing request.
        self.rows.extend(r for r in self.cursor.poll() if r.get('name') in ('CMSG_WHO','SMSG_WHO'))
        return [r for r in self.rows if r.get('time',0)>=started]


def probe(t):
    baseline(t);packets=Packets(t.receipt['session']);metadata=WhoMetadata()
    t.receipt['qualified_scope']='One stock owned-name Who request diagnostic. No result acceptance without native request/reply, exact public rows and reviewed rendered stock results.'
    t.receipt['raw_who_capture_available']=False;t.persist()
    original=None
    try:
        open_friends(t,'fixture.who.open');who_open(t,packets)
        field=target(t,'fixture.who.original',lambda c:c['name']=='WhoFrameEditBox' and c['kind']=='EditBox')
        if field['text']!='':raise RuntimeError('Who probe requires the reviewed original empty field')
        original=field['text'];t.receipt['original_who_text']=original;t.persist()
        require(edit(t,'fixture.who.query','Enter the exact owned primary-character name filter.',
            lambda c:c['name']=='WhoFrameEditBox',QUERY),'ui_edit_pass')
        state,frame=t.observe('who_pending');t.receipt['who_pending']={'state':state,'frame':frame};t.persist()
        started=time.time()
        def reply(a):
            return any(r.get('direction')=='to_client' and r['name']=='SMSG_WHO' for r in metadata.since(started))
        def outcome(b,a,s):
            rows=metadata.since(started)
            checks={'ordinary_refresh_click':s,'owned_modern_request':any(r.get('session')==t.receipt['session'] and
                r['name']=='CMSG_WHO' and r.get('direction')=='from_client' for r in rows),
                'native_request':any(r['name']=='CMSG_WHO' and r.get('direction')=='to_native' for r in rows),
                'native_reply':any(r['name']=='SMSG_WHO' and r.get('direction')=='from_native' for r in rows),
                'modern_reply':reply(a),'stock_window':'FriendsFrame' in a['panels'],
                'social_unchanged':social()==t.receipt['original_social'],
                'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'who_transport_probe_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'metadata':rows,'raw_packet_bodies_available':False,
                    'search_or_results_qualified':False}}
        result=click(t,'friends.who_search_probe','Submit one observed stock Who Refresh click.',
            lambda c:c['name']=='WhoFrameWhoButton' and c['text']=='Refresh',outcome,await_state=reply)
        state,frame=t.observe('who_result');t.receipt['who_result']={'state':state,'frame':frame};t.persist()
        require(result,'who_transport_probe_pass')
    finally:
        if original is not None:
            require(edit(t,'fixture.who.restore_text','Restore the original empty stock Who field.',
                lambda c:c['name']=='WhoFrameEditBox',original),'ui_edit_pass')
        cleanup(t);restored(t,t.receipt)


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
