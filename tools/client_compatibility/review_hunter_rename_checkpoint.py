"""Verify the actual Rename checkpoint object and its attributable private packets."""
import argparse,hashlib,json,struct,tarfile,time
from pathlib import Path
from . import lab_runtime as lab
from .world.buffer import Writer


def whole(e,phase,checks):
    assert e['completed'] is True and e['failure'] is None and e['finished_at'] and e['phase']==phase
    for key,count in checks.items():
        assert len(e[key])==count and all(e[key].values())


def name_replies(e):
    count=0
    for direction in ('native','modern'):
        rows=e['name_replies'][direction];assert rows
        for row in rows:
            d,p=row['decoded'],row['packet'];name=d['name'].encode('ascii')
            assert d['name']=='Harnesswolf' and d['timestamp']>0
            if direction=='native':
                assert d['pet_number']==4 and p['direction']=='from_native'
                body=struct.pack('<I',4)+name+b'\0'+struct.pack('<IB',d['timestamp'],0)
            else:
                assert p['direction']=='to_client'
                w=Writer().guid(*d['guid']).bits(1,1).bits(len(name),8).bits(0,1)
                for _ in range(5):w.bits(0,7)
                body=w.pack('q',d['timestamp']).raw(name).finish()
            assert p['body']==body.hex();count+=1
    return count


def packet_proof(receipts):
    capture=receipts['hunter_rename_capture02'];accept=receipts['hunter_rename_accept01']
    persisted=receipts['hunter_name_persistence02']
    whole(capture,'hunter_rename_shape_captured',{'restoration_checks':13,'protected_checks':5})
    whole(accept,'hunter_renamed',{'rename_checks':18,'restoration_checks':13,'protected_checks':5})
    whole(persisted,'hunter_rename_persisted',{'persistence_checks':14,'restoration_checks':13,'protected_checks':5})
    for e in (capture,accept):
        assert e['capture_disarmed'] is True
        config=e['capture_config'];assert (config['owner'],config['pet_number'],config['synthetic_name'])==(6,4,'Harnesswolf')
        name=config['synthetic_name'].encode('ascii')
        modern=Writer().guid(*config['modern_pet_guid']).pack('i',4).bits(len(name),8).bits(0,1).bits(0,7).raw(name).finish()
        rows=e['capture_packets' if e is capture else 'rename_packets']
        client=[p for p in rows if p['direction']=='from_client' and p['name']=='CMSG_PET_RENAME']
        assert len(client)==1 and client[0]['body']==modern.hex()
        native=[p for p in rows if p['direction']=='to_native' and p['name']=='CMSG_PET_RENAME']
        if e is capture:assert not native
        else:
            assert len(native)==1 and native[0]['body']==(struct.pack('<Q',config['native_pet_guid'])+name+b'\0\0').hex()
    for e in (accept,persisted):
        assert e['public_pet']['name']=='Harnesswolf'
        assert len(e['pet_menu']['checks'])==4 and all(e['pet_menu']['checks'].values())
    return {'captured_client_requests':1,'accepted_client_requests':1,'accepted_native_requests':1,
        'accepted_name_replies':name_replies(accept),'reentry_name_replies':name_replies(persisted),
        'rename_checks':18,'persistence_checks':14,'restoration_checks_each':13,'menu_checks_each':4}


class DigestReader:
    def __init__(self,stream):self.stream=stream;self.digest=hashlib.sha256();self.bytes=0;self.buffer=b'';self.progress=0
    def read(self,size=-1):
        if size<0:size=1024*1024
        if len(self.buffer)<size:self.buffer+=self.stream.read(max(1024*1024,size-len(self.buffer)))
        data,self.buffer=self.buffer[:size],self.buffer[size:]
        self.digest.update(data);self.bytes+=len(data)
        if self.bytes-self.progress>=128*1024*1024:
            self.progress=self.bytes;print(json.dumps({'bytes_read':self.bytes}),flush=True)
        return data


def review(directory,output,remote=False):
    directory=directory.resolve();assert directory.parent==lab.ROOT/'evidence'
    checkpoint=json.loads((directory/'checkpoint_receipt.json').read_text())
    pointer=checkpoint['file']+'.dvc';prefix=str(directory.relative_to(lab.ROOT))+'/'
    selected={r['path']:r['sha256'] for r in checkpoint['file_manifest'] if r['path'].startswith(prefix) and
        Path(r['path']).suffix in ('.json','.png')}
    receipts={};seen=set()
    def inspect(raw):
        reader=DigestReader(raw)
        with tarfile.open(fileobj=reader,mode='r|gz') as archive:
            for member in archive:
                if member.name not in selected:continue
                assert member.isfile() and member.name not in seen
                with archive.extractfile(member) as f:
                    if member.name.endswith('/episode.json'):
                        data=f.read();assert hashlib.sha256(data).hexdigest()==selected[member.name]
                        e=json.loads(data);assert e['finished_at'] and isinstance(e['completed'],bool)
                        receipts[Path(member.name).parent.name]=e
                    else:assert hashlib.file_digest(f,'sha256').hexdigest()==selected[member.name]
                seen.add(member.name)
        while reader.read(1024*1024):pass
        assert reader.bytes==checkpoint['bytes'] and reader.digest.hexdigest()==checkpoint['sha256']
        assert seen==set(selected)
    if remote:
        import yaml
        from dvc.repo import Repo
        out=yaml.safe_load((lab.REPO/pointer).read_text())['outs'][0]
        assert out['size']==checkpoint['bytes']
        with Repo(str(lab.REPO)) as repo:
            odb=repo.cloud.get_remote_odb()
            with odb.fs.open(odb.oid_to_path(out['md5']),'rb',block_size=1024*1024,cache_type='none') as raw:inspect(raw)
    else:
        with (lab.REPO/checkpoint['file']).open('rb') as raw:inspect(raw)
    proof=packet_proof(receipts)
    report={'schema':'client442_hunter_rename_archive_review_v1','reviewed_at':time.time(),'verified':True,
        'pointer':pointer,'archive_sha256':checkpoint['sha256'],'archive_bytes':checkpoint['bytes'],
        'direct_remote_object':remote,'local_archive_created':False,'qualification_added':False,
        'receipts':[{'member':p,'sha256':s,'verified':True} for p,s in selected.items() if p.endswith('.json')],
        'frames':[{'member':p,'sha256':s,'verified':True} for p,s in selected.items() if p.endswith('.png')],
        'packet_proof':proof,'limits':'One retained synthetic Hunter name through ordinary confirmation/logout/reentry. '
            'General Rename bodies are excluded from global tracking; exact owned packets are verified in private archived receipts. '
            'Whole failed trials remain excluded. No forced permission reset or repeated purchase.'}
    lab.private_write(output,json.dumps(report,indent=2)+'\n')
    print(json.dumps({'verified':True,'remote':remote,'receipts':len(report['receipts']),
        'frames':len(report['frames']),'bytes':checkpoint['bytes'],'packet_proof':proof}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--remote',action='store_true');a=p.parse_args();review(a.directory,a.output,a.remote)
