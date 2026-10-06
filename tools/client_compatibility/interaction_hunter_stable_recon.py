"""Walk the retained named Hunter to the native stable master using owned bindings."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_owned_class_fixture import prepared,saved,pets,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import protected
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_pet_recon import saved_pet_unchanged
from .interaction_actionbar_pages import detail
from .interaction_pet_target import PetOracle
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .world.gameobjects import modern_guid
from .world.objects import INDEX


def master():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
            'COALESCE(NULLIF(c.npcflag,0),t.npcflag),c.MovementType '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id '
            'WHERE c.guid=280694 AND c.id=6749 AND c.map=0');rows=q.fetchall()
    expected=(280694,6749,'Erma',0,-9465.95,48.1419,56.9676,1.46608,4194433,0)
    if rows!=(expected,):raise RuntimeError('native stable master fixture differs')
    return list(rows[0])


def turn_delta(position,facing,goal):
    wanted=math.atan2(goal[1]-position[1],goal[0]-position[0])
    return (wanted-facing+math.pi)%(2*math.pi)-math.pi


def suite(t,preparation,entry):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    if tuple(t.fixture.get(k) for k in ('guid','account_id','character_name','class','level'))!=(6,2,'Harnesshunt',3,10):
        raise RuntimeError('requires the retained owned Hunter')
    entered=entry_source(t,entry,session,preparation);npc=master();goal=npc[4:6]
    retained=pets(6);baseline_saved=saved(6)
    if len(retained)!=1 or tuple(retained[0].get(k) for k in ('id','entry','owner','name','renamed'))!=(4,42717,6,'Harnesswolf',1):
        raise RuntimeError('retained one-time named Hunter pet differs')
    since=min(p['time'] for p in entered['login_packets']);inv=Inventory(lab.ROOT,session,6).poll()
    before=resources(inv);t.clean_panels();initial,initial_frame=t.observe('stable_navigation_before')
    if before!=entered['resources'] or baseline_saved!=entered['entered_saved']:
        raise RuntimeError('owned Hunter entry resources changed')
    bar=detail(t,'stable_navigation_bindings');keys={}
    for command in ('MOVEFORWARD','TURNLEFT','TURNRIGHT'):
        row=bar['keys'].get(command,[])
        if not row or not row[0]:raise RuntimeError('required movement binding is absent')
        keys[command]=binding_key(row[0])
    t.receipt.update(native_session=session,entry_source={'path':str(entry.resolve()),'sha256':lab.sha256(entry)},
        native_master=npc,baseline_resources=before,baseline_saved=baseline_saved,baseline_pets=retained,
        navigation_origin={'state':initial,'frame':initial_frame},navigation=[],observed_bindings=keys,
        qualification_added=False);t.persist()
    state,frame=initial,initial_frame;stalled=0
    for index in range(24):
        pose=frame['movement'];position=state.get('world_position',[])
        if (len(position)!=4 or position[3]!=0 or pose.get('dead') or pose.get('in_combat') or
            pose.get('speed')!=0 or state.get('lua_errors') or state.get('blocked_actions') or
            not all(protected(old).values())):
            raise RuntimeError('owned stable navigation state is unsuitable')
        distance=math.dist(position[:2],goal)
        if distance<=3:break
        if distance>100:raise RuntimeError('stable navigation left its bounded fixture')
        delta=turn_delta(position,pose['facing_radians'],goal)
        if abs(delta)>.12:
            command='TURNLEFT' if delta>0 else 'TURNRIGHT';hold=max(.05,min(.6,abs(delta)/math.pi))
        else:command='MOVEFORWARD';hold=max(.05,min(2,(distance-2.5)/7))
        started=time.time();t.execute({'kind':'key','value':keys[command],'hold':hold})
        after,after_frame=t.observe(f'stable_navigation_{index:02d}')
        remaining=math.dist(after['world_position'][:2],goal)
        if command=='MOVEFORWARD':stalled=stalled+1 if distance-remaining<.2 else 0
        t.receipt['navigation'].append({'started_at':started,'binding':command,'key':keys[command],'hold':hold,
            'distance_before':distance,'distance_after':remaining,'state':after,'frame':after_frame,
            'consecutive_no_progress':stalled});t.persist()
        if stalled>=3:raise RuntimeError('stable navigation stalled; inputs stopped')
        state,frame=after,after_frame
    else:raise RuntimeError('stable navigation exhausted its bounded decisions')
    t.execute({'kind':'chat','value':'/targetexact Erma'});state,frame=t.observe('stable_master_staged')
    oracle=PetOracle(session,6,since).poll();guid=oracle.selected();target=state.get('target',{})
    checks={'native_master_selected':guid>>52==0xf13 and (guid>>32&0xfffff)==6749,
        'visible_named_master':target.get('name')=='Erma' and target.get('visible') is True,
        'within_interaction_range':math.dist(state['world_position'][:2],goal)<=3,
        'resources':resources(inv.poll())==before,'saved_rows':saved(6)==baseline_saved,
        'retained_named_pet':saved_pet_unchanged(retained,pets(6),time.time()),
        'owned_named_pet_present':oracle.pet is not None and
            oracle.pet['fields'].get(INDEX['OBJECT_FIELD_ENTRY'])==42717 and
            oracle.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])==4 and
            oracle.pet['fields'].get(INDEX['UNIT_FIELD_BYTES_2'],0)>>16&255==2,
        'clean_ui':not state.get('panels') and not state.get('lua_errors') and not state.get('blocked_actions'),
        **protected(old)}
    t.receipt.update(checks=checks,protected_checks=protected(old),state=state,frame=frame,
        native_stable_master_guid=guid,modern_stable_master_guid=list(modern_guid(guid,0)),
        retained_pets=pets(6),navigation_position_intentionally_retained=True);t.persist()
    if not all(checks.values()):raise RuntimeError('owned stable master staging differs')
    t.receipt.update(completed=True,phase='hunter_stable_master_staged',
        qualified_scope='Normal movement to the native stable fixture only. The Hunter position and Erma selection '
            'are intentionally retained for a separately reviewed service input; all prior actors stay unchanged. '
            'No stable opening, pet move, purchase or interaction coverage is claimed.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:suite(t,a.preparation,a.entry)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure')}),flush=True)
