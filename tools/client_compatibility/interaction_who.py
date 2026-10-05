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
from .interaction_operations import controls
from .interaction_observation import read_current_page
from . import interaction_who_wire as wire

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


def who_state(t,label):
    state,frame=read_current_page(t,label,'who',lambda s:isinstance(s.get('who_probe'),dict))
    t.receipt.setdefault('who_details',[]).append({'label':label,'state':state,'frame':frame});t.persist()
    return state['who_probe']


def check_deployed_baseline(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires the owned closed unmapped Who probe')
    old=json.loads(path.read_text());current=t.receipt
    if (old.get('completed') is not False or not old.get('finished_at') or
        old.get('failure')!='RuntimeError: operation did not advance: friends.who_search_probe client_or_protocol_failure' or
        old.get('actor')!=current['actor'] or old.get('original_who_text')!='' or
        not any(c.get('id')=='fixture.who.restore_text' and c.get('status')=='ui_edit_pass' for c in old.get('cases',[])) or
        any(old.get('runtime',{}).get(k)!=current['runtime'][k] for k in ('worldserver','client')) or
        old.get('runtime',{}).get('modern_world')==current['runtime']['modern_world'] or
        any(not old.get(k,{}).get('checks') or not all(old[k]['checks'].values()) for k in
            ('bridge_native_restoration','friend_restoration'))):
        raise RuntimeError('Who deployment baseline, closed cleanup or owned lifetime differs')
    keys=('native_baseline','original_social','original_public_friends','original_inventory',
        'original_quest_log','original_native_quests','original_group','offline_owned_dwarf')
    checks={k:current.get(k)==old.get(k) for k in keys}
    t.receipt['deployed_fixture_checks']=checks
    t.receipt['baseline_source']={'file':str(path),'sha256':lab.sha256(path)};t.persist()
    if not all(checks.values()):raise RuntimeError('Who deployment did not preserve the pre-repair fixture')


def suite(t,path):
    baseline(t,observer_version=123);packets=Packets(t.receipt['session']);original=None
    check_deployed_baseline(t,path)
    t.receipt.update(raw_who_capture_available=True,qualified_scope=
        'One stock owned-primary name search and exact native-backed result. No race filters, cross-realm/addon queries, sorting, selection, invitations or whispers.');t.persist()
    try:
        open_friends(t,'fixture.who.open');who_open(t,packets)
        field=target(t,'fixture.who.original',lambda c:c['name']=='WhoFrameEditBox' and c['kind']=='EditBox')
        if field['text']!='':raise RuntimeError('Who suite requires the original empty query field')
        original='';t.receipt['original_who_text']=original;t.persist()
        before=who_state(t,'who_before_search')
        require(edit(t,'fixture.who.query','Enter the exact owned primary-character name filter.',
            lambda c:c['name']=='WhoFrameEditBox',QUERY),'ui_edit_pass')
        started=time.time()
        def reply(a):return packets.has(started,'SMSG_WHO','to_client')
        def outcome(b,a,s):
            rows=[r for r in packets.since(started) if r['name'] in ('CMSG_WHO','SMSG_WHO')]
            checks,detail=wire.checks(rows);visible=who_state(t,'who_after_search')
            entries=visible.get('rows') or []
            def own_name(name):return name in ('Harnessone','Harnessone-Client442Lab')
            checks.update(ordinary_refresh_click=s,public_api_ready=visible.get('ready') is True,
                public_exact_count=visible.get('count')==visible.get('total')==1 and len(entries)==1 and
                    visible.get('rows_truncated') is False,
                public_owned_name_level=len(entries)==1 and own_name(entries[0].get('fullName')) and entries[0].get('level')==85,
                public_owned_class_race_zone=len(entries)==1 and entries[0].get('filename')=='WARRIOR' and
                    entries[0].get('raceStr')=='Human' and entries[0].get('classStr')=='Warrior' and entries[0].get('area')=='Badlands',
                stock_owned_row=len(entries)==1 and own_name(entries[0].get('stock',{}).get('name')) and
                    entries[0].get('stock',{}).get('level')=='85' and entries[0].get('stock',{}).get('class')=='Warrior',
                one_result_event=visible.get('event_count')==before.get('event_count',-1)+1,
                query_unchanged=visible.get('query')==QUERY,stock_window='FriendsFrame' in a['panels'],
                original_social_unchanged=social()==t.receipt['original_social'],chat_closed=not a.get('chat_edit_open'),
                clean=not a.get('lua_errors') and not a.get('blocked_actions'))
            t.receipt['who_outcome']={'checks':checks,'wire':detail,'public':visible};t.persist()
            return {'status':'owned_who_search_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'wire':detail,'packets':rows,'public':visible}}
        result=click(t,'friends.who_search','Submit one stock Refresh for the owned character name.',
            lambda c:c['name']=='WhoFrameWhoButton' and c['text']=='Refresh',outcome,await_state=reply)
        state,frame=t.observe('who_result');t.receipt['who_result']={'state':state,'frame':frame};t.persist()
        require(result,'owned_who_search_pass')
    finally:
        if original is not None:
            require(edit(t,'fixture.who.restore_text','Restore the original empty stock Who field.',
                lambda c:c['name']=='WhoFrameEditBox',original),'ui_edit_pass')
        cleanup(t);restored(t,t.receipt)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['probe','suite'],default='probe');p.add_argument('--baseline-source',type=Path);a=p.parse_args()
    if a.mode=='suite' and not a.baseline_source:p.error('suite requires the closed pre-repair baseline source')
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:(suite(t,a.baseline_source) if a.mode=='suite' else probe(t));t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
