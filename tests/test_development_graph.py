"""Workflow regression fixtures, not evidence of native class or raid correctness."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.raid_program import development_graph as graph


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return {'path': str(path.name), 'sha256': graph.digest(path.read_bytes())}


@pytest.fixture
def case(tmp_path,monkeypatch):
    # These are workflow fixtures. Native provenance verification is separately
    # exercised by test_real_queued_build_verifier_rejects_fabricated_receipt.
    from tools.raid_program import queued_build
    monkeypatch.setattr(queued_build,'verify_receipt',lambda path,policy,allow_test_mode: {'classification':'success','gate_bearing':True})
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path/'code.cpp').write_text('original')
    (tmp_path/'.gitignore').write_text('*.json\n')
    subprocess.run(['git','-C',str(tmp_path),'add','code.cpp','.gitignore'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline'],check=True)
    evidence = put(tmp_path/'native.json', {'fixture': 'synthetic workflow test'})
    state = {'development_graph': {'version': 1, 'coordinator_worktree': str(tmp_path), 'revision': 0, 'objective': 'all actors', 'stage': 'diagnose',
        'unit': {'id': 'u1', 'edge': 'edge1', 'requirements': ['setup'], 'next_action': 'fix setup'},
        'encounter':{'raid':'fixture','boss':'fixture','mode':'10N'},'actor_ids': ['1', '2'], 'requirements': {'setup': {'status': 'open'},
            'actor_1': {'status': 'open', 'actor_id': '1', 'needs_raid': True, 'needs_performance': True},
            'actor_2': {'status': 'open', 'actor_id': '2', 'needs_raid': True, 'needs_performance': True}},
        'history': [], 'failures': {}, 'completed_measurements': [{'spec':'Survival','scoring_ms':300000}]}}
    put(tmp_path/graph.STATE_PATH, state)
    return tmp_path, state, evidence


def receipt(root, state, evidence, **changes):
    g=state['development_graph']; stage=g['stage']
    r={'authority':'coordinator_attestation', 'kind':graph.RECEIPTS[stage], 'unit_id':g['unit']['id'], 'producer':'reviewer' if stage=='review' else 'coordinator', 'evidence':[evidence]}
    r.update({
        'diagnose': {'policy':evidence,'validation_identity':{'scenario_kind':'raid','encounter':g['encounter'],'roster':evidence,'runtime_profile':evidence,'route':evidence},'base_commit':graph.git(root,'rev-parse','HEAD'),'hypothesis':'native setup missing','owned_files':['code.cpp'],'forbidden_changes':['no coefficient tuning'],'acceptance_conditions':['observe setup'],'required_test_commands':['pytest focused']},
        'implement': {'file_hashes':graph.snapshot(root,['code.cpp']), 'tests':[{'command':'pytest focused','exit_status':0}]},
        'review': {'file_hashes':graph.snapshot(root,['code.cpp']), 'verdict':'approved'},
        'build': {'policy':evidence,'file_hashes':graph.snapshot(root,['code.cpp']), 'source_commit':graph.git(root,'rev-parse','HEAD'),'binary_sha256':'b'*64,'build_receipt':put(root/'build-native.json',{'commit':graph.git(root,'rev-parse','HEAD'),'exit_code':0,'source_identity_stable':True,'test_mode':False,'output_artifacts':[{'kind':'worldserver_elf','sha256':'b'*64,'produced_by_ticket':True}]})},
        'validate': {'validation_identity':g.get('assignment',{}).get('validation_identity'),'build_identity':{'source_commit':graph.git(root,'rev-parse','HEAD'),'binary_sha256':'b'*64},'attempt_id':'attempt1','server_epoch':'epoch1','closed':True,'cleanup_verified':True,'terminal_reason':'clear','scenario_kind':'raid','clock':'completion_watchdog'},
        'assess': {'attempt_id':'attempt1','baseline':evidence,'comparison':evidence,'actor_reviews':{'1':{'status':'reviewed','receipt':evidence},'2':{'status':'not_exercised','reason':'not in this fixture'}},'encounter_clear':True,'repair_accepted':True,'performance_accepted':False,'accepted_requirements':['setup']},
        'publish': {'dvc_status_checked':True,'dvc_push_completed':True,'remote_verified':True,'cleanup_verified':True},
    }[stage])
    if stage in ('diagnose','implement'):
        r['advice']={p:{'status':'not_reviewed','reason':'offline test','adjudication':'independent review retained'} for p in ('jev','laya')}
    if g.get('claim'):r['operation_id']=g['claim']['operation_id']
    r.update(changes)
    ref=put(root/(stage+'.json'),r)
    return {'revision':g['revision'],'unit_id':g['unit']['id'],'action':'advance','receipt':ref,'claim_token':g.get('claim',{}).get('token')}


def claimed(root,state):
    g=state['development_graph']
    if g['stage'] in ('implement','build','validate','publish') and not g.get('claim'):
        return graph.reduce(root,state,{'action':'claim','revision':g['revision'],'unit_id':g['unit']['id'],'owner':'fixture-tab'})
    return state


def reach(case, stage):
    root,state,evidence=case
    while state['development_graph']['stage'] != stage:
        state=claimed(root,state)
        state=graph.reduce(root,state,receipt(root,state,evidence))
    return root,claimed(root,state),evidence


def test_resume_from_separate_process_preserves_completed_work_and_all_actors(case):
    root,state,evidence=case
    for _ in range(4):
        g=state['development_graph']
        if g['stage'] in ('implement','build','validate','publish'):
            graph.advance(root,{'action':'claim','revision':g['revision'],'unit_id':g['unit']['id'],'owner':'fixture-tab'},graph.resume(root)['state_sha256'])
            state=json.loads((root/graph.STATE_PATH).read_text())
        event=receipt(root,state,evidence)
        graph.advance(root,event,graph.resume(root)['state_sha256'])
        state=json.loads((root/graph.STATE_PATH).read_text())
    repo=Path(__file__).resolve().parents[1]
    output=subprocess.check_output([sys.executable,'-m','tools.raid_program.raid_workloop','--root',str(root),'resume'],cwd=repo,text=True)
    resumed=json.loads(output)
    assert resumed['stage']=='validate'
    assert resumed['completed_measurements'][0]['spec']=='Survival'
    assert set(resumed['open_requirements'])=={'setup','actor_1','actor_2'}
    assert 'build' in resumed['receipts']
    assert 'Reconcile any existing attempt' in resumed['next_action']


def test_stale_writer_does_not_overwrite_new_progress(case):
    root,state,evidence=case; old=graph.resume(root)['state_sha256'];event=receipt(root,state,evidence)
    graph.advance(root,event,old)
    before=(root/graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError,match='state changed'):graph.advance(root,event,old)
    assert (root/graph.STATE_PATH).read_bytes()==before


@pytest.mark.parametrize('stage,changes,match',[
    ('diagnose',{'producer':'jev'},'model advice'),
    ('diagnose',{'advice':{}},'adjudication'),
    ('implement',{'tests':[]},'required test'),
    ('review',{'producer':'coordinator'},'independent'),
    ('review',{'verdict':'changes_required'},'independent'),
    ('validate',{'build_identity':{}},'run/build mismatch'),
    ('validate',{'closed':False},'closed and cleaned'),
    ('validate',{'clock':'fixed_300'},'watchdog'),
    ('assess',{'actor_reviews':{}},'actor_reviews'),
    ('assess',{'attempt_id':'old'},'attempt mismatch'),
    ('assess',{'performance_accepted':True},'matched baseline'),
    ('assess',{'accepted_requirements':['actor_1']},'outside current unit'),
    ('publish',{'remote_verified':False},'publication incomplete'),
])
def test_bad_transitions_fail_without_mutation(case,stage,changes,match):
    root,state,evidence=reach(case,stage);before=json.dumps(state)
    with pytest.raises(graph.GraphError,match=match):graph.reduce(root,state,receipt(root,state,evidence,**changes))
    assert json.dumps(state)==before


def test_changed_code_invalidates_review(case):
    root,state,evidence=reach(case,'review')
    (root/'code.cpp').write_text('unreviewed change')
    with pytest.raises(graph.GraphError,match='commit source changes'):
        graph.reduce(root,state,receipt(root,state,evidence))


def test_changed_receipt_fails(case):
    root,state,evidence=case;event=receipt(root,state,evidence)
    (root/event['receipt']['path']).write_text('{}')
    with pytest.raises(graph.GraphError,match='hash mismatch'):graph.reduce(root,state,event)


def test_clear_does_not_finish_program_and_only_published_repair_closes(case):
    root,state,evidence=reach(case,'publish')
    assert state['development_graph']['requirements']['setup']['status']=='open'
    state=graph.reduce(root,state,receipt(root,state,evidence));g=state['development_graph']
    assert g['requirements']['setup']['status']=='accepted'
    with pytest.raises(graph.GraphError,match='open requirements'):
        graph.reduce(root,state,{'action':'complete','revision':g['revision'],'unit_id':'u1'})
    with pytest.raises(graph.GraphError,match='closed or unknown'):
        graph.reduce(root,state,{'action':'route','revision':g['revision'],'unit_id':'u1','reason':'repeat','unit':{'id':'u2','edge':'edge1','requirements':['setup'],'next_action':'repeat'}})


def test_ten_failures_require_summary_and_changed_hypothesis(case):
    root,state,evidence=case
    for i in range(10):
        state=graph.reduce(root,state,{'action':'rework','revision':i,'unit_id':'u1','receipt':evidence,'reason':'same rejected diagnosis'})
    assert state['development_graph']['stage']=='route'
    event={'action':'route','revision':10,'unit_id':'u1','reason':'new attempt','unit':{'id':'u2','edge':'edge1','requirements':['setup'],'next_action':'retry'}}
    with pytest.raises(graph.GraphError,match='receipt requires'):graph.reduce(root,state,event)
    event['causal_summary']=evidence
    with pytest.raises(graph.GraphError,match='change the causal'):graph.reduce(root,state,event)
    event['unit']['edge']='different cause'
    assert graph.reduce(root,state,event)['development_graph']['stage']=='diagnose'


def test_dummy_requires_exact_window_but_failed_attempt_can_be_closed(case):
    root,state,evidence=reach(case,'validate')
    state['development_graph']['assignment']['validation_identity']={'scenario_kind':'dummy','actor_id':'1','spec':'fixture','reference':evidence,'roster':evidence,'runtime_profile':evidence}
    with pytest.raises(graph.GraphError,match='exact 300'):
        graph.reduce(root,state,receipt(root,state,evidence,scenario_kind='dummy',terminal_reason='measurement_complete',scoring_ms=299000))
    result=graph.reduce(root,state,receipt(root,state,evidence,scenario_kind='dummy',terminal_reason='infrastructure_loss',scoring_ms=0))
    with pytest.raises(graph.GraphError,match='unattributable'):
        graph.reduce(root,result,receipt(root,result,evidence,encounter_clear=False))


def test_repo_seed_has_all_actors_and_completed_measurements():
    root=Path(__file__).resolve().parents[1];status=graph.resume(root)
    assert len(status['completed_measurements'])==5
    assert {str(n) for n in range(30001,30011)}=={k.removeprefix('actor_') for k in status['open_requirements'] if k.startswith('actor_')}
    assert status['unit']['edge']=='balance_missing_self_buff_and_leather_specialization'


def test_fabricated_completion_and_skipped_stage_rejected(case):
    root,state,evidence=case;g=state['development_graph']
    g['stage']='route'
    for r in g['requirements'].values():r['status']='accepted'
    with pytest.raises(graph.GraphError,match='stage does not match'):graph.check_graph(g)
    g['history']=[{'revision':0,'from':'diagnose','to':'route','unit_id':'u1','event':{'action':'advance','revision':0,'unit_id':'u1'}}];g['revision']=1
    with pytest.raises(graph.GraphError,match='illegal transition'):graph.check_graph(g)


def test_hidden_source_change_blocks_review(case):
    root,state,evidence=reach(case,'review')
    (root/'unowned.cpp').write_text('unreviewed')
    graph.git(root,'add','unowned.cpp');graph.git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','unowned change')
    with pytest.raises(graph.GraphError,match='outside bounded assignment'):
        graph.reduce(root,state,receipt(root,state,evidence))


def test_pending_acceptance_cannot_be_added_after_assessment(case):
    root,state,evidence=reach(case,'publish');state['development_graph']['pending_acceptance'].append('actor_2')
    with pytest.raises(graph.GraphError,match='pending acceptance'):
        graph.reduce(root,state,receipt(root,state,evidence))


def test_claim_only_one_concurrent_tab_can_start_operation(case):
    from concurrent.futures import ThreadPoolExecutor
    root,state,evidence=case
    state=graph.reduce(root,state,receipt(root,state,evidence));put(root/graph.STATE_PATH,state)
    before=graph.resume(root)['state_sha256'];g=state['development_graph'];executed=[]
    def tab(owner):
        try:
            saved=graph.advance(root,{'action':'claim','revision':g['revision'],'unit_id':'u1','owner':owner},before)
            executed.append(saved['claim']['operation_id'])  # mocked executor runs only after claim
        except graph.GraphError:
            pass
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(tab,['tab1','tab2']))
    assert len(executed)==1
    assert graph.resume(root)['claim']['operation_id']==executed[0]


def test_wrong_worktree_cannot_advance_progress(case):
    root,state,evidence=case;state['development_graph']['coordinator_worktree']='/another/worktree';put(root/graph.STATE_PATH,state)
    with pytest.raises(graph.GraphError,match='canonical coordinator'):
        graph.advance(root,receipt(root,state,evidence),graph.digest((root/graph.STATE_PATH).read_bytes()))


def test_no_requirement_progress_counts_even_with_repair_claim(case):
    root,state,evidence=reach(case,'assess')
    state=graph.reduce(root,state,receipt(root,state,evidence,accepted_requirements=[]))
    assert state['development_graph']['failures']['edge1']==1


def test_real_queued_build_verifier_rejects_fabricated_receipt(case,monkeypatch):
    from tools.raid_program import queued_build
    root,state,evidence=reach(case,'build')
    monkeypatch.undo()
    with pytest.raises(graph.GraphError,match='queued-build verification failed'):
        graph.reduce(root,state,receipt(root,state,evidence))


def test_validation_rework_requires_controller_reconciliation(case):
    root,state,evidence=reach(case,'validate');g=state['development_graph']
    event={'revision':g['revision'],'unit_id':'u1','claim_token':g['claim']['token'],'action':'rework','reason':'source changed before launch','receipt':evidence}
    with pytest.raises(graph.GraphError,match='reconcile controller'):
        graph.reduce(root,state,event)
    event['receipt']=put(root/'reconcile.json',{'ownership_checked':True,'active_operation':False,'operation_id':g['claim']['operation_id'],'completed_operation':False,'reusable_receipt_found':False})
    assert graph.reduce(root,state,event)['development_graph']['stage']=='diagnose'


def test_claim_gate_and_active_build_reconciliation(case):
    root,state,evidence=reach(case,'build');g=state['development_graph']
    event=receipt(root,state,evidence);event.pop('claim_token')
    with pytest.raises(graph.GraphError,match='operation is claimed'):graph.reduce(root,state,event)
    reconciliation=put(root/'busy.json',{'operation_id':g['claim']['operation_id'],'ownership_checked':True,'active_operation':True})
    for action in ('release','rework'):
        with pytest.raises(graph.GraphError,match='reconcil'):
            graph.reduce(root,state,{'action':action,'reason':'retry','revision':g['revision'],'unit_id':'u1','claim_token':g['claim']['token'],'receipt':reconciliation})


def test_unaccepted_actor_review_cannot_close_actor(case):
    root,state,evidence=case
    state['development_graph']['unit']['requirements']=['actor_1']
    root,state,evidence=reach((root,state,evidence),'assess')
    with pytest.raises(graph.GraphError,match='actor acceptance'):
        graph.reduce(root,state,receipt(root,state,evidence,accepted_requirements=['actor_1'],performance_accepted=True,baseline_matched=True,unexplained_material_decline=False))


def test_wrong_worktree_resume_has_no_action(case):
    root,state,evidence=case;state['development_graph']['coordinator_worktree']='/another/worktree';put(root/graph.STATE_PATH,state)
    with pytest.raises(graph.GraphError,match='canonical coordinator'):graph.resume(root)


def test_rework_cannot_hide_unreviewed_code_in_new_baseline(case):
    root,state,evidence=reach(case,'review');g=state['development_graph']
    (root/'code.cpp').write_text('bad committed change')
    graph.git(root,'add','code.cpp');graph.git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','unreviewed')
    state=graph.reduce(root,state,{'action':'rework','revision':g['revision'],'unit_id':'u1','reason':'failed review','receipt':evidence})
    with pytest.raises(graph.GraphError,match='rebase over unreviewed'):
        graph.reduce(root,state,receipt(root,state,evidence))


def test_completed_operation_cannot_be_released_to_repeat(case):
    root,state,evidence=reach(case,'validate');g=state['development_graph']
    ref=put(root/'completed.json',{'ownership_checked':True,'active_operation':False,'completed_operation':True,'reusable_receipt_found':True,'operation_id':g['claim']['operation_id']})
    with pytest.raises(graph.GraphError,match='record completed operations'):
        graph.reduce(root,state,{'action':'release','revision':g['revision'],'unit_id':'u1','claim_token':g['claim']['token'],'receipt':ref})


def test_existing_status_does_not_offer_claimed_live_launch(case):
    from tools.raid_program.raid_workloop import active_work_unit_status
    root,state,evidence=reach(case,'validate');put(root/graph.STATE_PATH,state)
    status=active_work_unit_status(root)
    assert status['workflow']['claim']
    assert status['ready_for_live_verification'] is False


def test_wrong_scenario_or_policy_cannot_validate(case):
    root,state,evidence=reach(case,'build')
    other=put(root/'other-policy.json',{'different':True})
    with pytest.raises(graph.GraphError,match='build policy differs'):
        graph.reduce(root,state,receipt(root,state,evidence,policy=other))
    root,state,evidence=reach(case,'validate')
    with pytest.raises(graph.GraphError,match='run scenario'):
        graph.reduce(root,state,receipt(root,state,evidence,validation_identity={'scenario_kind':'raid','encounter':'different boss'}))
