"""Verify the actual remote primary-combat archive and its accepted packet proofs."""
import argparse,hashlib,json,tarfile,time
from pathlib import Path
from . import lab_runtime as lab
from .review_hunter_rename_checkpoint import DigestReader
from .review_hunter_stable_checkpoint import require
from .melee_result_evidence import pairs,public_events
from .primary_range_feedback_evidence import stock_range_error
from .world.objects import INDEX


def packet_key(p):return tuple(p.get(k) for k in ('session','time','direction','name','body'))


def checks(e,name,count):
    require(len(e.get(name,{}))==count and all(e[name].values()),name+' differs')


def proof(episodes,packets):
    m=episodes['primary_melee_damage01/episode.json'];r=episodes['primary_range_error04/episode.json']
    for e,phase in ((m,'primary_melee_damage_verified'),(r,'primary_range_feedback_verified')):
        require(e.get('completed') is True and e.get('failure') is None and e.get('phase')==phase and
            e['actor']['guid']==1 and e['actor']['actor']=='primary' and e['actor']['level']==85 and
            e.get('custom_script_permission')=='blocked_by_user','primary episode is not whole accepted')
        checks(e,'restoration_checks',10)
        require(all(packet_key(p) in packets for p in e['packets']),'accepted primary packet absent from actual archive')
    checks(m,'combat_checks',13);checks(r,'range_checks',10)
    e=episodes['primary_combat_entry01/episode.json'];checks(e,'reentry_checks',15)
    fresh=episodes['primary_combat_entry03/episode.json'];checks(fresh,'reentry_checks',15)
    require(e.get('completed') is True and e.get('failure') is None and fresh.get('completed') is True and
        fresh.get('failure') is None and m['session']==e['session'] and r['session']==fresh['session'] and
        fresh['started_at']>m['finished_at'] and m['runtime']==r['runtime']==fresh['runtime'],
        'normal fresh primary login lineage differs')
    target=m['first_health']['native'];hits,orphans=pairs(m['packets'],1,target['guid'],0)
    require(hits and not orphans and all(p['client'] for p in hits),'primary native/client swing proof differs')
    damage=sum(h['expected']['damage']-max(0,h['expected']['overkill']) for h in hits)
    require(damage==15 and target['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]==0,'primary clipped health loss differs')
    public=public_events(m['public']['melee_probe'],m['cases'][0]['before']['owner_melee']['event_sequence'],
        hits,e['state']['guid'],m['events'][0]['destination_guid'])
    require(public,'primary stock SWING_DAMAGE absent')
    require(r['public_errors'] and all(stock_range_error(v) for v in r['public_errors']) and
        not any(stock_range_error(v) for v in r['cases'][0]['before'].get('errors',[])),
        'fresh stock range feedback differs')
    require(bool(r['error_pairs']),'native range error pair is absent')
    for p in r['error_pairs']:
        require(p['native']['name']=='SMSG_ATTACKSWING_NOTINRANGE' and p['native']['body']=='' and
            p['client'] and p['client']['name']=='SMSG_ATTACK_SWING_ERROR' and p['client']['body']=='00' and
            0<=p['client']['time']-p['native']['time']<2,'native/client range error differs')
    park=episodes['primary_combat_final_park01/episode.json'];checks(park,'checks',7)
    require(park.get('completed') is True and park.get('failure') is None and park['parked_native']['online']==0,
        'primary final parking differs')
    return {'owner':1,'session':m['session'],'melee_checks':13,'melee_restoration':10,
        'positive_swings':len(hits),'raw_damage':sum(h['expected']['damage'] for h in hits),'clipped_health_loss':damage,
        'range_checks':10,'range_restoration':10,'range_pairs':len(r['error_pairs']),
        'stock_range_error_code':265,'park_checks':7,'primary_offline':True}


def review(directory,output):
    directory=directory.resolve();output=output.resolve()
    require(directory.parent==lab.ROOT/'evidence' and output.is_relative_to(lab.ROOT/'evidence') and
        not output.is_relative_to(directory) and not output.exists(),'requires a new review outside the immutable batch')
    checkpoint=json.loads((directory/'checkpoint_receipt.json').read_text());pointer=checkpoint['file']+'.dvc'
    prefix=str(directory.relative_to(lab.ROOT))+'/'
    manifest=checkpoint['file_manifest']
    require(len({r['path'] for r in manifest})==len(manifest),'duplicate manifest path')
    selected={r['path']:r['sha256'] for r in manifest if r['path'].startswith(prefix) and Path(r['path']).suffix in ('.json','.png')}
    episodes={};seen=set();packets=set()
    import yaml
    from dvc.repo import Repo
    out=yaml.safe_load((lab.REPO/pointer).read_text())['outs'][0]
    require(out['size']==checkpoint['bytes'],'DVC remote object size differs')
    with Repo(str(lab.REPO)) as repo:
        odb=repo.cloud.get_remote_odb()
        with odb.fs.open(odb.oid_to_path(out['md5']),'rb',block_size=1024*1024,cache_type='none') as raw:
            reader=DigestReader(raw)
            with tarfile.open(fileobj=reader,mode='r|gz') as archive:
                for member in archive:
                    if member.name=='tracking/packets.jsonl':
                        with archive.extractfile(member) as f:
                            for line in f:
                                p=json.loads(line)
                                if p.get('session') in {episodes['primary_melee_damage01/episode.json']['session'],episodes['primary_range_error04/episode.json']['session']} and p.get('name') in ('CMSG_ATTACK_SWING','CMSG_ATTACK_STOP','SMSG_ATTACK_START',
                                    'SMSG_ATTACK_STOP','SMSG_ATTACKER_STATE_UPDATE','SMSG_ATTACKSWING_NOTINRANGE','SMSG_ATTACK_SWING_ERROR'):
                                    packets.add(packet_key(p))
                                    require(len(packets)<=4096,'primary archive combat packet bound exceeded')
                    if member.name not in selected:continue
                    require(member.isfile() and member.name not in seen,'duplicate or invalid selected archive member')
                    with archive.extractfile(member) as f:
                        if member.name.endswith('/episode.json'):
                            data=f.read();require(hashlib.sha256(data).hexdigest()==selected[member.name],'episode digest differs')
                            e=json.loads(data);require(e.get('finished_at') and isinstance(e.get('completed'),bool),'episode remains open')
                            episodes[member.name.removeprefix(prefix)]=e
                        else:require(hashlib.file_digest(f,'sha256').hexdigest()==selected[member.name],'member digest differs')
                    seen.add(member.name)
            while reader.read(1024*1024):pass
            require(reader.bytes==checkpoint['bytes'] and reader.digest.hexdigest()==checkpoint['sha256'] and seen==set(selected),
                'complete remote archive identity differs')
    result=proof(episodes,packets)
    report={'schema':'client442_primary_combat_archive_review_v1','reviewed_at':time.time(),'verified':True,
        'review_tool_sha256':lab.sha256(Path(__file__)),
        'pointer':pointer,'archive_sha256':checkpoint['sha256'],'archive_bytes':checkpoint['bytes'],
        'direct_remote_object':True,'local_archive_created':False,'qualification_added':False,'packet_proof':result,
        'receipts':[{'member':p,'sha256':h,'verified':True} for p,h in selected.items() if p.endswith('.json')],
        'frames':[{'member':p,'sha256':h,'verified':True} for p,h in selected.items() if p.endswith('.png')],
        'limits':'One primary in-range critter swing and one native out-of-range Parched Buzzard attempt; all earlier whole failures excluded. '
            'No general class abilities, monster combat or attack cadence qualification.'}
    lab.private_write(output,json.dumps(report,indent=2)+'\n')
    print(json.dumps({'verified':True,'remote':True,'receipts':len(report['receipts']),'frames':len(report['frames']),
        'bytes':checkpoint['bytes'],'packet_proof':result}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();review(a.directory,a.output)
