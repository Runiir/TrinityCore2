"""Close a whole stable opening against the normally parked retained fixture."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_owned_class_fixture import prepared,character,saved,pets,origin_checks,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_pet_recon import saved_pet_unchanged
from .observation.journal import entries
from .review_hunter_stable_checkpoint import packet_proof


def close(t,preparation,opening,park,finish,primary):
    old=prepared(t,preparation,True)
    sources=[opening,park,finish,primary]
    opened,parked,restored,protected_primary=[closed(p) for p in sources]
    digest=lab.sha256(preparation)
    if any(e.get('fixture_source',{}).get('sha256')!=digest for e in (opened,parked,restored)):
        raise RuntimeError('stable closure preparation chain differs')
    if (opened.get('actor')!=old['class_actor'] or parked.get('actor')!=old['class_actor'] or
        restored.get('actor')!=old['origin_actor'] or protected_primary.get('actor',{}).get('guid')!=1 or
        any(e.get('runtime')!=t.receipt['runtime'] for e in (opened,parked,restored)) or
        parked.get('phase')!='await_original_selection_review' or
        len(parked.get('checks',{}))!=4 or not all(parked['checks'].values()) or
        len(restored.get('checks',{}))!=5 or not all(restored['checks'].values()) or
        not opened['finished_at']<parked['started_at']<restored['started_at']):
        raise RuntimeError('stable closure actors, lifetimes or normal parking differ')
    primary_runtime=protected_primary.get('runtime',{})
    if any(primary_runtime.get(k)!=t.receipt['runtime'][k] for k in ('worldserver','modern_world')):
        raise RuntimeError('primary closure is from another server lifetime')
    cfg=opened['capture_config']
    notifications=[row for row in entries(lab.ROOT/'evidence/world_packets.jsonl') if
        row.get('session')==cfg['session'] and row.get('direction')=='to_client' and
        row.get('name')=='SMSG_NPC_INTERACTION_OPEN_RESULT' and
        cfg['created_at']<=row.get('time',0)<=cfg['expires_at']]
    proof=packet_proof(opened,notifications)
    retained=pets(6);fixture=character(6,2)
    checks={**origin_checks(old),**protected(old),
        'accepted_whole_opening':proof['outcome_checks']==9 and proof['restoration_checks']==13,
        'capture_disarmed':opened['capture_disarmed'] is True and not (lab.ROOT/'run/owned_stable_request_probe.json').exists(),
        'hunter_offline':fixture['online']==0,
        'retained_character_unchanged':fixture==parked['retained_class_fixture'],
        'retained_saved_unchanged':saved(6)==parked['retained_class_saved'],
        'retained_pet_unchanged':retained==parked['retained_class_pets'],
        'preserved_named_pet':len(retained)==1 and tuple(retained[0].get(k) for k in
            ('id','owner','entry','name','renamed','slot'))==(4,6,42717,'Harnesswolf',1,0),
        'opening_saved_unchanged':saved(6)==opened['baseline_saved'],
        'opening_pet_preserved':saved_pet_unchanged(opened['baseline_pets'],retained,time.time()),
        'bridge_lifetime':identity('modern_world')==old['runtime']['modern_world'],
        'scout_lifetime':identity('client')==old['runtime']['client'],
        'original_registration':actors.load()==old['origin_actor'],
        'original_selection_restored':restored['checks']['origin_registration'] and restored['checks']['class_offline']}
    t.receipt.update(sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in [preparation,*sources]],
        checks=checks,opening_packet_proof=proof,input_sent=False,scout_frame=shot(t.out/'scout_offline.png'))
    with actor('primary'):
        checks['primary_lifetime']=identity('client')==primary_runtime['client']
        t.receipt['primary_frame']=shot(t.out/'primary_offline.png')
    t.receipt.update(completed=all(checks.values()),phase='hunter_stable_closed_boundary',
        custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY,
        qualified_scope='Closed native stable opening and retained fixture preservation only. '
            'Remote archive verification and separate frame review remain required for admission.')
    if not all(checks.values()):raise RuntimeError('stable final preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('preparation','opening','park','finish','primary','output'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code')
        try:close(t,a.preparation,a.opening,a.park,a.finish,a.primary)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
