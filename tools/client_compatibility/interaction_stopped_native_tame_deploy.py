"""Stage and install a tested native Tame candidate with both owned clients stopped."""
import argparse,json,shutil,socket,subprocess,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_bridge_deploy import identity
from .interaction_hunter_stable_slots import bound
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_parked_client_resource_pause import snapshot
from .interaction_paused_scout_bridge_deploy import absent,primary_absent,pause_source
from .stopped_native_ancestry import passed_tests,verified_previous

SCHEMA='client442_stopped_native_tame_deployment_v1'
SOURCES={
    'tame_completion_source_sha256':'src/server/scripts/Spells/spell_hunter_tame_completion.cpp',
    'spell_loader_source_sha256':'src/server/scripts/Spells/spell_script_loader.cpp',
    'tame_binding_source_sha256':'sql/updates/world/4.3.4/2026_10_07_00_world.sql'}
BINDING=[13481,'spell_hun_tame_beast_completion']


def binding():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT spell_id,ScriptName FROM client442_world.spell_script_names WHERE spell_id=13481 ORDER BY ScriptName')
        return [list(r) for r in q.fetchall()]


def verified_build(path):
    if path.is_symlink() or not path.resolve().is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires private native build evidence')
    b=json.loads(path.read_text());binary=lab.ROOT/'build/src/server/worldserver/worldserver'
    if (b.get('schema')!='client442_native_core_build_v1' or b.get('completed') is not True or
        b.get('exit_code')!=0 or b.get('jobs')!=1 or b.get('native_unchanged') is not True or
        not b.get('finished_at') or b.get('binary_sha256')!=lab.sha256(binary) or
        any(b.get(k)!=lab.sha256(lab.REPO/v) for k,v in SOURCES.items())):
        raise RuntimeError('current one-job native Tame build/source differs')
    return b


def stage(out,pause_path,build_path,tests_path,previous_path=None,previous_review=None):
    out.mkdir(mode=0o700,parents=True,exist_ok=False);started=time.time()
    p=pause_source(pause_path);absent();b=verified_build(build_path);before=snapshot()
    if tests_path.is_symlink() or not tests_path.resolve().is_relative_to(out.parent):
        raise RuntimeError('requires the actual private native candidate test log')
    count=passed_tests(tests_path.read_text());previous=None;root=p['runtime']['worldserver'];expected_binding=[]
    if previous_path:
        previous,root=verified_previous(previous_path,p,previous_review)
        expected_binding=[BINDING]
        if lab.sha256(lab.ROOT/'bin/worldserver')!=previous['binary_sha256']:
            raise RuntimeError('installed predecessor binary differs')
    elif previous_review:raise RuntimeError('native predecessor review has no deployment')
    if (binding()!=expected_binding or actors.load()!=p['actor'] or before!=p['after'] or
        identity('worldserver')!=p['runtime']['worldserver'] or b['native_before']!=p['runtime']['worldserver'] or
        identity('modern_world')!=p['runtime']['modern_world']):
        raise RuntimeError('stopped native stage state, process or binding differs')
    d={'schema':SCHEMA,'started_at':started,'staged_at':time.time(),'source':bound(pause_path),
        'primary_stop_source':p['primary_stop_source'],'native_before':identity('worldserver'),
        'before':identity('modern_world'),'build':identity('modern_world')['build'],
        'previous_scout':p['runtime']['client'],'origin_actor':p['actor'],'offline_baselines':before,
        'native_build_source':bound(build_path),'native_build':b,'tests_source':bound(tests_path),
        'binary_sha256':b['binary_sha256'],'previous_binary_sha256':lab.sha256(lab.ROOT/'bin/worldserver'),
        'config_sha256':lab.sha256(lab.ROOT/'config/worldserver.conf'),'binding_before':expected_binding,
        'tests_passed':count,'primary_native':root,
        'rollback_file':('worldserver.before_tame_completion-'+previous['binary_sha256'][:12]
            if previous else 'worldserver.before_tame_completion'),
        'custom_script_permission':'blocked_by_user','softTargetInteract':SCRIPT_BOUNDARY,
        'primary_stopped':True,'parked_scout':True,'input_sent':False,'qualification_added':False,'completed':False}
    if previous:
        d.update(previous_native_deployment=bound(previous_path),previous_native_review=bound(previous_review))
    lab.private_write(out/'deployment.json',json.dumps(d,indent=2)+'\n')
    checks=dict.fromkeys(('all_saved_state','original_primary_state','all_six_offline','primary_stopped',
        'scout_stopped','origin_registration','native_lifetime','bridge_lifetime','candidate_build','native_binding'),True)
    episode={'started_at':started,'finished_at':time.time(),'completed':True,'failure':None,'controller':'code',
        'model':None,'revision':None,'actor':p['actor'],'runtime':{**p['runtime'],'client':None},
        'custom_script_permission':'blocked_by_user','softTargetInteract':SCRIPT_BOUNDARY,'checks':checks,
        'phase':'stopped_native_tame_candidate_staged','input_sent':False,'qualification_added':False,
        'cases':[],'sources':[bound(pause_path),bound(build_path),bound(tests_path)],'all_offline_snapshot':before}
    lab.private_write(out/'episode.json',json.dumps(episode,indent=2)+'\n')
    print(json.dumps({'staged':True,'checks':len(checks),'binary_sha256':b['binary_sha256']}),flush=True)


def install(source,batch):
    source=source.resolve();stage_path=source/'deployment.json';d=json.loads(stage_path.read_text())
    cp=json.loads((source.parent/'checkpoint_receipt.json').read_text());p=pause_source(Path(d['source']['path']))
    absent();build_path=Path(d['native_build_source']['path']);b=verified_build(build_path)
    backup=lab.ROOT/'bin'/d.get('rollback_file','worldserver.before_tame_completion');target=lab.ROOT/'bin/worldserver'
    expected_backup='worldserver.before_tame_completion'+('-'+d['previous_binary_sha256'][:12]
        if d.get('previous_native_deployment') else '')
    from .stopped_native_ancestry import verify_ancestry
    verify_ancestry(d,p)
    if backup.name!=expected_backup or backup.parent!=lab.ROOT/'bin':raise RuntimeError('native rollback path differs')
    if (batch.exists() or batch.resolve().parent!=lab.ROOT/'evidence' or backup.exists() or
        d.get('schema')!=SCHEMA or d.get('source')!=bound(Path(d['source']['path'])) or
        d.get('native_build_source')!=bound(build_path) or d.get('native_build')!=b or
        cp.get('cloud_verified') is not True or snapshot()!=d['offline_baselines'] or d['offline_baselines']!=p['after'] or
        identity('worldserver')!=d['native_before'] or identity('modern_world')!=d['before'] or
        lab.sha256(target)!=d['previous_binary_sha256'] or binding()!=d['binding_before'] or
        lab.sha256(lab.ROOT/'config/worldserver.conf')!=d['config_sha256'] or
        not any(r['path']==str(stage_path.relative_to(lab.ROOT)) and r['sha256']==lab.sha256(stage_path) for r in cp['file_manifest']) or
        not any(r['path']=='build/src/server/worldserver/worldserver' and r['sha256']==b['binary_sha256'] for r in cp['file_manifest'])):
        raise RuntimeError('closed remote native stage, build, process or saved authority differs')
    lab.server_command('saveall');lab.server_command('server shutdown 1');deadline=time.monotonic()+45
    while lab.owned_process('worldserver'):
        if time.monotonic()>deadline:raise RuntimeError('owned native graceful shutdown did not complete')
        time.sleep(.2)
    target.rename(backup);shutil.copy2(lab.ROOT/'build/src/server/worldserver/worldserver',target)
    lab.start_server('worldserver');deadline=time.monotonic()+45
    while True:
        try:
            with socket.create_connection(('127.0.0.1',18085),timeout=1):break
        except OSError:
            if time.monotonic()>deadline:raise RuntimeError('new owned native listener is unavailable')
            time.sleep(.2)
    subprocess.run(['pixi','run','python','-m','tools.client_compatibility.checkpoint_interactions',
        '--initialize','--directory',str(batch)],cwd=lab.REPO,check=True)
    out=batch/'native_tame_deploy01';out.mkdir(mode=0o700)
    d.update(started_at=time.time(),source_stage=bound(stage_path),native=identity('worldserver'),
        after=identity('modern_world'),native_restarted=True,bridge_unchanged=True,native_unchanged=False,
        installed=True,completed=False,rollback_binary_sha256=lab.sha256(backup),parked_reconnect_attempt={})
    absent();checks={'new_native':d['native']!=d['native_before'],'same_bridge':d['after']==d['before'],
        'all_saved_state':snapshot()==d['offline_baselines'],'primary_stopped':True,'scout_stopped':True,
        'origin_registration':actors.load()==d['origin_actor'],'installed_binary':lab.sha256(target)==d['binary_sha256'],
        'native_binding':binding()==[BINDING],'config_unchanged':lab.sha256(lab.ROOT/'config/worldserver.conf')==d['config_sha256']}
    d['installation_checks']=checks
    if not all(checks.values()):d['failure']='native installation preservation or binding differs'
    lab.private_write(out/'deployment.json',json.dumps(d,indent=2)+'\n')
    print(json.dumps({'installed':all(checks.values()),'checks':checks,'deployment':str(out)}),flush=True)
    if not all(checks.values()):raise RuntimeError(d['failure'])


def current(directory,require_client=False):
    d=json.loads((directory/'deployment.json').read_text());p=pause_source(Path(d['source']['path']));primary_absent()
    if (d.get('schema')!=SCHEMA or d.get('source')!=bound(Path(d['source']['path'])) or d.get('failure') or
        d.get('installed') is not True or len(d.get('installation_checks',{}))!=9 or
        not all(v is True for v in d['installation_checks'].values()) or d.get('native_before')!=p['runtime']['worldserver'] or
        d.get('native')==d.get('native_before') or d.get('before')!=p['runtime']['modern_world'] or d.get('after')!=d.get('before') or
        identity('worldserver')!=d.get('native') or identity('modern_world')!=d.get('after') or
        snapshot()!=p['after'] or d.get('offline_baselines')!=p['after'] or actors.load()!=p['actor'] or
        binding()!=[BINDING] or lab.sha256(lab.ROOT/'bin/worldserver')!=d.get('binary_sha256') or
        d.get('primary_stop_source')!=p['primary_stop_source'] or
        (require_client and identity('client')!=d.get('scout_lifetime'))):
        raise RuntimeError('stopped native deployment or offline lobby state differs')
    return d


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','install'])
    for name in ('output','source','pause','build','tests','previous-deployment','previous-review'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    with actor('scout'):
        if a.action=='stage':
            if bool(a.previous_deployment)!=bool(a.previous_review):p.error('predecessor requires deployment and actual remote review')
            stage(a.output,a.pause,a.build,a.tests,a.previous_deployment,a.previous_review)
        else:install(a.source,a.output)
