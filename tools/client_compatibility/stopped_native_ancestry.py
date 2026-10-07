"""Bind a replacement of an already-installed candidate to its archived authority."""
import json,re
from pathlib import Path
from . import lab_runtime as lab
from .interaction_hunter_stable_slots import bound

SCHEMA='client442_stopped_native_tame_deployment_v1'


def primary_native(d):
    root=d.get('primary_native',d.get('native_before'))
    if not d.get('previous_native_deployment') and root!=d.get('native_before'):
        raise RuntimeError('original native authority has no predecessor')
    return root


def passed_tests(text):
    matches=re.findall(r'^(\d+) passed in [^\n]+$',text,re.M)
    if len(matches)!=1 or int(matches[0])<101 or re.search(r'\b\d+ (?:failed|error|errors|skipped)\b',text):
        raise RuntimeError('requires a whole native candidate test run with at least101 passing checks')
    return int(matches[0])


def prior_transition(previous,pause,review,checkpoint,deployment_ref):
    root=primary_native(previous);before=pause.get('runtime',{})
    checks=previous.get('installation_checks',{})
    member=str(Path(deployment_ref['path']).relative_to(lab.ROOT))
    if (previous.get('schema')!=SCHEMA or previous.get('completed') is not True or
        previous.get('installed') is not True or previous.get('failure') or not previous.get('finished_at') or
        len(checks)!=9 or not all(v is True for v in checks.values()) or
        previous.get('native_restarted') is not True or previous.get('bridge_unchanged') is not True or
        previous.get('native')!=before.get('worldserver') or previous.get('before')!=previous.get('after') or
        previous.get('after')!=before.get('modern_world') or
        previous.get('scout_lifetime')!=before.get('client') or
        previous.get('primary_stop_source')!=pause.get('primary_stop_source') or
        not previous['finished_at']<pause.get('started_at',0)<pause.get('finished_at',0) or
        pause.get('completed') is not True or pause.get('failure') or
        pause.get('phase')!='parked_scout_resource_paused' or pause.get('before')!=pause.get('after') or
        len(pause.get('checks',{}))!=8 or not all(v is True for v in pause['checks'].values()) or
        review.get('actual_remote_verified') is not True or review.get('complete_json_png_verified') is not True or
        review.get('archive_sha256')!=checkpoint.get('sha256') or review.get('bytes')!=checkpoint.get('bytes') or
        review.get('pointer')!=checkpoint.get('file','')+'.dvc' or checkpoint.get('cloud_verified') is not True or
        not any(r.get('path')==member and r.get('sha256')==deployment_ref['sha256'] for r in checkpoint.get('file_manifest',[])) or
        not any(r.get('path')=='bin/worldserver' and r.get('sha256')==previous.get('binary_sha256')
            for r in checkpoint.get('file_manifest',[]))):
        raise RuntimeError('previous native candidate is not bound to the verified closed archive')
    return root


def verified_previous(path,pause,review_path,depth=0):
    path=path.resolve();review_path=review_path.resolve()
    if (depth>=8 or path.name!='deployment.json' or not path.is_relative_to(lab.ROOT/'evidence') or
        path.is_symlink() or not review_path.is_relative_to(lab.ROOT/'evidence') or review_path.is_symlink()):
        raise ValueError('requires a bounded private native predecessor and actual remote review')
    previous=json.loads(path.read_text());checkpoint=json.loads((path.parent.parent/'checkpoint_receipt.json').read_text())
    review=json.loads(review_path.read_text());root=prior_transition(previous,pause,review,checkpoint,bound(path))
    if previous.get('previous_native_deployment'):
        verify_ancestry(previous,json.loads(Path(previous['source']['path']).read_text()),depth+1)
    stop_path=Path(previous['primary_stop_source']['path']);stop=json.loads(stop_path.read_text())
    if (bound(stop_path)!=previous['primary_stop_source'] or stop.get('runtime',{}).get('worldserver')!=root or
        stop.get('phase')!='user_requested_primary_client_stopped' or stop.get('completed') is not True or
        len(stop.get('checks',{}))!=8 or not all(v is True for v in stop['checks'].values()) or stop.get('before')!=stop.get('after')):
        raise RuntimeError('native predecessor original primary authority differs')
    return previous,root


def verify_ancestry(d,pause,depth=0):
    ref=d.get('previous_native_deployment');review=d.get('previous_native_review')
    if not ref:
        primary_native(d)
        if review:raise RuntimeError('orphan native predecessor review')
        return
    if not review:raise RuntimeError('native predecessor remote review is absent')
    path=Path(ref['path']);review_path=Path(review['path'])
    if ref!=bound(path) or review!=bound(review_path):raise RuntimeError('native predecessor evidence changed')
    previous,root=verified_previous(path,pause,review_path,depth)
    if d.get('primary_native')!=root or d.get('previous_binary_sha256')!=previous.get('binary_sha256'):
        raise RuntimeError('replacement native binary or original primary authority differs')
