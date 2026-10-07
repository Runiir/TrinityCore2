"""A closed read-only precision receipt archives without inventing Trial fields."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tarfile
import pytest
from tools.client_compatibility import checkpoint_interactions as checkpoint
from tools.client_compatibility import hunter_rest_accrual as rest
from tools.client_compatibility.interaction_metrics import choice_counts


@pytest.fixture
def diagnostic_batch(tmp_path,monkeypatch):
    root=tmp_path/'lab';repo=tmp_path/'repo';directory=root/'evidence/batch'
    directory.mkdir(parents=True)
    monkeypatch.setattr(checkpoint.lab,'ROOT',root);monkeypatch.setattr(checkpoint.lab,'REPO',repo)
    snapshots={str(n):{'native':{'guid':n,'online':0},'saved':{},'pets':[],'inventory':[]} for n in range(1,7)}
    hunter={'guid':6,'account':2,'name':'Harnesshunt','race':1,'class':3,'level':10,'xp':45,'online':0,
        'rest_bonus':168.588,'logout_time':200,'is_logout_resting':0}
    snapshots['6']['native']=hunter
    common={'schema':'client442_laya_interactions_v1','runtime':{'worldserver':1},'actor':{'guid':6},
        'fixture_source':{'path':'fixture','sha256':'a'*64},'completed':True,'failure':None,
        'controller':'code','model':None,'revision':None,'cases':[]}
    def put(name,value):
        path=directory/name/'episode.json';path.parent.mkdir();path.write_text(json.dumps(value,indent=2)+'\n')
        return {'path':str(path),'sha256':checkpoint.lab.sha256(path)}
    entry=put('entry',{**common,'phase':'owned_class_entered','started_at':100,'finished_at':110,
        'cases':[{'status':'observed','selected':'inspect','after_frame':{'file':'frame.png'}}]})
    park=put('park',{**common,'phase':'await_original_selection_review','started_at':200,'finished_at':210,
        'checks':{str(n):True for n in range(4)},'retained_class_fixture':deepcopy(hunter)})
    normalize=put('normalize',{**common,'phase':'owned_revive_fixture_normalized','started_at':300,'finished_at':301,
        'sources':[park],'after':deepcopy(snapshots),'input_sent':False,'qualification_added':False})
    failed=put('failedclose',{**common,'phase':None,'completed':False,'failure':rest.REST_FAILURE,
        'started_at':310,'finished_at':311})
    exact=168.58815002441406
    run={'schema':checkpoint.REST_PRECISION_SCHEMA,'phase':'owned_hunter_readonly_rest_precision_complete',
        'completed':True,'started_at':400,'finished_at':401,'input_sent':False,'mutation_sent':False,
        'qualification_added':False,'query':rest.PRECISION_QUERY,
        'row':{**{k:hunter[k] for k in ('guid','account','name','class','level','xp','online','rest_bonus',
            'logout_time','is_logout_resting')},'exact_rest_bonus':exact,'exact_rest_bonus_float32_bits':struct.pack('<f',exact).hex()},
        'sources':[entry,park,normalize,failed],'before':deepcopy(snapshots),'after':deepcopy(snapshots),
        'checks':{k:True for k in ('all_six_offline','all_saved_state_unchanged','hunter_identity',
            'snapshot_rest_matches','exact_float32')}}
    ref=put('precision',run)
    path=Path(ref['path'])
    return root,repo,directory,path,run


def test_precision_projection_keeps_absent_trial_identity_and_zero_choices(diagnostic_batch):
    _,_,directory,path,run=diagnostic_batch
    original=deepcopy(run);raw=path.read_bytes()
    cases,metadata,trials=checkpoint.checkpoint_runs([(path,run)],directory)
    assert cases==[] and trials==[] and all(v==0 for v in choice_counts(trials).values())
    assert metadata[0]['record_kind']=='readonly_diagnostic' and metadata[0]['operations_admitted']==0
    assert metadata[0]['receipt_sha256']==checkpoint.lab.sha256(path)
    assert not {'controller','model','revision','failure'} & set(metadata[0])
    assert not {'cases','controller','model','revision','failure'} & set(run)
    assert run==original and path.read_bytes()==raw


@pytest.mark.parametrize('fault',['unknown_schema','cases','input','mutation','qualification','failed_check',
    'missing_snapshot','online','changed_state','source_hash','source_outside_batch','query','float_bits',
    'nonfinite_time','backward_time'])
def test_invalid_diagnostic_never_gets_missing_trial_field_exemption(diagnostic_batch,fault):
    _,_,directory,path,run=diagnostic_batch
    if fault=='unknown_schema':run['schema']='unknown_readonly_schema'
    elif fault=='cases':run['cases']=[{'status':'operation_pass'}]
    elif fault=='input':run['input_sent']=True
    elif fault=='mutation':run['mutation_sent']=True
    elif fault=='qualification':run['qualification_added']=True
    elif fault=='failed_check':run['checks']['exact_float32']=False
    elif fault=='missing_snapshot':del run['before']['1'];del run['after']['1']
    elif fault=='online':run['before']['1']['native']['online']=1;run['after']=deepcopy(run['before'])
    elif fault=='changed_state':run['after']['6']['native']['xp']+=1
    elif fault=='source_hash':run['sources'][0]['sha256']='0'*64
    elif fault=='source_outside_batch':run['sources'][0]['path']=str(directory.parent/'foreign/episode.json')
    elif fault=='query':run['query']='UPDATE characters SET rest_bonus=0'
    elif fault=='float_bits':run['row']['exact_rest_bonus_float32_bits']='00000000'
    elif fault=='nonfinite_time':run['finished_at']=float('inf')
    elif fault=='backward_time':run['finished_at']=run['started_at']-1
    path.write_text(json.dumps(run))
    with pytest.raises((RuntimeError,KeyError)):
        checkpoint.checkpoint_runs([(path,run)],directory)


@pytest.mark.parametrize('field',['cases','failure','controller','model','revision'])
def test_ordinary_trial_required_fields_stay_required(diagnostic_batch,field):
    _,_,directory,path,_=diagnostic_batch
    ordinary={'schema':'client442_laya_interactions_v1','completed':True,'failure':None,
        'controller':'code','model':None,'revision':None,'cases':[]}
    del ordinary[field]
    with pytest.raises(KeyError):checkpoint.checkpoint_runs([(path,ordinary)],directory)


def test_coherent_sources_cannot_turn_another_class_into_hunter_precision(diagnostic_batch):
    _,_,directory,path,run=diagnostic_batch
    run['before']['6']['native']['class']=9;run['after']=deepcopy(run['before']);run['row']['class']=9
    park_path=Path(run['sources'][1]['path']);park=json.loads(park_path.read_text())
    park['retained_class_fixture']['class']=9;park_path.write_text(json.dumps(park))
    run['sources'][1]['sha256']=checkpoint.lab.sha256(park_path)
    normalized_path=Path(run['sources'][2]['path']);normalized=json.loads(normalized_path.read_text())
    normalized['after']=deepcopy(run['before']);normalized['sources'][-1]=run['sources'][1]
    normalized_path.write_text(json.dumps(normalized));run['sources'][2]['sha256']=checkpoint.lab.sha256(normalized_path)
    path.write_text(json.dumps(run))
    with pytest.raises(RuntimeError):checkpoint.checkpoint_runs([(path,run)],directory)


def test_checkpoint_archive_retains_exact_raw_diagnostic_and_trial_metrics(diagnostic_batch,monkeypatch):
    pytest.importorskip('dvclive',reason='archive integration requires the root pixi publishing environment')
    root,repo,directory,path,run=diagnostic_batch
    raw=path.read_bytes();metrics={};commands=[]
    def file(relative,text):
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text);return target
    file('bin/worldserver','owned fixture binary')
    file('build/native_bridge/build_receipt.json','{}')
    binary=file('build/native_input/client442_input','fixture input binary')
    file('logs/modern_world.jsonl','')
    file('evidence/world_packets.jsonl','')
    (root/'run').mkdir()
    (repo/'artifacts/client_harness').mkdir(parents=True)
    plan=repo/'experiments/configs/client_harness/442_interactions_v1.json'
    plan.parent.mkdir(parents=True);plan.write_text(json.dumps({'cases':[{}],'qualified_operations':0}))
    (directory/'native_server_before.json').write_text(json.dumps({'pid':123,'start_ticks':456}))
    monkeypatch.setattr(checkpoint.lab,'owned_process',lambda name:{'pid':123,'start_ticks':456})
    monkeypatch.setattr(checkpoint,'verified_input',lambda:(binary,{'verified':True}))
    def check_output(command,**kwargs):
        if command[:3]==['git','status','--porcelain']:return ''
        if command==['git','rev-parse','HEAD']:return 'f'*40
        if command[:4]==['dvc','status','--cloud','--json']:return '{}'
        raise AssertionError(command)
    monkeypatch.setattr(checkpoint.subprocess,'check_output',check_output)
    monkeypatch.setattr(checkpoint.subprocess,'run',lambda command,**kwargs:commands.append(command))
    class Live:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def log_param(self,*args):pass
        def log_metric(self,name,value):metrics[name]=value
        def next_step(self):pass
    monkeypatch.setattr(checkpoint,'tracking_live',Live)
    checkpoint.checkpoint(directory,'precision_fixture')
    assert commands[0][0:2]==['dvc','add'] and commands[-1][0:2]==['dvc','push']
    archive_path=repo/'artifacts/client_harness/precision_fixture.tar.gz'
    with tarfile.open(archive_path,'r:gz') as archive:
        assert archive.extractfile(str(path.relative_to(root))).read()==raw
        metadata=json.load(archive.extractfile('tracking/checkpoint.json'))
    diagnostic=next(r for r in metadata['runs'] if r.get('record_kind')=='readonly_diagnostic')
    assert diagnostic['receipt_sha256']==checkpoint.lab.sha256(path)
    assert not {'controller','model','revision','failure'} & set(diagnostic)
    assert metrics['readonly_diagnostic_runs']==1 and metrics['closed_runs']==5
    assert metrics['code_choices_selected']==metrics['code_choices_executed']==1
    assert metrics['model_choices_selected']==metrics['model_choices_executed']==0
    assert metadata['counts']=={'observed':1} and path.read_bytes()==raw
