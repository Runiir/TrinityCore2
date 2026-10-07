"""Read the actual remote native-feedback archive and verify every batch JSON/PNG."""
import argparse,hashlib,json,struct,tarfile,time
from pathlib import Path
from types import SimpleNamespace
from . import lab_runtime as lab
from .review_hunter_rename_checkpoint import DigestReader
from .primary_range_feedback_evidence import stock_range_error
from .world.buffer import Reader
from .world.gameobjects import modern_guid
from .world import combat


def require(value,message):
    if not value:raise RuntimeError(message)


def packet_key(p):return tuple(p.get(k) for k in ('session','time','direction','name','body'))


def whole(e,key,count):
    require(e.get('completed') is True and e.get('failure') is None and e.get('finished_at'), 'episode is not whole accepted')
    require(len(e.get(key,{}))==count and all(e[key].values()),key+' differs')


def proof(data,packets,phase,digests=None):
    if phase=='integrity':return {'integrity_only':True,'gameplay_qualified':False}
    if phase=='owned-slot':
        from .hunter_slot_evidence import proof as slot_proof
        return slot_proof(data,digests,packets)
    if phase=='owned-pair':
        from .hunter_pair_evidence import proof as pair_proof
        return pair_proof(data,digests,packets)
    if phase=='owned-abandon-cancel':
        from .hunter_abandon_cancel_evidence import proof as cancel_proof
        return cancel_proof(data,digests,packets)
    if phase=='owned-abandon':
        from .hunter_abandon_evidence import proof as abandon_proof
        return abandon_proof(data,digests,packets['raw'],packets['events'])
    if phase=='owned-tame':
        from .hunter_tame_evidence import proof as tame_proof
        return tame_proof(data,digests,packets)
    if phase=='ability':
        from .primary_throw_checkpoint_evidence import proof as ability_proof
        return ability_proof(data,digests,packets)
    if phase=='pre':
        b=data['native_feedback_build01.json'];d=data['native_feedback_stage01/deployment.json']
        require(b['completed'] and b['jobs']==1 and b['available_memory_kib']>=6291456 and
            d['staged'] and d['binary_sha256']==b['binary_sha256'],'one-job native deployment build differs')
        require(all(data['native_feedback_stage01/'+a+'_before/episode.json']['completed'] for a in ('primary','scout')),
            'original offline actor baseline absent')
        return {'staged_only':True,'gameplay_qualified':False,'jobs':1,'binary_sha256':b['binary_sha256']}
    entry=data['primary_combat_entry01/episode.json'];whole(entry,'reentry_checks',15)
    deploy=data['native_feedback_deploy01/deployment.json']
    require(deploy['completed'] and deploy['native_restarted'] and deploy['bridge_unchanged'] and
        deploy['before']==deploy['after'] and entry['runtime']['worldserver']==deploy['native'],
        'accepted native deployment and new login lineage differs')
    ranges=[]
    for name in ('primary_range_error01','primary_range_error02'):
        e=data[name+'/episode.json'];whole(e,'range_checks',10);whole(e,'restoration_checks',10)
        staged=data[Path(e['source']['path']).parent.name+'/episode.json'];whole(staged,'checks',13)
        target=staged['target']['guid']
        requests=[p for p in e['packets'] if p['name']=='CMSG_ATTACK_SWING']
        native=[p for p in requests if p['direction']=='to_native']
        client=[p for p in requests if p['direction']=='from_client']
        require(len(native)==len(client)==1 and native[0]['body']==struct.pack('<Q',target).hex(),
            'one exact current native Attack request absent')
        r=Reader(bytes.fromhex(client[0]['body']));identity=r.guid();r.end()
        require(identity==modern_guid(target,0) and 0<=native[0]['time']-client[0]['time']<2,
            'owned modern Attack target differs')
        require(not any(p['name']=='SMSG_ATTACKER_STATE_UPDATE' or
            p['name']=='CMSG_CAST_SPELL' and p['direction']=='to_native' for p in e['packets']),
            'unexpected damage or native spell during range attempt')
        for opcode in ('SMSG_ATTACK_START','SMSG_ATTACK_STOP'):
            matches=[]
            for p in e['packets']:
                if p['name']!=opcode or p['direction']!='from_native':continue
                expected=combat.response(SimpleNamespace(character={'map':0}),opcode,bytes.fromhex(p['body']))[1].hex()
                matches.extend(c for c in e['packets'] if c['name']==opcode and c['direction']=='to_client' and
                    c['body']==expected and 0<=c['time']-p['time']<2)
            require(matches,'native/client attack lifecycle pair absent')
        require(e['actor']==entry['actor'] and e['runtime']==entry['runtime'] and e['session']==entry['session'] and
            e['custom_script_permission']=='blocked_by_user' and e['phase']=='primary_range_feedback_verified',
            'range actor, native epoch or script boundary differs')
        require(e['public_errors'] and all(stock_range_error(v) for v in e['public_errors']) and
            not any(stock_range_error(v) for v in (e['cases'][0]['before'].get('errors') or [])),
            'fresh stock range error absent')
        require(e['error_pairs'] and all(packet_key(p) in packets for p in e['packets']),
            'accepted range packets absent from actual remote tracking')
        for pair in e['error_pairs']:
            n,c=pair['native'],pair['client']
            require(n['name']=='SMSG_ATTACKSWING_NOTINRANGE' and n['body']=='' and n['direction']=='from_native' and
                c and c['name']=='SMSG_ATTACK_SWING_ERROR' and c['body']=='00' and c['direction']=='to_client' and
                native[0]['time']<=n['time'] and 0<=c['time']-n['time']<2,'exact native/client error pair differs')
        ranges.append(e)
    reload=data['primary_observer_reload01/episode.json'];whole(reload,'checks',13)
    require(ranges[0]['finished_at']<reload['started_at']<reload['finished_at']<ranges[1]['started_at'] and
        reload['runtime']==entry['runtime'] and ranges[0]['baseline']==ranges[1]['baseline'],
        'Stop/reload/restart lifecycle differs')
    park=data['primary_combat_final_park01/episode.json'];whole(park,'checks',7)
    require(park['parked_native']['online']==0,'primary final parking absent')
    return {'new_native_epoch':deploy['native'],'bridge_unchanged':True,'ordinary_login':True,
        'range_checks_each':10,'restoration_checks_each':10,'reload_checks':13,'park_checks':7,
        'fresh_native_error_pairs':[len(e['error_pairs']) for e in ranges],
        'stock_error_code':265,'primary_offline':True,'scripts_blocked':True}


def review(directory,output,phase):
    directory=directory.resolve();output=output.resolve()
    require(directory.parent==lab.ROOT/'evidence' and output.is_relative_to(lab.ROOT/'evidence') and
        not output.is_relative_to(directory) and not output.exists(),'requires new review outside immutable batch')
    cp=json.loads((directory/'checkpoint_receipt.json').read_text());pointer=cp['file']+'.dvc'
    prefix=str(directory.relative_to(lab.ROOT))+'/'
    manifest={r['path']:r for r in cp['file_manifest']}
    require(len(manifest)==len(cp['file_manifest']),'duplicate manifest')
    selected={p:r['sha256'] for p,r in manifest.items() if p.startswith(prefix) and Path(p).suffix in ('.json','.png')}
    import yaml
    from dvc.repo import Repo
    out=yaml.safe_load((lab.REPO/pointer).read_text())['outs'][0]
    require(out['size']==cp['bytes'],'remote object size differs')
    data={};seen=set();packets=set();abandon_events=set();abandon_instances=set()
    tame_tracking={'raw':set(),'packets':set(),'events':[],'instances':set()}
    with Repo(str(lab.REPO)) as repo:
        odb=repo.cloud.get_remote_odb()
        with odb.fs.open(odb.oid_to_path(out['md5']),'rb',block_size=1024*1024,cache_type='none') as raw:
            reader=DigestReader(raw)
            with tarfile.open(fileobj=reader,mode='r|gz') as archive:
                for member in archive:
                    if phase=='owned-tame' and member.name in ('tracking/events.jsonl','tracking/packets.jsonl',
                            'tracking/owned_tame_request_packets.jsonl'):
                        from .hunter_tame_evidence import collect
                        with archive.extractfile(member) as f:
                            collect(member.name,(json.loads(line) for line in f),data,tame_tracking)
                    if phase=='owned-abandon' and member.name in ('tracking/owned_pet_abandon_packets.jsonl','tracking/events.jsonl'):
                        e=data['hunter_abandon_confirm01/episode.json'];session=e['native_session']
                        entry=data['hunter_abandon_entry01/episode.json']
                        since=e['started_at'];until=e['finished_at']
                        destination=packets if member.name=='tracking/owned_pet_abandon_packets.jsonl' else abandon_events
                        with archive.extractfile(member) as f:
                            for line in f:
                                p=json.loads(line)
                                if (member.name=='tracking/events.jsonl' and p.get('event')=='instance_authenticated' and
                                    p.get('account_id')==entry['actor']['account_id'] and
                                    entry['started_at']<=p.get('time',0)<=entry['finished_at']):
                                    abandon_instances.add(p['session']);require(len(abandon_instances)<=1,'ambiguous owned Abandon instance')
                                sessions={session}|abandon_instances if member.name=='tracking/events.jsonl' else {session}
                                if p.get('session') in sessions and since<=p.get('time',0)<=until and p.get('name')=='CMSG_PET_ABANDON':
                                    destination.add(packet_key(p));require(len(destination)<=8,'disposable Abandon request bound exceeded')
                    if phase=='owned-abandon-cancel' and member.name=='tracking/events.jsonl':
                        session=data['hunter_abandon_entry01/episode.json']['native_session']
                        since=data['hunter_abandon_dialog03/episode.json']['started_at']
                        until=data['hunter_abandon_cancel02/episode.json']['finished_at']
                        with archive.extractfile(member) as f:
                            for line in f:
                                p=json.loads(line)
                                if p.get('session')==session and since<=p.get('time',0)<=until and p.get('name')=='CMSG_PET_ABANDON':
                                    packets.add(packet_key(p));require(len(packets)<=8,'Abandon event bound exceeded')
                    if phase in ('ability','owned-slot','owned-pair') and member.name=='tracking/packets.jsonl':
                        if phase=='ability':key='primary_faced_throw_native01/episode.json'
                        elif phase=='owned-slot':
                            from .hunter_slot_evidence import NAMES
                            key=NAMES['restore']+'/episode.json'
                        field='packets' if phase=='ability' else 'call_pet_packets'
                        if phase=='owned-pair':
                            from .hunter_pair_evidence import CLOSURE
                            refs=data[CLOSURE]['sources']
                            keys=[str(Path(refs[i]['path']).relative_to(directory)) for i in (3,5)]
                            wanted={packet_key(p) for k in keys for p in data[k][field]}
                        else:wanted={packet_key(p) for p in data[key][field]}
                        require(0<len(wanted)<=256,'ability outcome packet bound differs')
                        with archive.extractfile(member) as f:
                            for line in f:
                                p=json.loads(line);key=packet_key(p)
                                if key in wanted:packets.add(key)
                    if phase=='repeat' and member.name=='tracking/packets.jsonl':
                        session=data['primary_combat_entry01/episode.json']['session']
                        with archive.extractfile(member) as f:
                            for line in f:
                                p=json.loads(line)
                                if p.get('session')==session and p.get('name') in ('CMSG_ATTACK_SWING','CMSG_ATTACK_STOP',
                                    'SMSG_ATTACK_START','SMSG_ATTACK_STOP','SMSG_ATTACKER_STATE_UPDATE',
                                    'SMSG_ATTACKSWING_NOTINRANGE','SMSG_ATTACK_SWING_ERROR'):
                                    packets.add(packet_key(p));require(len(packets)<=4096,'combat archive packet bound exceeded')
                    if member.name not in selected:continue
                    require(member.isfile() and member.name not in seen,'duplicate or invalid selected member')
                    with archive.extractfile(member) as f:
                        if member.name.endswith('.json'):
                            body=f.read();require(hashlib.sha256(body).hexdigest()==selected[member.name],'JSON member digest differs')
                            data[member.name.removeprefix(prefix)]=json.loads(body)
                        else:require(hashlib.file_digest(f,'sha256').hexdigest()==selected[member.name],'PNG member digest differs')
                    seen.add(member.name)
            while reader.read(1024*1024):pass
    require(seen==set(selected) and reader.bytes==cp['bytes'] and reader.digest.hexdigest()==cp['sha256'],
        'actual remote compressed archive or complete member set differs')
    if phase=='owned-abandon':require(len(abandon_instances)==1,'fresh owned Abandon instance attribution absent')
    packet_proof=tame_tracking if phase=='owned-tame' else (
        {'raw':packets,'events':abandon_events} if phase=='owned-abandon' else packets)
    outcome=proof(data,packet_proof,phase,{p.removeprefix(prefix):sha for p,sha in selected.items()})
    d={'schema':'client442_native_feedback_remote_review_v1','reviewed_at':time.time(),
        'pointer':pointer,'archive_sha256':cp['sha256'],'bytes':reader.bytes,'actual_remote_verified':True,
        'complete_json_png_verified':True,'json_members':sum(p.endswith('.json') for p in selected),
        'png_members':sum(p.endswith('.png') for p in selected),'proof':outcome}
    lab.private_write(output,json.dumps(d,indent=2)+'\n');print(json.dumps(d),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--phase',choices=['pre','repeat','integrity','ability','owned-slot','owned-pair','owned-abandon-cancel','owned-abandon','owned-tame'],required=True)
    a=p.parse_args();review(a.directory,a.output,a.phase)
