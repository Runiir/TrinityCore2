"""Bind later interaction closures to one proven offline scout replacement."""

RELAUNCH_SCHEMA='client442_no_login_scout_relaunch_v1'
SINGLE_SCHEMA='client442_single_scout_bridge_deployment_v1'


def transition(report,runtime,deployment,restored,refs):
    before=report.get('before_runtime',{});after=report.get('after_runtime',{})
    baseline=report.get('offline_baselines',{})
    if (report.get('schema')!=RELAUNCH_SCHEMA or deployment.get('schema')!=SINGLE_SCHEMA or
        report.get('completed') is not True or report.get('installed') is not True or
        not report.get('finished_at') or report.get('input_sent') is not False or
        len(report.get('checks',{}))!=9 or not all(v is True for v in report['checks'].values()) or
        after!=runtime or before.get('worldserver')!=after.get('worldserver') or
        before.get('modern_world')!=after.get('modern_world') or before.get('client')==after.get('client') or
        before.get('worldserver')!=deployment.get('native') or
        before.get('modern_world')!=deployment.get('after') or before.get('client')!=deployment.get('scout_lifetime') or
        report.get('deployment_source')!=refs['deployment'] or
        report.get('primary_stop_source')!=deployment.get('primary_stop_source') or
        report.get('restoration_source')!=refs['restoration'] or
        baseline!=deployment.get('offline_baselines') or set(baseline)!={'1','2','3','4','5','6'} or
        any(v.get('native',{}).get('online')!=0 for v in baseline.values()) or
        restored.get('completed') is not True or restored.get('failure') is not None or
        restored.get('phase')!='owned_no_login_scout_restored' or restored.get('runtime')!=after or
        restored.get('actor')!=report.get('origin_actor') or report.get('origin_actor',{}).get('guid')!=2 or
        restored.get('input_sent') is not False or not restored.get('session') or
        len(restored.get('restoration_checks',{}))!=7 or
        not all(v is True for v in restored['restoration_checks'].values()) or
        not deployment.get('finished_at',0)<report.get('started_at',0)<restored.get('started_at',0)<
            restored.get('finished_at',0)<=report['finished_at']):
        raise RuntimeError('closed no-login scout replacement lineage differs')
    return before


def verified_deployment(path,runtime,relaunch=None):
    import json
    from pathlib import Path
    from . import lab_runtime as lab
    from .interaction_hunter_stable_slots import bound
    from .interaction_retained_class_fixture import closed
    from .interaction_single_scout_bridge_deploy import verified_report
    from .interaction_offline_scout_relaunch import no_login
    from .interaction_parked_client_resource_pause import gone

    path=path.resolve()
    if (path.name!='deployment.json' or not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink()):
        raise ValueError('requires an owned bridge deployment')
    d=json.loads(path.read_text());lineage=None;expected=runtime
    if relaunch:
        relaunch=relaunch.resolve()
        if (relaunch.name!='relaunch.json' or not relaunch.is_relative_to(lab.ROOT/'evidence') or relaunch.is_symlink()):
            raise ValueError('requires an owned no-login scout relaunch')
        r=json.loads(relaunch.read_text());sources={}
        for key in ('preparation_source','failed_entry_source','restoration_source'):
            ref=r.get(key,{})
            if not isinstance(ref,dict) or not ref.get('path'):raise RuntimeError('scout relaunch source missing')
            source=Path(ref['path']).resolve()
            if (source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence') or
                source.is_symlink() or ref!=bound(source)):raise RuntimeError('scout relaunch source changed')
            sources[key]=json.loads(source.read_text()) if key=='failed_entry_source' else closed(source)
        refs={'deployment':bound(path),'restoration':r['restoration_source']}
        restored=sources['restoration_source'];expected=transition(r,runtime,d,restored,refs)
        old=sources['preparation_source'];failed=sources['failed_entry_source']
        if (old.get('runtime')!=expected or old.get('origin_actor')!=r.get('origin_actor') or
            old.get('class_actor')!=r.get('class_actor') or old.get('phase')!='await_owned_class_lobby_review' or
            not old['finished_at']<failed.get('started_at',0)<failed.get('finished_at',0)<r['started_at'] or
            not gone(r['old_game']['pid'],r['old_game']['start_ticks'])):
            raise RuntimeError('original no-login failure or old scout boundary differs')
        no_login(failed,r['preparation_source'],r['class_actor'],expected,r.get('events',[]))
        lineage={'report':r,'restored':restored,'refs':refs}
    if d.get('schema')==SINGLE_SCHEMA:verified_report(path.parent,expected)
    elif relaunch:raise RuntimeError('scout relaunch requires a verified single-scout deployment')
    else:
        from .scout_pause_lineage import verified,SCHEMA
        if d.get('schema')==SCHEMA:lineage=verified(d,path,runtime)
    return d,lineage


def deployment_runtime(lineage,runtime,deployment):
    if not lineage:return runtime
    if 'pause' in lineage:
        from .scout_pause_lineage import transition as paused_transition
        return paused_transition(deployment,runtime,**lineage)
    return transition(runtime=runtime,deployment=deployment,**lineage)
