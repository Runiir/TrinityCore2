"""Two-owned-client ready checks using the normal raid controls and buttons."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab,actors
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import click_case
from .interaction_macros import require
from .observation.journal import entries,Cursor
from .world.buffer import Reader


def round_check(output,ready):
    output.mkdir(exist_ok=False,parents=True,mode=0o700)
    summary={'started_at':time.time(),'completed':False,'failure':None};sessions=[]
    try:
        with actor('primary'):
            t=Trial(output/'start');sessions.append(actors.session_entry(t.fixture)['session'])
            try:
                t.clean_panels();s,_=t.observe('fixture')
                if not s['group']['leader'] or s['group']['members']!=2:raise RuntimeError('two-owned-member leader required')
                if not s['raid_profile']['expanded']:
                    require(click_case(t,'raid.expand','Expand the raid controls.',lambda c:c['name']=='CompactRaidFrameManagerToggleButton',
                        lambda b,a,s:{'status':'panel_open_pass' if a['raid_profile']['expanded'] else 'controller_failure'}),'panel_open_pass')
                require(click_case(t,'raid.ready_check_start','Start a ready check for your group.',
                    lambda c:c['name']=='CompactRaidFrameManagerDisplayFrameLeaderOptionsInitiateReadyCheck',
                    lambda b,a,s:{'status':'ready_check_start_pass' if a.get('ready_check') or a.get('ready_status')=='ready' else
                        ('controller_failure' if not s else 'client_or_protocol_failure')}),'ready_check_start_pass')
                t.receipt['completed']=True
            except Exception as e:t.receipt['failure']=str(e);raise
            finally:t.receipt['finished_at']=time.time();t.persist()
        with actor('scout'):
            t=Trial(output/'answer');sessions.append(actors.session_entry(t.fixture)['session'])
            try:
                s,_=t.observe('received')
                if not s.get('ready_check'):raise RuntimeError('peer ready-check dialog is absent')
                name='ReadyCheckFrame'+('Yes' if ready else 'No')+'Button'
                require(click_case(t,'raid.ready_check_answer',('Confirm that you are ready.' if ready else 'Report that you are not ready.'),
                    lambda c:c['name']==name,
                    lambda b,a,s:{'status':'ready_check_answer_pass' if s and not a.get('ready_check') else
                        ('controller_failure' if not s else 'client_or_protocol_failure')}),'ready_check_answer_pass')
                t.receipt['completed']=True
            except Exception as e:t.receipt['failure']=str(e);raise
            finally:t.receipt['finished_at']=time.time();t.persist()
        confirmations=[];finished=False;response_sent=False
        for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
            if row.get('session') not in sessions or row.get('time',0)<summary['started_at']:continue
            if row.get('direction')=='from_client' and row.get('name')=='CMSG_READY_CHECK_RESPONSE' and row.get('session')==sessions[1]:response_sent=True
            if row.get('direction')=='from_native' and row.get('name')=='MSG_RAID_READY_CHECK_CONFIRM':
                r=Reader(bytes.fromhex(row['body']));guid,value=r.unpack('QB');r.end()
                confirmations.append({'guid':guid,'ready':bool(value),'time':row['time']})
            if row.get('direction')=='to_client' and row.get('name')=='SMSG_READY_CHECK_COMPLETED':finished=True
        summary.update(native_confirmations=confirmations,client_response_sent=response_sent,bridge_finished=finished)
        if not response_sent or not any(r['guid']==2 and r['ready']==ready for r in confirmations) or not finished:
            raise RuntimeError('client response, native peer confirmation or bridge completion is missing')
        with actor('primary'):
            t=Trial(output/'completed');s,_=t.observe('completion')
            t.receipt['completed']=not s.get('ready_check');t.receipt['finished_at']=time.time();t.persist()
            if s.get('ready_check'):raise RuntimeError('leader ready-check frame did not close after completion')
        summary['completed']=True
    except Exception as e:summary['failure']=str(e)
    finally:summary['finished_at']=time.time();lab.private_write(output/'cohort.json',json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout-only',action='store_true');a=p.parse_args()
    if a.timeout_only:timeout_check(a.output);return
    for label,ready in [('ready',True),('not_ready',False)]:
        if not round_check(a.output/label,ready)['completed']:break


def timeout_check(output):
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    summary={'started_at':time.time(),'completed':False,'failure':None};trials={};sessions={}
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl');completion=set();answers=[]
    try:
        for name in ['primary','scout']:
            with actor(name):
                trials[name]=Trial(output/name);sessions[name]=actors.session_entry(trials[name].fixture)['session']
                trials[name].clean_panels()
        with actor('primary'):
            t=trials['primary'];s,_=t.observe('fixture')
            if not s['raid_profile']['expanded']:
                require(click_case(t,'raid.timeout.expand','Expand raid controls.',lambda c:c['name']=='CompactRaidFrameManagerToggleButton',
                    lambda b,a,s:{'status':'panel_open_pass' if a['raid_profile']['expanded'] else 'controller_failure'}),'panel_open_pass')
            require(click_case(t,'raid.timeout.start','Start a ready check and wait for unanswered members.',
                lambda c:c['name']=='CompactRaidFrameManagerDisplayFrameLeaderOptionsInitiateReadyCheck',
                lambda b,a,s:{'status':'ready_check_start_pass' if a.get('ready_check') else ('controller_failure' if not s else 'client_or_protocol_failure')}),'ready_check_start_pass')
        with actor('scout'):
            s,_=trials['scout'].observe('unanswered_dialog')
            if not s.get('ready_check'):raise RuntimeError('peer dialog is absent before timeout')
        deadline=time.monotonic()+40
        while time.monotonic()<deadline and completion!=set(sessions.values()):
            for r in cursor.poll():
                if r.get('time',0)<summary['started_at'] or r.get('session') not in sessions.values():continue
                if r['name']=='CMSG_READY_CHECK_RESPONSE' and r['direction']=='from_client':answers.append(r['session'])
                if r['name']=='SMSG_READY_CHECK_COMPLETED' and r['direction']=='to_client':completion.add(r['session'])
            if completion!=set(sessions.values()):time.sleep(.5)
        if completion!=set(sessions.values()) or answers:raise RuntimeError('unanswered check did not complete cleanly on both owned sessions')
        for name,t in trials.items():
            with actor(name):
                s,_=t.observe('timeout_finished')
                if s.get('ready_check'):raise RuntimeError(name+' ready-check dialog remained after timeout')
                t.receipt['completed']=True
        summary.update(completed=True,client_responses=answers,completed_sessions=sorted(completion))
    except Exception as e:summary['failure']=str(e)
    finally:
        for t in trials.values():t.receipt['finished_at']=time.time();t.persist()
        summary['finished_at']=time.time();lab.private_write(output/'cohort.json',json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))


if __name__=='__main__':main()
