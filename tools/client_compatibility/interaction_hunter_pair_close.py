"""Close a fresh two-pet occupied swap with both originals offline and preserved."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import identity,shot
from .interaction_owned_class_fixture import prepared,character,saved,pets,origin_checks,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_pair import identities
from .interaction_hunter_stable_slots import bound
from .interaction_hunter_tame_stage import NAMES
from .interaction_primary_combat_reentry import retained


def close(t,preparation,entry,forward,forward_call,back,back_call,park,finish,deployment,primary_stop=None):
    old=prepared(t,preparation,True)
    paths=(entry,forward,forward_call,back,back_call,park,finish)
    entered,m1,c1,m2,c2,p,f=[closed(path) for path in paths]
    for e in (entered,m1,c1,m2,c2,p,f):
        if (e.get('fixture_source')!=bound(preparation) or e.get('runtime')!=t.receipt['runtime'] or
            e.get('custom_script_permission')!='blocked_by_user'):
            raise RuntimeError('fresh occupied swap actor/runtime/source/script chain differs')
    if (any(e.get('actor')!=old['class_actor'] for e in (entered,m1,c1,m2,c2,p)) or
        f.get('actor')!=old['origin_actor'] or
        not entered['finished_at']<m1['started_at']<m1['finished_at']<c1['started_at']<c1['finished_at']<
            m2['started_at']<m2['finished_at']<c2['started_at']<c2['finished_at']<p['started_at']<
            p['finished_at']<f['started_at']):
        raise RuntimeError('fresh complete occupied swap ordering differs')
    for e,count,key in ((entered,9,'checks'),(m1,12,'move_checks'),(c1,7,'call_checks'),
                        (m2,12,'move_checks'),(c2,7,'call_checks'),(p,4,'checks'),(f,5,'checks')):
        if len(e.get(key,{}))!=count or not all(e[key].values()):
            raise RuntimeError('fresh whole pair checks differ: '+key)
    if ((m1['number'],m1['source_slot'],m1['destination'],m1['swap_number'])!=(4,5,0,6) or
        (m2['number'],m2['source_slot'],m2['destination'],m2['swap_number'])!=(4,0,5,6) or
        c1.get('active_pet_number')!=4 or c2.get('active_pet_number')!=6 or
        not identities(m1['retained_pet_after'],c1['retained_pet_after'],{4:0,6:5},{4:1,6:0},4) or
        not identities(c1['retained_pet_after'],m2['retained_pet_before']) or
        not identities(m2['retained_pet_after'],c2['retained_pet_after'],{4:5,6:0},{4:0,6:1},6) or
        not identities(c2['retained_pet_after'],p['retained_class_pets'])):
        raise RuntimeError('fresh occupied pair restoration identity differs')
    d=json.loads(deployment.read_text())
    if not d.get('completed') or d.get('kind')!='pet_slot' or not d.get('config_unchanged'):
        raise RuntimeError('requires completed exact native pet-slot deployment')
    retained=pets(6);rows={r['id']:r for r in retained}
    checks={**origin_checks(old),**protected(old),
        'hunter_offline':character(6,2)['online']==0,
        'parked_character_exact':character(6,2)==p['retained_class_fixture'],
        'parked_saved_exact':saved(6)==p['retained_class_saved']==entered['entered_saved'],
        'parked_two_pets_exact':retained==p['retained_class_pets'],
        'named_pet_stored':set(rows)=={4,6} and (rows[4]['slot'],rows[4]['active'])==(5,0),
        'test_pet_retained':6 in rows and (rows[6]['slot'],rows[6]['active'])==(0,1),
        'capture_disarmed':not any((lab.ROOT/'run'/name).exists() for name in
            ('owned_tame_request_probe.json','owned_stable_request_probe.json')),
        'bridge_lifetime':identity('modern_world')==d['before']==d['after'],
        'scout_lifetime':identity('client')==d['client_lifetimes']['scout'],
        'native_lifetime':identity('worldserver')==d['native'],
        'installed_binary':lab.sha256(lab.ROOT/'bin/worldserver')==d['binary_sha256'],
        'config_unchanged':lab.sha256(lab.ROOT/'config/worldserver.conf')==d['config_before_sha256'],
        'original_registration':actors.load()==old['origin_actor']}
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
        checks['no_temporary_tame_pose_rows']=not q.fetchall()
    t.receipt['scout_frame']=shot(t.out/'scout_offline.png')
    with actor('primary'):
        if primary_stop:
            stopped=closed(primary_stop)
            if (stopped.get('phase')!='user_requested_primary_client_stopped' or
                stopped.get('action')!='stop_owned_primary_client' or stopped.get('input_sent') is not False or
                stopped.get('actor',{}).get('guid')!=1 or
                stopped.get('deployment_source')!=bound(deployment) or
                stopped.get('runtime',{}).get('worldserver')!=d['native'] or
                stopped.get('runtime',{}).get('modern_world')!=d['after'] or
                stopped.get('runtime',{}).get('client')!=d['client_lifetimes']['primary'] or
                len(stopped.get('checks',{}))!=8 or not all(stopped['checks'].values()) or
                not stopped['finished_at']<m1['started_at'] or
                stopped.get('before')!=stopped.get('after') or
                stopped.get('after')!=d['offline_baselines']['primary']):
                raise RuntimeError('exact user-requested primary shutdown source differs')
            checks['primary_intentionally_stopped']=lab.owned_process('client') is None and retained(1,1)==stopped['after']
            t.receipt['primary_stop_source']=bound(primary_stop)
        else:
            checks['primary_lifetime']=identity('client')==d['client_lifetimes']['primary']
            t.receipt['primary_frame']=shot(t.out/'primary_offline.png')
    sources=(preparation,*paths,deployment)+((primary_stop,) if primary_stop else ())
    t.receipt.update(sources=[bound(path) for path in sources],checks=checks,
        input_sent=False,qualification_added=False,retained_pets=retained,
        phase='fresh_occupied_pair_parked_boundary',completed=all(checks.values()),
        qualified_scope='Fresh occupied swap closed preservation only; inventory admission requires actual remote proof.')
    if not all(checks.values()):raise RuntimeError('fresh occupied swap parked preservation differs')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('preparation','entry','forward','forward-call','back','back-call','park','finish','deployment','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--primary-stop',type=Path,help='Exact closed user-requested offline primary shutdown')
    a=parser.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',
                                                          softTargetInteract=SCRIPT_BOUNDARY)
        try:close(t,a.preparation,a.entry,a.forward,a.forward_call,a.back,a.back_call,a.park,a.finish,a.deployment,a.primary_stop)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
