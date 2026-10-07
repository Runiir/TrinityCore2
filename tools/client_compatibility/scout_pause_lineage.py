"""Verify a later bridge replacement against its exact closed offline pause."""
SCHEMA='client442_resource_paused_scout_deployment_v1'


def transition(report,runtime,pause,restored,refs):
    before=pause.get('runtime',{});baseline=pause.get('after',{});attempt=report.get('parked_reconnect_attempt',{})
    if (report.get('schema')!=SCHEMA or report.get('completed') is not True or report.get('installed') is not True or
        report.get('native_unchanged') is not True or report.get('primary_stopped') is not True or
        report.get('parked_scout') is not True or not report.get('finished_at') or report.get('failure') or
        len(report.get('installation_checks',{}))!=4 or not all(v is True for v in report['installation_checks'].values()) or
        report.get('source')!=refs['pause'] or report.get('primary_stop_source')!=pause.get('primary_stop_source') or
        pause.get('phase')!='parked_scout_resource_paused' or pause.get('completed') is not True or pause.get('failure') or
        len(pause.get('checks',{}))!=8 or not all(v is True for v in pause['checks'].values()) or
        pause.get('before')!=baseline or report.get('offline_baselines')!=baseline or
        set(baseline)!={'1','2','3','4','5','6'} or any(v.get('native',{}).get('online')!=0 for v in baseline.values()) or
        pause.get('actor')!=report.get('origin_actor') or pause.get('actor',{}).get('guid')!=2 or
        runtime.get('worldserver')!=report.get('native') or report.get('native')!=before.get('worldserver') or
        report.get('before')!=before.get('modern_world') or report.get('after')!=runtime.get('modern_world') or
        report.get('after')==report.get('before') or report.get('after',{}).get('build')!=report.get('build') or
        report.get('previous_scout')!=before.get('client') or report.get('scout_lifetime')!=runtime.get('client') or
        report.get('previous_scout')==report.get('scout_lifetime') or set(attempt)!={'scout'} or
        attempt['scout'].get('completed') is not True or attempt['scout'].get('failure') or
        {'path':attempt['scout'].get('episode'),'sha256':attempt['scout'].get('sha256')}!=refs['restoration'] or
        restored.get('phase')!='single_scout_parked_reconnected' or restored.get('completed') is not True or
        restored.get('failure') or restored.get('runtime')!=runtime or restored.get('actor')!=pause.get('actor') or
        restored.get('all_offline_snapshot')!=baseline or restored.get('session')!=attempt['scout'].get('session') or
        not restored.get('session') or len(restored.get('restoration_checks',{}))!=7 or
        not all(v is True for v in restored['restoration_checks'].values()) or
        not pause.get('finished_at',0)<report.get('started_at',0)<restored.get('started_at',0)<
            restored.get('finished_at',0)<=report['finished_at']):
        raise RuntimeError('closed single-scout pause/deployment/restoration lineage differs')
    return before


def verified(report,path,runtime):
    from pathlib import Path
    from . import lab_runtime as lab
    from .interaction_retained_class_fixture import closed
    from .interaction_hunter_stable_slots import bound
    from .interaction_paused_scout_bridge_deploy import pause_source,tests_source
    from .interaction_single_scout_bridge_deploy import primary_stopped
    from .interaction_parked_client_resource_pause import gone
    source=Path(report.get('source',{}).get('path','')).resolve()
    if report.get('source')!=bound(source):raise RuntimeError('closed scout pause source changed')
    pause=pause_source(source);primary_stopped(Path(pause['primary_stop_source']['path']))
    attempt=report.get('parked_reconnect_attempt',{}).get('scout',{})
    restore=Path(attempt.get('episode','')).resolve()
    if not restore.is_relative_to(path.parent.parent):raise RuntimeError('scout restoration is outside its evidence batch')
    restored=closed(restore);refs={'pause':bound(source),'restoration':bound(restore)}
    transition(report,runtime,pause,restored,refs)
    test_path=Path(report['tests_source']['path'])
    if report['tests_source']!=bound(test_path):raise RuntimeError('paused candidate tests changed')
    tests_source(test_path,report['build'])
    if not gone(pause['game_before']['pid'],pause['game_before']['start_ticks']):
        raise RuntimeError('previous scout game still exists')
    return {'pause':pause,'restored':restored,'refs':refs}
