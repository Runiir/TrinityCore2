"""Read-only attribution of ordinary melee requests to native quest kill credit."""
import argparse,json,struct
from pathlib import Path
from . import lab_runtime as lab
from .observation.journal import entries
from .world.buffer import Reader,player_high
from .world.gameobjects import modern_guid


def review(source):
    run=json.loads(source.read_text())
    if not run.get('finished_at') or not all(run.get('restoration',{}).values()):
        raise RuntimeError('melee review requires a closed, restored quest fixture')
    cases=[c for c in run['cases'] if c['id'].endswith('_kill') and c['status']=='quest_progress_pass']
    journal=list(entries(lab.ROOT/'evidence/world_packets.jsonl'));results=[]
    for case in cases:
        credits=[p for p in case['oracle']['credit_packets'] if p['direction']=='from_native']
        if len(credits)!=1:raise RuntimeError('kill has no unique native credit')
        credit=credits[0];quest,entry,count,required,victim=struct.unpack('<4IQ',bytes.fromhex(credit['body']))
        packets=[p for p in journal if p.get('session')==credit['session'] and case['time']<=p.get('time',0)<=credit['time'] and
            p['name'] in ['CMSG_ATTACK_SWING','SMSG_ATTACK_START']]
        modern_identity=modern_guid(victim,0);proof={}
        for p in packets:
            r=Reader(bytes.fromhex(p['body']));name,direction=p['name'],p['direction']
            if (name,direction)==('CMSG_ATTACK_SWING','from_client'):matches=r.guid()==modern_identity
            elif (name,direction)==('CMSG_ATTACK_SWING','to_native'):matches=r.unpack('Q')==(victim,)
            elif (name,direction)==('SMSG_ATTACK_START','from_native'):matches=r.unpack('QQ')==(1,victim)
            elif (name,direction)==('SMSG_ATTACK_START','to_client'):matches=r.guid()==(1,player_high()) and r.guid()==modern_identity
            else:continue
            r.end()
            if matches:proof[name+':'+direction]=p
        expected={'CMSG_ATTACK_SWING:from_client','CMSG_ATTACK_SWING:to_native',
            'SMSG_ATTACK_START:from_native','SMSG_ATTACK_START:to_client'}
        oracle=case['oracle'];public=oracle.get('public_credit_agrees');modern=oracle.get('modern_credit_agrees')
        native=oracle['native_credit'];counter='mobcount1' if entry==118 else 'mobcount2'
        passed=(set(proof)==expected and case['input']=={'kind':'chat','value':'/startattack',
            'description':case['input']['description']} and case['selection_source']=='code' and
            quest==52 and entry in [118,822] and 0<count<=required and native.get(counter)==count and public and modern)
        results.append({'case':case['id'],'passed':bool(passed),'victim':victim,'entry':entry,'count':count,
            'credit':credit,'attack_identity_proof':proof,'ordinary_input':case['input']})
    if not results or not all(x['passed'] for x in results):raise RuntimeError('one or more ordinary melee identities do not match native kill credit')
    report={'schema':'client442_ordinary_melee_review_v1','source':str(source.relative_to(lab.ROOT)),
        'source_sha256':lab.sha256(source),'review_controller':'code_read_only','passed':True,'cases':results,
        'scope':'Ordinary melee start and one automatic melee kill against existing low-level quest creatures.',
        'limits':'Does not qualify repeated swing cadence, stop while alive, damage amounts, ranged combat, spells, or complete quest turn-in.'}
    target=source.parent/'melee_review.json'
    if target.exists():raise RuntimeError('review already exists; preserve its immutable source binding')
    lab.private_write(target,json.dumps(report,indent=2)+'\n');return {'file':str(target),'verified_kills':len(results),'passed':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--episode',type=Path,required=True)
    print(json.dumps(review(p.parse_args().episode)),flush=True)
