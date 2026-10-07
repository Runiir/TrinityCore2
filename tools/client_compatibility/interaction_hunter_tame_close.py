"""Close the excluded single Tame trial with both originals and two pets retained."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_owned_class_fixture import prepared,character,saved,pets,origin_checks,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_hunter_tame_stage import NAMES


def close(t,preparation,settled,park,finish,primary):
    old=prepared(t,preparation,True)
    s,p,f,base=[closed(path) for path in (settled,park,finish,primary)]
    if (s.get('phase')!='owned_tame_late_owner_reconciled' or s.get('tame_input_replayed') is not False or
        s.get('qualification_added') is not False or len(s.get('settling_checks',{}))!=16 or
        not all(s['settling_checks'].values()) or p.get('phase')!='await_original_selection_review' or
        len(p.get('checks',{}))!=4 or not all(p['checks'].values()) or
        len(f.get('checks',{}))!=5 or not all(f['checks'].values()) or
        any(e.get('fixture_source')!=bound(preparation) for e in (s,p,f)) or
        any(e.get('runtime')!=t.receipt['runtime'] for e in (s,p,f)) or
        (s.get('actor'),p.get('actor'),f.get('actor'))!=(old['class_actor'],old['class_actor'],old['origin_actor']) or
        not s['finished_at']<p['started_at']<p['finished_at']<f['started_at'] or
        base.get('actor',{}).get('guid')!=1 or any(base['runtime'][k]!=t.receipt['runtime'][k]
            for k in ('worldserver','modern_world'))):
        raise RuntimeError('closed no-replay Tame settling/normal parking chain differs')
    retained=pets(6);rows={r['id']:r for r in retained}
    checks={**origin_checks(old),**protected(old),
        'hunter_offline':character(6,2)['online']==0,
        'parked_character_exact':character(6,2)==p['retained_class_fixture'],
        'parked_saved_rows_exact':saved(6)==p['retained_class_saved'],
        'parked_two_pets_exact':retained==p['retained_class_pets'],
        'named_pet_stored':set(rows)=={4,6} and tuple(rows[4][k] for k in
            ('owner','entry','name','renamed','slot','active'))==(6,42717,'Harnesswolf',1,5,0),
        'new_native_test_pet_retained':6 in rows and tuple(rows[6][k] for k in
            ('owner','entry','name','CreatedBySpell','slot','active'))==(6,299,'Wolf',13481,0,1),
        'no_tame_or_stable_probe':not any((lab.ROOT/'run'/name).exists() for name in
            ('owned_tame_request_probe.json','owned_stable_request_probe.json')),
        'bridge_lifetime':identity('modern_world')==old['runtime']['modern_world'],
        'scout_lifetime':identity('client')==old['runtime']['client'],
        'original_registration':actors.load()==old['origin_actor']}
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
        checks['no_temporary_tame_pose_rows']=not q.fetchall()
    t.receipt['scout_frame']=shot(t.out/'scout_offline.png')
    with actor('primary'):
        checks['primary_lifetime']=identity('client')==base['runtime']['client']
        t.receipt['primary_frame']=shot(t.out/'primary_offline.png')
    t.receipt.update(sources=[bound(path) for path in (preparation,settled,park,finish,primary)],
        checks=checks,input_sent=False,qualification_added=False,retained_pets=retained,
        custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY,
        phase='excluded_tame_trial_parked_boundary',completed=all(checks.values()),
        qualified_scope='Read-only closure of the excluded whole Tame trial. Original actors preserved; '
            'Harnesswolf remains stored, new normally tamed Wolf retained. No Tame qualification or input replay.')
    if not all(checks.values()):raise RuntimeError('excluded Tame trial parked preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('preparation','settled','park','finish','primary','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code')
        try:close(t,a.preparation,a.settled,a.park,a.finish,a.primary)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
