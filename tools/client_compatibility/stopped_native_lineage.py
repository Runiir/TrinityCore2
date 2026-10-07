"""Prove one stopped native replacement followed by one isolated scout launch."""
SCHEMA='client442_stopped_native_tame_deployment_v1'


def transition(d,runtime,pause,restored,refs):
    before=pause.get('runtime',{});base=pause.get('after',{})
    if (d.get('schema')!=SCHEMA or d.get('completed') is not True or d.get('installed') is not True or
        d.get('failure') or not d.get('finished_at') or d.get('native_restarted') is not True or
        d.get('bridge_unchanged') is not True or d.get('primary_stopped') is not True or
        d.get('parked_scout') is not True or d.get('input_sent') is not False or
        len(d.get('installation_checks',{}))!=9 or not all(v is True for v in d['installation_checks'].values()) or
        d.get('source')!=refs['pause'] or d.get('native_before')!=before.get('worldserver') or
        d.get('native')!=runtime.get('worldserver') or d.get('native')==d.get('native_before') or
        d.get('before')!=before.get('modern_world') or d.get('after')!=d.get('before') or
        d.get('after')!=runtime.get('modern_world') or d.get('build')!=d.get('after',{}).get('build') or
        d.get('previous_scout')!=before.get('client') or d.get('scout_lifetime')!=runtime.get('client') or
        d.get('scout_lifetime')==d.get('previous_scout') or d.get('offline_baselines')!=base or
        pause.get('completed') is not True or pause.get('failure') or pause.get('before')!=base or
        pause.get('phase')!='parked_scout_resource_paused' or len(pause.get('checks',{}))!=8 or
        not all(v is True for v in pause['checks'].values()) or set(base)!={'1','2','3','4','5','6'} or
        any(v['native']['online']!=0 for v in base.values()) or
        d.get('primary_stop_source')!=pause.get('primary_stop_source') or d.get('origin_actor')!=pause.get('actor') or
        restored.get('completed') is not True or restored.get('failure') or
        restored.get('phase')!='single_scout_parked_reconnected' or restored.get('runtime')!=runtime or
        restored.get('actor')!=pause.get('actor') or restored.get('all_offline_snapshot')!=base or
        len(restored.get('restoration_checks',{}))!=7 or not all(v is True for v in restored['restoration_checks'].values()) or
        not pause.get('finished_at',0)<d.get('staged_at',0)<d['started_at']<restored.get('started_at',0)<
            restored.get('finished_at',0)<=d['finished_at'] or
        set(d.get('parked_reconnect_attempt',{}))!={'scout'} or
        d['parked_reconnect_attempt']['scout']!={'completed':True,'failure':None,
            'episode':refs['restoration']['path'],'sha256':refs['restoration']['sha256'],'session':restored.get('session')} or
        not restored.get('session')):
        raise RuntimeError('stopped native replacement or isolated scout lineage differs')
    return before


def verified(d,path,runtime):
    import json
    from pathlib import Path
    from . import lab_runtime as lab
    from .interaction_hunter_stable_slots import bound
    from .interaction_retained_class_fixture import closed
    from .interaction_paused_scout_bridge_deploy import pause_source,primary_absent
    from .interaction_bridge_deploy import identity
    from .interaction_stopped_native_tame_deploy import binding,BINDING,SOURCES
    pause_path=Path(d['source']['path']);pause=pause_source(pause_path)
    restore_path=Path(d['parked_reconnect_attempt']['scout']['episode']);restored=closed(restore_path)
    if not restore_path.resolve().is_relative_to(path.parent.parent):raise RuntimeError('native scout restoration leaves its batch')
    refs={'pause':bound(pause_path),'restoration':bound(restore_path)};transition(d,runtime,pause,restored,refs)
    stage_path=Path(d['source_stage']['path']);stage=json.loads(stage_path.read_text())
    cp=json.loads((stage_path.parent.parent/'checkpoint_receipt.json').read_text())
    if (d['source_stage']!=bound(stage_path) or cp.get('cloud_verified') is not True or
        stage.get('offline_baselines')!=pause['after'] or stage.get('native_before')!=d['native_before'] or
        stage.get('binary_sha256')!=d['binary_sha256'] or stage.get('source')!=refs['pause'] or
        not any(r['path']==str(stage_path.relative_to(lab.ROOT)) and r['sha256']==lab.sha256(stage_path) for r in cp['file_manifest']) or
        d.get('native_build')!=json.loads(Path(d['native_build_source']['path']).read_text()) or
        d['native_build_source']!=bound(Path(d['native_build_source']['path'])) or
        d['native_build'].get('completed') is not True or
        any(d['native_build'].get(k)!=lab.sha256(lab.REPO/v) for k,v in SOURCES.items()) or
        d['tests_source']!=bound(Path(d['tests_source']['path'])) or
        '101 passed' not in Path(d['tests_source']['path']).read_text() or
        identity('worldserver')!=runtime['worldserver'] or identity('modern_world')!=runtime['modern_world'] or
        lab.sha256(lab.ROOT/'bin/worldserver')!=d['binary_sha256'] or binding()!=[BINDING]):
        raise RuntimeError('remote native stage, installed sources or candidate tests differ')
    primary_absent()
    return {'native_pause':pause,'restored':restored,'refs':refs}
