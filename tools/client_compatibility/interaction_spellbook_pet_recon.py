"""Read owned native pet creation and public pet state after one closed summon."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_spellbook_navigation import detail
from .interaction_owned_class_fixture import prepared,origin_checks,SCRIPT_BOUNDARY
from .observation.journal import entries
from .world.native_objects import records
from .world.objects import INDEX


def suite(t,preparation,source):
    old=prepared(t,preparation);source=source.resolve();e=json.loads(source.read_text())
    if (not e.get('completed') or e.get('failure') or not e.get('finished_at') or
            len(e.get('native_summon_outcomes',[]))!=1 or
            e['fixture']!=t.fixture or e['runtime']!=t.receipt['runtime'] or
            e.get('native_session')!=actors.session_entry(t.fixture)['session']):
        raise RuntimeError('pet recon requires the closed same-runtime owned summon')
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},
        input_sent=False,qualification_added=False)
    captured=[]
    def word(fields,name):
        return fields.get(INDEX[name],0) | fields.get(INDEX[name]+1,0)<<32
    for p in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if (p.get('session')!=e['native_session'] or p.get('direction')!='from_native' or
                p.get('name')!='SMSG_UPDATE_OBJECT' or not e['summon_started_at']<=p['time']<=e['finished_at']):continue
        bound=[]
        for r in records(bytes.fromhex(p['body'])):
            fields=r.get('fields',{})
            if r.get('kind')==3 and r['guid']>>52==0xf14 and word(fields,'UNIT_FIELD_SUMMONEDBY')==t.fixture['guid']:
                bound.append({'kind':'owned_pet_create','record':r,'owner':word(fields,'UNIT_FIELD_SUMMONEDBY'),
                    'pet_number':fields.get(INDEX['UNIT_FIELD_PETNUMBER'],0)})
            if r.get('guid')==t.fixture['guid'] and INDEX['UNIT_FIELD_SUMMON'] in fields:
                bound.append({'kind':'owned_player_summon','record':r,'summon_guid':word(fields,'UNIT_FIELD_SUMMON')})
        if bound:captured.append({'packet':p,'bound_records':bound})
    probe=detail(t,'public_pet_after_summon')
    checks=origin_checks(old)
    t.receipt.update(native_pet_packets=captured,public_pet=probe['pet'],origin_checks=checks,
        phase='native_pet_public_comparison',completed=all(checks.values()))
    if not all(checks.values()):raise RuntimeError('read-only pet recon changed the parked scout')
    if not any(r['kind']=='owned_pet_create' for p in captured for r in p['bound_records']):
        t.receipt['completed']=False;raise RuntimeError('owned native pet creation is absent from the summon window')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.source)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure','public_pet','origin_checks']}),flush=True)
