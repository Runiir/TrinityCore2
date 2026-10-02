"""Normal local chat through Laya-selected inputs and two owned client observations."""
import argparse,hashlib,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_macros import require
from .observation.journal import entries
from .world.buffer import Reader


def packets(session,since,token):
    rows=[]
    for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if row.get('session')==session and row.get('time',0)>=since and token.encode() in bytes.fromhex(row.get('body','')):
            rows.append({'time':row['time'],'direction':row['direction'],'name':row['name']})
    return rows


def suite(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700);cohort={'started_at':time.time(),'completed':False,'failure':None};trials={};sessions={}
    try:
        for name in ['primary','scout']:
            with actor(name):
                trials[name]=Trial(out/name);sessions[name]=actors.session_entry(trials[name].fixture)['session'];trials[name].clean_panels()
                s,_=trials[name].observe('fixture')
                if 'chat_probes' not in s:raise RuntimeError('read-only chat observer is missing')
        nonce=hashlib.sha256(str(out).encode()).hexdigest()[:8]
        cases=[('say','/say','SAY',False),('yell','/yell','YELL',False),('emote','/em','EMOTE',False),
            ('raid','/raid','RAID',True),('raid_warning','/rw','RAID_WARNING',True),('whisper','/w Harnesstwo','WHISPER',True)]
        for label,command,suffix,peer in cases:
            token='TC442UI:'+label+'_'+nonce;since=time.time()
            with actor('primary'):
                t=trials['primary'];actions={
                    'target':{'kind':'chat','value':command+' '+token,'description':f'Type {command} followed by the test message to send a {label.replace("_"," ")}.'},
                    'map':{'kind':'key','value':'m','description':'Open the world map.'},
                    'friends':{'kind':'key','value':'o','description':'Open the friends window.'}}
                def outcome(b,a,s):
                    rows=packets(sessions['primary'],since,token)
                    request=any(x['direction']=='from_client' and x['name']=='CMSG_CHAT_MESSAGE_'+suffix for x in rows)
                    native=any(x['direction']=='from_native' and x['name']=='SMSG_MESSAGECHAT' for x in rows)
                    event='CHAT_MSG_WHISPER_INFORM' if label=='whisper' else 'CHAT_MSG_'+suffix
                    events={event,event+'_LEADER'}
                    visible=any(x['text']==token and x['event'] in events for x in a.get('chat_probes',[]))
                    return {'status':'chat_send_pass' if request and native and visible else ('controller_failure' if s!='target' else 'client_or_protocol_failure'),
                        'oracle':{'client_request':request,'native_delivery':native,'visible_message':visible,'packets':rows,'expected_events':sorted(events)}}
                require(t.step('chat.'+label,'Send the test message as a '+label.replace('_',' ')+(' to Harnesstwo.' if label=='whisper' else '.'),actions,outcome,diagnostic_action='target'),'chat_send_pass')
            if peer:
                with actor('scout'):
                    t=trials['scout'];s,frame=t.observe(label+'_received');rows=packets(sessions['scout'],since,token)
                    visible=any(x['text']==token and x['event'] in {'CHAT_MSG_'+suffix,'CHAT_MSG_'+suffix+'_LEADER'} for x in s.get('chat_probes',[]))
                    native=any(x['direction']=='from_native' and x['name']=='SMSG_MESSAGECHAT' for x in rows)
                    row={'id':'chat.receive.'+label,'time':time.time(),'status':'chat_receive_pass' if visible and native else 'client_or_protocol_failure',
                        'selection_source':'read_only_owned_peer_oracle','oracle':{'visible_message':visible,'native_delivery':native,'packets':rows},'frame':frame}
                    t.receipt['cases'].append(row);t.persist();require(row,'chat_receive_pass')
        cohort['completed']=True
        for t in trials.values():t.receipt['completed']=True
    except Exception as e:cohort['failure']=str(e)
    finally:
        for name,t in trials.items():
            with actor(name):
                try:t.clean_panels()
                except Exception as e:t.receipt['cleanup_failure']=str(e)
            t.receipt['failure']=cohort['failure'];t.receipt['finished_at']=time.time();t.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n');print(json.dumps(cohort))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();suite(a.output)


if __name__=='__main__':main()
