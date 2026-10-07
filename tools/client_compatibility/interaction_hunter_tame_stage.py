"""Stage only the owned Hunter beside an existing tameable wolf, with exact pose restoration."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source,wire_known
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound,pet_identity
from .interaction_pet_dismiss import Presence
from .interaction_pet_target import pair
from .interaction_spellbook_recon import resources
from .interaction_observation import read_page
from .observation.inventory import Inventory
from .observation.transport import Observer
from .world.objects import INDEX


NAMES=('TC442HunterTameRestore','TC442HunterTameTarget')


def pose():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT position_x,position_y,position_z,orientation,map FROM client442_characters.characters '
            'WHERE guid=6 AND account=2 AND name="Harnesshunt" AND level=10')
        rows=q.fetchall()
    if len(rows)!=1:raise RuntimeError('owned Hunter pose authority differs')
    return list(rows[0])


def teleport_row(q,number):
    q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
        'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(number,))
    row=q.fetchone()
    if row is None:raise RuntimeError('owned tame teleport row is absent')
    return list(row)


def existing_wolf(wolf):
    keys=('guid','id','name','map','position_x','position_y','position_z','orientation',
        'minlevel','maxlevel','type','type_flags','family','faction','unit_flags','MovementType')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
            't.minlevel,t.maxlevel,t.type,t.type_flags,t.family,t.faction,t.unit_flags,c.MovementType '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id '
            'WHERE c.guid=%s',(wolf['guid'],))
        rows=q.fetchall()
    if len(rows)!=1 or dict(zip(keys,rows[0]))!=wolf:
        raise RuntimeError('existing tameable wolf database prerequisite changed')


def restore(t,fixture,old,baseline):
    if fixture['owner']!=6 or fixture['native']!=t.receipt['runtime']['worldserver']:
        raise RuntimeError('owned tame pose fixture belongs to another actor/lifetime')
    with lab.connection() as c,c.cursor() as q:
        if any(teleport_row(q,row[0])!=row for row in fixture['rows']):
            raise RuntimeError('owned tame pose rows changed; refusing restoration/deletion')
        # ObjectMgr::LoadGameTele consumes this ordinary SQL FLOAT projection.
        # Compare the same saved authority as the established position oracle.
        q.execute('SELECT position_x,position_y,position_z,orientation,map '
            'FROM client442_world.game_tele WHERE id=%s',(fixture['rows'][0][0],))
        expected=list(q.fetchone())
    replayed=pose()!=expected
    if replayed:lab.server_command('tele name Harnesshunt '+NAMES[0]);time.sleep(4)
    lab.server_command('saveall');time.sleep(.5)
    current=pose()
    if current!=expected:raise RuntimeError('owned Hunter native saved pose did not restore')
    with lab.connection() as c,c.cursor() as q:
        for row in fixture['rows']:
            if teleport_row(q,row[0])!=row:raise RuntimeError('owned tame teleport changed before deletion')
            q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
    lab.server_command('reload game_tele')
    checks={'native_saved_hunter_pose':current==expected,'saved_rows':saved(6)==baseline,
        'temporary_rows_removed':True,**protected(old)}
    t.receipt.update(pose_restoration={'fixture':fixture,'restored':current,'removed':[r[0] for r in fixture['rows']],
        'checks':checks,'gameplay_input_sent':False,'native_teleport_replayed':replayed,
        'native_restore_projection':expected,'raw_float_difference':[b-a for a,b in zip(fixture['before'],current)],
        'authority':'Native ordinary SQL FLOAT projection, matching ObjectMgr::LoadGameTele and the saved-position oracle.'});t.persist()
    if not all(checks.values()):raise RuntimeError('owned tame fixture restoration differs')


def run(t,preparation,entry,stored,recon,action,source=None):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    entered=entry_source(t,entry,session,preparation);moved=closed(stored)
    if (moved.get('runtime')!=t.receipt['runtime'] or moved.get('actor')!=t.fixture or
        moved.get('native_session')!=session or moved.get('phase')!='owned_stable_slot_move_verified' or
        moved.get('destination')!=5 or moved.get('capture_disarmed') is not True or
        len(moved.get('move_checks',{}))!=12 or not all(moved['move_checks'].values())):
        raise RuntimeError('tame staging requires a whole owned pet4 stable move')
    t.receipt.update(native_session=session,entry_source=bound(entry),stored_source=bound(stored),recon_source=bound(recon))
    if action in ('restore','recover'):
        if action=='recover':
            path=source.resolve()
            if path.name!='episode.json' or source.is_symlink() or not path.is_relative_to(lab.ROOT/'evidence'):
                raise RuntimeError('requires a private closed failed wolf staging source')
            staged=json.loads(path.read_text())
            if (staged.get('completed') is not False or not staged.get('finished_at') or
                staged.get('failure')!='RuntimeError: owned Hunter exact original pose did not restore' or
                not staged.get('pose_fixture') or any(r.get('selected_text')!='/tcui' for r in
                    staged.get('chat_submission_checks',[]))):
                raise RuntimeError('failed no-Tame pose recovery identity differs')
        else:staged=closed(source)
        if ((action=='restore' and staged.get('phase')!='owned_existing_wolf_staged') or staged.get('runtime')!=t.receipt['runtime'] or
            staged.get('actor')!=t.fixture or staged.get('stored_source')!=bound(stored)):
            raise RuntimeError('exact owned tame staging source differs')
        t.receipt['stage_source']=bound(source)
        restore(t,staged['pose_fixture'],old,staged['baseline_saved'])
        t.receipt.update(completed=True,phase='owned_tame_pose_restored',qualification_added=False);return
    if not pet_identity(moved['baseline_pets'],pets(6),5,0):
        raise RuntimeError('retained named pet4 is not safely stored in native stable5')
    known=wire_known(t,session)
    if 1515 not in known:raise RuntimeError('ordinary native Tame Beast1515 is not known')
    o=Presence(session,6,min(p['time'] for p in entered['login_packets'])).poll()
    inv=Inventory(lab.ROOT,session,6).poll();before=resources(inv);baseline=saved(6)
    if o.present() or pair(o.player,'UNIT_FIELD_SUMMON') or before!=entered['resources'] or baseline!=entered['entered_saved']:
        raise RuntimeError('tame staging requires no summoned pet and preserved owner resources/saved rows')
    r=json.loads(recon.read_text());wolf=r['nearest_existing_wolves'][0]
    if (r.get('schema')!='client442_owned_tame_prerequisite_recon_v1' or r.get('native')!=t.receipt['runtime']['worldserver'] or
        r.get('owner')!=6 or tuple(wolf[k] for k in ('guid','id','map','minlevel','maxlevel','type','type_flags','family'))!=
        (280666,299,0,1,1,1,1,1)):
        raise RuntimeError('existing level1 tameable wolf prerequisite differs')
    existing_wolf(wolf)
    t.clean_panels();read_page(t,'tame_stage_core','state','/tcui');state,frame=t.observe('tame_stage_before')
    if frame['movement']['in_combat'] or frame['movement']['dead'] or frame['movement']['speed']:
        raise RuntimeError('tame staging requires an idle living Hunter')
    lab.server_command('saveall');time.sleep(.5);original=pose()
    landing=[wolf['position_x'],wolf['position_y']+12,wolf['position_z'],3*math.pi/2,0]
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
        if q.fetchone():raise RuntimeError('prior owned tame pose fixture needs restoration')
        q.execute('SELECT MAX(id) FROM client442_world.game_tele');number=q.fetchone()[0]+1;rows=[]
        for i,(name,where) in enumerate(zip(NAMES,(original,landing))):
            q.execute('INSERT INTO client442_world.game_tele '
                '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (number+i,*where,name));rows.append(teleport_row(q,number+i))
    fixture={'owner':6,'native':t.receipt['runtime']['worldserver'],'before':original,'landing':rows[1][1:6],
        'rows':rows,'source':'Reversible native Hunter-only pose staging; no tame/spell/pet/health grant.'}
    t.receipt.update(pose_fixture=fixture,baseline_resources=before,baseline_saved=baseline,
        retained_pet_before=pets(6),native_wolf_spawn=wolf);t.persist()
    try:
        lab.server_command('reload game_tele');lab.server_command('tele name Harnesshunt '+NAMES[1]);time.sleep(4)
        t.execute({'kind':'chat','value':'/targetexact Young Wolf'})
        state,frame=t.observe('existing_wolf_staged');native=Observer(guid=6,session=session);facts=native.poll()
        target=facts.get('selected_unit');unit=native.units.get((target or {}).get('guid'),{})
        fields=unit.get('fields',{})
        checks={'existing_native_wolf':bool(target) and target['guid']>>52==0xf13 and
            fields.get(INDEX['OBJECT_FIELD_ENTRY'])==299 and fields.get(INDEX['UNIT_FIELD_LEVEL'])==1 and
            fields.get(INDEX['UNIT_FIELD_HEALTH'],0)>0 and
            math.dist(target['position'][:2],[wolf['position_x'],wolf['position_y']])<1,
            'visible_wolf':state.get('target',{}).get('name')=='Young Wolf' and state['target'].get('visible') is True,
            'in_tame_range':math.dist(state['world_position'][:2],[wolf['position_x'],wolf['position_y']])<15,
            'stored_retained_pet':pet_identity(moved['baseline_pets'],pets(6),5,0),
            'no_runtime_pet':not o.poll().present() and pair(o.player,'UNIT_FIELD_SUMMON')==0,
            'resources':resources(inv.poll())==before,'saved_rows':saved(6)==baseline,
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions'),**protected(old)}
        t.receipt.update(stage_checks=checks,state=state,frame=frame,native_target=target,native_target_unit=unit);t.persist()
        if not all(checks.values()):raise RuntimeError('existing owned tame target staging differs')
        t.receipt.update(completed=True,phase='owned_existing_wolf_staged',qualification_added=False,
            qualified_scope='Existing tameable wolf and reversible owned Hunter pose only; no Tame Beast input yet.')
    except Exception as error:
        import traceback
        t.receipt.update(staging_failure=f'{type(error).__name__}: {error}',
            staging_failure_traceback=traceback.format_exc());t.persist()
        try:t.clean_panels()
        except Exception as cleanup:t.receipt['chat_cleanup_failure']=f'{type(cleanup).__name__}: {cleanup}';t.persist()
        restore(t,fixture,old,baseline);raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','restore','recover'])
    for k in ('preparation','entry','stored','recon','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--source',type=Path);a=p.parse_args()
    if a.action in ('restore','recover') and not a.source:p.error('requires a closed owned staging source')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.stored,a.recon,a.action,a.source)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
