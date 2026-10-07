"""Stream the actual checkpoint object and prove a scoped owned stable opening."""
import argparse,hashlib,json,struct,tarfile,time
from pathlib import Path
from . import lab_runtime as lab
from .world.buffer import Writer
from .world.gameobjects import modern_guid
from .review_hunter_rename_checkpoint import DigestReader


def require(ok,reason):
    if not ok:raise RuntimeError(reason)


def packet_proof(e,packets):
    require(e.get('completed') is True and e.get('failure') is None and e.get('finished_at') and
        e.get('phase')=='hunter_stable_native_open_verified','stable episode is not whole accepted')
    for key,count in [('outcome_checks',9),('restoration_checks',13),('protected_checks',5)]:
        require(len(e.get(key,{}))==count and all(e[key].values()),'stable '+key+' differs')
    cfg=e['capture_config'];master=cfg['native_master_guid'];session=cfg['session']
    require(cfg['owner']==6 and e['native_session']==session and e['actor']['guid']==6 and
        e['actor']['class']==3 and e['capture_disarmed'] is True and
        0<cfg['expires_at']-cfg['created_at']<=60,'stable capture authority differs')
    require(master>>52==0xf13 and master>>32&0xfffff==6749,'stable native master differs')
    require(cfg['modern_master_guid']==list(modern_guid(master,0)),'stable modern master differs')
    catalog=struct.pack('<QBBiIII',master,1,20,0,4,42717,10)+b'Harnesswolf\0\x01'
    request=Writer().guid(*cfg['modern_master_guid']).finish().hex()
    native=0;reads=0
    for row in e['capture_packets']:
        require(row['session']==session and cfg['created_at']<=row['time']<=cfg['expires_at'],
            'stable packet is outside the exact capture')
        if (row['direction'],row['name'])==('from_native','MSG_LIST_STABLED_PETS'):
            require(row['body']==catalog.hex(),'native stable catalog differs');native+=1
        else:
            require((row['direction'],row['name'],row['body'])==
                ('from_client','CMSG_REQUEST_STABLED_PETS',request),'stable read identity differs');reads+=1
    require(native>0,'native stable reply is absent')
    pet=e['baseline_pets'][0];public=e['public_stable']
    require(len(e['baseline_pets'])==1 and (pet['id'],pet['owner'],pet['entry'],pet['name'],pet['renamed'])==
        (4,6,42717,'Harnesswolf',1),'retained named pet differs')
    observed=[{k:p.get(k) for k in ('slot','name','level','display_id')} for p in public['pets']]
    require(public['visible'] is True and public['selected']==1 and public['name']=='Harnesswolf' and public['stable_slots']==16 and
        observed==[{'slot':1,'name':'Harnesswolf','level':10,'display_id':pet['modelid']}] and
        public['events']['PET_STABLE_SHOW']['count']>0,'public stable opening differs')
    notify=Writer().guid(*cfg['modern_master_guid']).pack('i',22).bits(1,1).finish().hex()
    delivered=[p for p in packets if p.get('session')==session and p.get('direction')=='to_client' and
        p.get('name')=='SMSG_NPC_INTERACTION_OPEN_RESULT' and
        cfg['created_at']<=p.get('time',0)<=cfg['expires_at'] and p.get('body')==notify]
    require(bool(delivered),'archived exact stable notification is absent')
    cases=[c for c in e['cases'] if c['id']=='pets.stable_open']
    require(len(cases)==1 and cases[0]['status']=='native_owned_stable_open_pass','stable case is not accepted')
    return {'native_catalogs':native,'client_reads':reads,'delivered_notifications':len(delivered),
        'outcome_checks':9,'restoration_checks':13,'protected_checks':5,'pet_number':4,'native_capacity':16}


def review(directory,output,accepted=None,remote=False):
    directory=directory.resolve();output=output.resolve()
    require(directory.parent==lab.ROOT/'evidence' and output.is_relative_to(lab.ROOT/'evidence') and
        not output.is_relative_to(directory) and not output.exists(),'review output must be new and outside the closed batch')
    checkpoint=json.loads((directory/'checkpoint_receipt.json').read_text());pointer=checkpoint['file']+'.dvc'
    prefix=str(directory.relative_to(lab.ROOT))+'/'
    selected={r['path']:r['sha256'] for r in checkpoint['file_manifest'] if r['path'].startswith(prefix) and
        Path(r['path']).suffix in ('.json','.png')}
    require(len({r['path'] for r in checkpoint['file_manifest']})==len(checkpoint['file_manifest']),
        'duplicate checkpoint manifest path')
    episodes={};seen=set();packets=[]
    def inspect(raw):
        reader=DigestReader(raw)
        with tarfile.open(fileobj=reader,mode='r|gz') as archive:
            for member in archive:
                if member.name=='tracking/packets.jsonl':
                    with archive.extractfile(member) as f:
                        for line in f:
                            row=json.loads(line)
                            if (row.get('direction'),row.get('name'))==('to_client','SMSG_NPC_INTERACTION_OPEN_RESULT'):
                                packets.append(row)
                if member.name not in selected:continue
                require(member.isfile() and member.name not in seen,'duplicate or invalid archive member')
                with archive.extractfile(member) as f:
                    if member.name.endswith('/episode.json'):
                        data=f.read();require(hashlib.sha256(data).hexdigest()==selected[member.name],'episode digest differs')
                        e=json.loads(data);require(e.get('finished_at') and isinstance(e.get('completed'),bool),'episode is open')
                        episodes[member.name.removeprefix(prefix)]=e
                    else:require(hashlib.file_digest(f,'sha256').hexdigest()==selected[member.name],'member digest differs')
                seen.add(member.name)
        while reader.read(1024*1024):pass
        require(reader.bytes==checkpoint['bytes'] and reader.digest.hexdigest()==checkpoint['sha256'] and
            seen==set(selected),'complete archive identity or member set differs')
    if remote:
        import yaml
        from dvc.repo import Repo
        out=yaml.safe_load((lab.REPO/pointer).read_text())['outs'][0]
        require(out['size']==checkpoint['bytes'],'DVC object size differs')
        with Repo(str(lab.REPO)) as repo:
            odb=repo.cloud.get_remote_odb()
            with odb.fs.open(odb.oid_to_path(out['md5']),'rb',block_size=1024*1024,cache_type='none') as raw:inspect(raw)
    else:
        with (lab.REPO/checkpoint['file']).open('rb') as raw:inspect(raw)
    proof=packet_proof(episodes[accepted],packets) if accepted else None
    report={'schema':'client442_hunter_stable_archive_review_v1','reviewed_at':time.time(),'verified':True,
        'pointer':pointer,'archive_sha256':checkpoint['sha256'],'archive_bytes':checkpoint['bytes'],
        'direct_remote_object':remote,'local_archive_created':False,'qualification_added':False,
        'accepted_episode':accepted,'packet_proof':proof,
        'receipts':[{'member':p,'sha256':s,'verified':True} for p,s in selected.items() if p.endswith('.json')],
        'frames':[{'member':p,'sha256':s,'verified':True} for p,s in selected.items() if p.endswith('.png')],
        'limits':'One ordinary owned native stable opening only. Whole failures remain excluded; slot mutations, '
            '200-cell capacity and general combat remain open. No pet setter or forced permission reset.'}
    lab.private_write(output,json.dumps(report,indent=2)+'\n')
    print(json.dumps({'verified':True,'remote':remote,'receipts':len(report['receipts']),
        'frames':len(report['frames']),'bytes':checkpoint['bytes'],'packet_proof':proof}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--accepted',help='Exact relative episode path inside this batch, only for a whole accepted opening')
    p.add_argument('--remote',action='store_true');a=p.parse_args();review(a.directory,a.output,a.accepted,a.remote)
