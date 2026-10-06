"""Carry normal paid Hunter control knowledge across a verified bridge deployment."""
import json
from pathlib import Path
from types import SimpleNamespace
from . import lab_runtime as lab
from .interaction_retained_class_fixture import closed,continuity


RETAINED_CHECKS={'original_character','original_saved_rows','native_worldserver','class_offline',
    'retained_character','retained_saved_rows','retained_pets','origin_registration'}|{
        f'actor_{g}_unchanged' for g in range(1,6)}


def validate(preparation,purchase,previous,park,finish,deployment,current):
    checks=purchase.get('purchase_checks',{});protected=purchase.get('protected_checks',{})
    if (purchase.get('actor')!=preparation.get('class_actor') or purchase.get('phase')!='control_pet_trained' or
        purchase.get('completed') is not True or purchase.get('failure') or not purchase.get('finished_at') or
        len(checks)!=9 or not all(checks.values()) or
        set(protected)!={f'actor_{g}_unchanged' for g in range(1,6)} or not all(protected.values()) or
        purchase.get('runtime')!=previous.get('runtime') or park.get('runtime')!=purchase.get('runtime') or
        purchase.get('fixture_source',{}).get('sha256')!=preparation['sources'][0]['sha256'] or
        not purchase['finished_at']<=park['started_at']<park['finished_at']<=finish['started_at'] or
        park.get('retained_class_saved',{}).get('spells')!=[[1515,1,0],[79682,1,0]] or
        preparation.get('natural_saved')!=park.get('retained_class_saved') or
        deployment.get('completed') is not True or not deployment.get('finished_at') or
        not deployment.get('parked_primary') or not deployment.get('parked_scout') or
        deployment.get('before')!=purchase['runtime']['modern_world'] or
        deployment.get('after')!=current['modern_world'] or
        deployment.get('native')!=current['worldserver'] or
        purchase['runtime']['worldserver']!=current['worldserver'] or
        purchase['runtime']['client']!=current['client'] or
        purchase['runtime']['modern_world']==current['modern_world'] or
        preparation.get('runtime')!=current or set(preparation.get('checks',{}))!=RETAINED_CHECKS or
        not all(preparation['checks'].values())):
        raise RuntimeError('paid Hunter control deployment continuity differs')


def validate_next(preparation,previous,park,finish,deployment,current):
    """Every later bridge change must preserve the already paid saved knowledge."""
    continuity(SimpleNamespace(fixture=previous['origin_actor'],receipt={'runtime':current}),
        previous,park,finish,deployment,preparation['sources'][0]['sha256'])
    if (previous.get('class_actor')!=preparation.get('class_actor') or
        preparation.get('runtime')!=current or set(preparation.get('checks',{}))!=RETAINED_CHECKS or
        not all(preparation['checks'].values()) or not deployment.get('parked_primary') or
        previous.get('natural_saved',{}).get('spells')!=[[1515,1,0],[79682,1,0]] or
        not previous['natural_saved']==park.get('retained_class_saved')==preparation.get('natural_saved') or
        not previous['finished_at']<=park['started_at']<park['finished_at']<=finish['started_at']<
            finish['finished_at']<=deployment['started_at']<deployment['finished_at']<=preparation['started_at']):
        raise RuntimeError('subsequent paid Hunter control deployment continuity differs')


def retained_source(t,preparation,path):
    purchase=closed(path);current=t.receipt['runtime'];chain=[];seen=set()
    while True:
        sources=preparation.get('sources',[])
        if len(chain)>=16 or len(sources)!=4 or sources[0]['sha256'] in seen:
            raise RuntimeError('paid Hunter deployment chain is cyclic or exceeds its bound')
        seen.add(sources[0]['sha256'])
        previous,park,finish,deployment=source_chain(sources)
        chain.append(sources[3])
        if purchase.get('fixture_source',{}).get('sha256')==sources[0]['sha256']:
            validate(preparation,purchase,previous,park,finish,deployment,current);break
        validate_next(preparation,previous,park,finish,deployment,current)
        current=previous['runtime'];preparation=previous
    t.receipt['retained_paid_control_source']={'path':str(path.resolve()),'sha256':lab.sha256(path),
        'deployment':chain[0],'deployments':list(reversed(chain)),'purchase_replayed':False}
    return purchase


def source_chain(sources):
    if len(sources)!=4:raise RuntimeError('requires the verified retained Hunter bridge deployment chain')
    paths=[Path(s['path']).resolve() for s in sources]
    if any(lab.sha256(p)!=s['sha256'] for p,s in zip(paths,sources)):
        raise RuntimeError('retained Hunter deployment source changed')
    previous,park,finish=[closed(p) for p in paths[:3]]
    if paths[3].name!='deployment.json' or not paths[3].is_relative_to(lab.ROOT/'evidence'):
        raise RuntimeError('requires the private completed owned deployment')
    deployment=json.loads(paths[3].read_text())
    return previous,park,finish,deployment
