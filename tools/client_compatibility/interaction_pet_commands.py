"""Challenge stock Stay and Follow with owner separation on owned open ground."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_owned_class_fixture import prepared,saved,pets,character,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_follow_capture import FollowPresence
from .interaction_pet_command_probe import read
from .interaction_pet_control_training import protected
from .interaction_pet_target import pair,retained_imp
from .interaction_pet_dismiss import vitals
from .interaction_actionbar_pages import detail
from .interaction_sit_stand import pose,afk
from .interaction_extra_bar import signature
from .interaction_spellbook_recon import resources
from .interaction_ground_movement import position,packets
from .interaction_bridge_deploy import shot
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX
from .pet_ground_fixture import PetGroundFixture
from .pet_movement_evidence import movement_pairs
from .pet_command_evidence import command_checks,public_checks,stay_motion_checks,follow_range_checks

PET_KEYS=('id','entry','owner','name','CreatedBySpell','PetType','level','slot','abdata')


def eligibility(t,preparation,entry):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);o=FollowPresence(session,5,e['started_at']).poll()
    inventory=Inventory(lab.ROOT,session,5).poll();identity=retained_imp(t.fixture,pets(5))
    if (t.fixture['guid']!=5 or not o.present() or pair(o.pet['fields'],'UNIT_FIELD_SUMMONEDBY')!=5 or
        o.pet['fields'].get(INDEX['UNIT_FIELD_PETNUMBER'])!=identity['id'] or pair(o.player,'UNIT_FIELD_TARGET')!=0 or
        resources(inventory)!=e['resources'] or saved(5)!=e['entered_saved'] or not all(protected(old).values())):
        raise RuntimeError('trained owned pet eligibility differs')
    t.receipt.update(native_session=session,sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)}
        for p in (preparation,entry)])
    return old,e,o,inventory,identity


def stage(t,preparation,entry):
    old,e,o,inventory,identity=eligibility(t,preparation,entry);t.clean_panels()
    state,_=t.observe('original_fixture');layout=detail(t,'original_layout')
    baseline={'resources':resources(inventory),'saved':saved(5),'money':character(5,2)['money'],
        'pet':{k:identity[k] for k in PET_KEYS},'pose':pose(inventory),'afk':afk(inventory),
        'layout':layout,'vitals':vitals(o)}
    t.receipt['baseline']=baseline;t.persist();fixture=PetGroundFixture(t.out,t.fixture)
    try:
        fixture.prepare();time.sleep(3);o.poll();near=read(t,'ground_pet_baseline');layout=detail(t,'ground_layout')
        checks=public_checks(near,o.pet,True,True)
        checks.update(owned_pet_present=o.present(),ground_map=o.pet['map']==0,
            forward_binding=bool(layout.get('keys',{}).get('MOVEFORWARD')),
            original_saved=saved(5)==baseline['saved'],protected=all(protected(old).values()))
        t.receipt.update(checks=checks,ground_layout=layout,ground_sample=near,native_pet=o.pet,
            fixture_file={'path':str((t.out/'pet_ground_fixture.json').resolve()),
                'sha256':lab.sha256(t.out/'pet_ground_fixture.json')},
            frame=shot(t.out/'owned_pet_ground.png'),phase='owned_pet_ground_staged',completed=all(checks.values()),
            qualified_scope='Native-console owned fixture setup and passive readings only; no pet command qualification.')
        if not all(checks.values()):raise RuntimeError('owned ground pet baseline differs')
    except Exception:
        t.receipt['stage_failure_restoration']=fixture.restore();raise


def staged(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):raise ValueError('require private stage receipt')
    d=json.loads(path.read_text())
    if (not d.get('completed') or d.get('failure') or not d.get('finished_at') or d.get('phase')!='owned_pet_ground_staged'
        or d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or not all(d['checks'].values())
        or d['fixture_file']['sha256']!=lab.sha256(Path(d['fixture_file']['path']))):
        raise RuntimeError('closed owned ground fixture differs')
    t.receipt['stage_source']={'path':str(path),'sha256':lab.sha256(path)};return d


def reviewed(t,path,stage_path):
    path=path.resolve();d=json.loads(path.read_text());frame=d.get('frame',{});image=path.parent/frame.get('file','')
    m=frame.get('monitor',{});current=owned_input.focus()
    if (not path.is_relative_to(lab.ROOT/'evidence') or d.get('reviewed') is not True or
        d.get('control')!='owned_pet_open_ground' or d.get('fixture_source_sha256')!=lab.sha256(stage_path) or
        not image.resolve().is_relative_to(lab.ROOT/'evidence') or not image.is_file() or
        lab.sha256(image)!=frame.get('sha256') or not 0<=time.time()-image.stat().st_mtime<=120 or
        not m.get('second_monitor_verified') or m.get('pid')!=t.receipt['runtime']['client']['pid'] or
        m.get('input_isolation',{}).get('actor')!='scout' or
        m.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid']):
        raise RuntimeError('fresh reviewed owned open ground differs')
    t.receipt['ground_review']={'path':str(path),'sha256':lab.sha256(path),'frame':frame};t.persist()


def command(t,o,command,label,near):
    since=time.time();pet=o.pet
    def outcome(b,a,s):
        o.poll();sample=read(t,label+'_pet');requests=[p for p in o.requests if p['time']>=since]
        checks=command_checks(requests,pet,command);checks.update(public_checks(sample,pet,command==1,near))
        checks['owned_native_pet_present']=o.present() and o.pet['guid']==pet['guid']
        t.receipt[label+'_sample']=sample
        return {'status':'owned_pet_command_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'requests':requests,'public':sample,'native_pet':pet}}
    row=t.step(label,'Submit one stock pet command and verify its owned native translation and public selection.',
        {'command':{'kind':'chat','value':'/petfollow' if command else '/petstay','description':'Use the stock secure pet command.'}},
        outcome,diagnostic_action='command')
    require(row,'owned_pet_command_pass');return since,t.receipt[label+'_sample']


def restore(t,d,fixture,o,inventory,old):
    result=fixture.restore();time.sleep(8);t.clean_panels()
    baseline=d['baseline'];layout=detail(t,'restored_layout')
    if pose(inventory)['stand']!=baseline['pose']['stand']:
        t.execute({'kind':'key','value':binding_key(layout['keys']['SITORSTAND'][0]),'hold':.4})
    if afk(inventory)!=baseline['afk']:t.execute({'kind':'chat','value':'/afk'})
    sample=read(t,'restored_pet');state,frame=t.observe('restored_fixture');o.poll();identity=retained_imp(t.fixture,pets(5))
    checks=public_checks(sample,o.pet,True,True)
    checks.update(original_position=math.dist(state['world_position'][:2],fixture.before[:2])<.2,
        original_resources=resources(inventory)==baseline['resources'],original_saved=saved(5)==baseline['saved'],
        original_money=character(5,2)['money']==baseline['money'],retained_pet={k:identity[k] for k in PET_KEYS}==baseline['pet'],
        original_pose=pose(inventory)==baseline['pose'],original_afk=afk(inventory)==baseline['afk'],
        original_bar=signature(layout)==signature(baseline['layout']),empty_selection=not state['target'].get('exists')
            and pair(o.player,'UNIT_FIELD_TARGET')==0,owned_native_pet=o.present(),
        panels_closed=not state.get('panels') and not state.get('bags'),protected=all(protected(old).values()))
    t.receipt.update(restoration_checks=checks,fixture_restoration=result,restored_frame=frame,
        protected_checks=protected(old),restored_sample=sample);t.persist()
    if not all(checks.values()):raise RuntimeError('pet command fixture restoration differs')


def run(t,preparation,entry,stage_path,review):
    old,e,o,inventory,identity=eligibility(t,preparation,entry);d=staged(t,stage_path)
    fixture=PetGroundFixture.resume(t.out,t.fixture,Path(d['fixture_file']['path']))
    flag=lab.ROOT/'run/capture_public_movement';owns_flag=False;stay_attempted=False;follow_complete=False
    try:
        reviewed(t,review,stage_path)
        if flag.exists():raise RuntimeError('another movement capture is active')
        lab.private_write(flag,str(t.out)+'\n');owns_flag=True
        if afk(inventory):t.execute({'kind':'chat','value':'/afk'})
        if pose(inventory)['stand']!=0:raise RuntimeError('owned ground challenge requires standing')
        before=position(5);stay_attempted=True;stay_since,near=command(t,o,0,'pets.command_stay',True)
        key=binding_key(d['ground_layout']['keys']['MOVEFORWARD'][0]);move_since=time.time()
        t.receipt['owner_separation_started_at']=move_since;t.persist()
        t.execute({'kind':'key','value':key,'hold':2.});time.sleep(2);after=position(5)
        far=read(t,'stay_owner_separated');until=time.time()
        pairs=movement_pairs(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,o.pet['guid'],0,stay_since,until)
        owner_packets=packets(move_since,o.session,5,'START_FORWARD','STOP')
        checks=stay_motion_checks(pairs,near['probe'],far['probe'],before,after)
        checks.update(public_checks(far,o.pet,False,False))
        checks.update(native_forward_start_stop=all(any(p['modern']['name']=='CMSG_MOVE_'+suffix and p['native']
            for p in owner_packets) for suffix in ('START_FORWARD','STOP')),
            native_public_owner_xy=math.dist(after[:2],[far['probe']['player_position']['x'],far['probe']['player_position']['y']])<.2)
        t.receipt['stay_behavior']={'checks':checks,'native_before':before,'native_after':after,
            'owner_packets':owner_packets,'pet_paths':pairs,'public_near':near,'public_far':far}
        t.persist()
        if not all(checks.values()):raise RuntimeError('pet Stay anchoring challenge differs')
        follow_since,returned=command(t,o,1,'pets.command_follow',True);follow_complete=True
        paths=movement_pairs(entries(lab.ROOT/'evidence/world_packets.jsonl'),o.session,o.pet['guid'],0,follow_since,time.time())
        checks=follow_range_checks(paths,far['probe'],returned['probe'],after)
        t.receipt['follow_behavior']={'checks':checks,'native_owner':after,'pet_paths':paths,'public_far':far,'public_near':returned}
        t.persist()
        if not all(checks.values()):raise RuntimeError('pet Follow movement challenge differs')
        t.receipt['behavior_completed']=True
    except Exception as error:
        t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        try:
            if stay_attempted and not follow_complete:command(t,o,1,'fixture.pet_follow_restore',True)
        finally:
            try:restore(t,d,fixture,o,inventory,old)
            finally:
                if owns_flag and flag.exists() and flag.read_text()==str(t.out)+'\n':flag.unlink()
    t.receipt.update(completed=True,phase='owned_pet_command_challenge_complete',qualification_added=False,
        qualified_scope='One trained owned Imp, stock Stay, ordinary owner separation, unchanged pet range/idle state, '
            'then stock Follow with an owned native spline delivered to the client and return into public range. '
            'The original pose, saved rows, resources, money, retained pet and protected actors restore. '
            'Pet coordinates are unavailable; player XY and native spline height are kept separate.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['stage','run'])
    for name in ['preparation','entry','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--stage',type=Path);p.add_argument('--review',type=Path);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.operation=='stage':stage(t,a.preparation,a.entry)
            else:run(t,a.preparation,a.entry,a.stage,a.review)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure','restoration_checks']}),flush=True)
