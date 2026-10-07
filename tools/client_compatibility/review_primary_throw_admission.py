"""Validate a closed retained ability capture and reject broken admission variants."""
import argparse,copy,json,time
from pathlib import Path
from . import lab_runtime as lab
from .primary_throw_checkpoint_evidence import proof
from .review_native_feedback_checkpoint import packet_key
from .observation.journal import Cursor
from .world.buffer import Reader
from .world.native_objects import guid


def review(directory,output):
    directory=directory.resolve();output=output.resolve()
    if directory.parent!=lab.ROOT/'evidence' or not output.is_relative_to(directory) or output.exists():
        raise RuntimeError('requires a new local review in the owned open batch')
    data={str(p.relative_to(directory)):json.loads(p.read_text()) for p in directory.rglob('*.json')}
    digests={str(p.relative_to(directory)):lab.sha256(p) for p in directory.rglob('*') if p.is_file()}
    key='primary_faced_throw_native01/episode.json';e=data[key]
    wanted={packet_key(p) for p in e['packets']}
    packets={packet_key(p) for p in Cursor(lab.ROOT/'evidence/world_packets.jsonl').poll() if packet_key(p) in wanted}
    result=proof(data,digests,packets);guards=[]

    def reject(name,change):
        d=copy.deepcopy(data);h=digests.copy();p=packets.copy();change(d,h,p)
        try:proof(d,h,p)
        except (RuntimeError,ValueError,KeyError) as error:
            guards.append({'case':name,'rejected':True,'reason':str(error)})
        else:raise RuntimeError('invalid admission variant accepted: '+name)

    reject('whole_failed_cast',lambda d,h,p:d[key].update(completed=False))
    reject('whole_failed_park',lambda d,h,p:d['primary_combat_final_park01/episode.json'].update(failure='broken'))
    reject('missing_actual_tracking_packet',lambda d,h,p:p.remove(next(iter(p))))
    reject('changed_login',lambda d,h,p:d[key].update(session='different'))
    reject('changed_runtime',lambda d,h,p:d[key]['runtime']['worldserver'].update(pid=0))
    reject('wrong_facing_restore',lambda d,h,p:d[key]['facing_restoration'].update(restored=[0,0,0,0,0]))
    reject('missing_fixture_row_cleanup',lambda d,h,p:d[key]['facing_restoration'].update(removed=[]))
    reject('wrong_review_image',lambda d,h,p:h.update({'primary_faced_throw_stage01/review_ready.png':'0'*64}))
    reject('wrong_public_error',lambda d,h,p:d[key].update(public_errors=[{'code':51,'text':'Invalid target'}]))
    reject('missing_native_range_response',lambda d,h,p:d[key].update(packets=[r for r in d[key]['packets'] if r['name']!='SMSG_ATTACKSWING_NOTINRANGE']))

    def wrong_damage(d,h,p,modern):
        name='SMSG_SPELL_NON_MELEE_DAMAGE_LOG' if modern else 'SMSG_SPELLNONMELEEDAMAGELOG'
        rows=[r for r in d[key]['packets'] if r['name']==name]
        for row in rows:
            r=Reader(bytes.fromhex(row['body']))
            if modern:r.guid();r.guid();r.guid()
            else:
                guid(r)
                if guid(r)!=1 or r.unpack('I')!=(57755,):continue
                raw=bytearray.fromhex(row['body']);raw[r.pos]^=1;row['body']=raw.hex();return
            r.unpack('II');raw=bytearray.fromhex(row['body']);raw[r.pos]^=1;row['body']=raw.hex();return
        raise RuntimeError('positive capture lacks the owned damage packet')

    reject('wrong_native_damage',lambda d,h,p:wrong_damage(d,h,p,False))
    reject('wrong_client_damage',lambda d,h,p:wrong_damage(d,h,p,True))
    def public_damage(d,h,p):
        for event in d[key]['public_combat_log_after']['events']:
            if event['event']=='SPELL_DAMAGE':event['amount']+=1
    reject('wrong_public_damage',public_damage)
    reject('missing_stock_damage_text',lambda d,h,p:d['primary_stock_damage_log_open03/episode.json']['public'].update(recent_messages=[]))
    reject('wrong_general_restoration',lambda d,h,p:d['primary_stock_damage_log_restore01/episode.json']['public'].update(selected=2))
    reject('primary_still_online',lambda d,h,p:d['primary_combat_final_park01/episode.json']['parked_native'].update(online=1))
    report={'schema':'client442_primary_throw_local_review_v1','reviewed_at':time.time(),
        'actual_remote_verified':False,'local_tracking_verified':True,'proof':result,
        'guards':guards,'guard_count':len(guards),'all_guards_rejected':all(g['rejected'] for g in guards),
        'limits':'Local closure/negative controls only. Actual remote archive review remains required for admission.'}
    lab.private_write(output,json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();review(a.directory,a.output)
