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
    # Execution provenance is exercised against actual-format session records
    # in test_review_execution; these fixtures exercise the graph's transitions.
    from tools.raid_program import review_execution
    monkeypatch.setattr(review_execution, 'verify_review', lambda root, review, **kwargs: review['file_hashes'])
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path/'code.cpp').write_text('original')
    (tmp_path/'.gitignore').write_text('*.json\n')
    subprocess.run(['git','-C',str(tmp_path),'add','code.cpp','.gitignore'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline'],check=True)
    evidence = put(tmp_path/'native.json', {'fixture': 'synthetic workflow test'})
    state = {'development_graph': {'version': 1, 'coordinator_worktree': str(tmp_path), 'revision': 0, 'objective': 'all actors', 'stage': 'diagnose',
        'unit': {'id': 'u1', 'edge': 'edge1', 'requirements': ['setup'], 'next_action': 'fix setup'},
        'encounter':{'raid':'fixture','boss':'fixture','mode':'10N'},'actor_ids': ['1', '2'], 'requirements': {'setup': {'status': 'open'},
            'actor_1': {'status': 'open', 'actor_id': '1', 'role': 'tank', 'spec': 'blood_death_knight', 'needs_raid': True, 'needs_performance': True},
            'actor_2': {'status': 'open', 'actor_id': '2', 'role': 'healer', 'spec': 'holy_paladin', 'needs_raid': True, 'needs_performance': True}},
        'history': [], 'failures': {}, 'completed_measurements': [{'spec':'Survival','scoring_ms':300000}]}}
    put(tmp_path/graph.STATE_PATH, state)
    return tmp_path, state, evidence


def receipt(root, state, evidence, **changes):
    g=state['development_graph']; stage=g['stage']
    r={'authority':'coordinator_attestation', 'kind':graph.RECEIPTS[stage], 'unit_id':g['unit']['id'], 'producer':'reviewer' if stage=='review' else 'coordinator', 'evidence':[evidence]}
    r.update({
        'diagnose': {'policy':put(root/'policy.json',json.loads((Path(__file__).resolve().parents[1]/'experiments/configs/cata_raid_build_resource_policy_host12_v1.json').read_text())),'validation_identity':{'scenario_kind':'raid','encounter':g['encounter'],'roster':evidence,'runtime_profile':evidence,'route':evidence},'base_commit':graph.git(root,'rev-parse','HEAD'),'hypothesis':'native setup missing','owned_files':['code.cpp'],'forbidden_changes':['no coefficient tuning'],'acceptance_conditions':['observe setup'],'required_test_commands':['pytest focused']},
        'implement': {'file_hashes':graph.snapshot(root,['code.cpp']), 'tests':[{'command':'pytest focused','exit_status':0}]},
        'review': {'file_hashes':graph.snapshot(root,['code.cpp']), 'verdict':'approved',
                   'reviewer_session_id':'fixture-independent-session', 'review_report': evidence},
        'build': {'policy':put(root/'policy.json',json.loads((Path(__file__).resolve().parents[1]/'experiments/configs/cata_raid_build_resource_policy_host12_v1.json').read_text())),'file_hashes':graph.snapshot(root,['code.cpp']), 'source_commit':graph.git(root,'rev-parse','HEAD'),'binary_sha256':'b'*64,'build_receipt':put(root/'build-native.json',{'commit':graph.git(root,'rev-parse','HEAD'),'exit_code':0,'source_identity_stable':True,'test_mode':False,'output_artifacts':[{'kind':'worldserver_elf','sha256':'b'*64,'produced_by_ticket':True}]})},
        'smoke': {'build_identity':g.get('build_identity'),'attempt_id':'smoke1','server_epoch':'epoch1','closed':True,'cleanup_verified':True,'terminal_reason':'clear','scenario_kind':'raid','clock':'completion_watchdog','encounter':g['encounter']},
        'validate': {'validation_identity':g.get('assignment',{}).get('validation_identity'),'build_identity':g.get('build_identity') or {'source_commit':graph.git(root,'rev-parse','HEAD'),'binary_sha256':'b'*64},'attempt_id':'attempt1','server_epoch':'epoch1','closed':True,'cleanup_verified':True,'terminal_reason':'clear','scenario_kind':'raid','clock':'completion_watchdog'},
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
    if g['stage'] in graph.tiers.CLAIMED and not g.get('claim'):
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
    output=subprocess.check_output([sys.executable,'-m','tools.raid_program.raid_workloop','--root',str(root),'resume','--full'],cwd=repo,text=True)
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


def test_role_policy_rejected_at_plan_before_claim_tests_or_build(case):
    root, state, evidence = case
    role_policy = put(root/'role-policy.json', {'hard_reference_ratio': .95, 'scored_window_seconds': 300})
    before = json.dumps(state)
    with pytest.raises(graph.GraphError, match='frozen build/resource policy'):
        graph.reduce(root, state, receipt(root, state, evidence, policy=role_policy))
    assert json.dumps(state) == before


def test_performance_flag_and_review_cannot_skip_dps_gate(case):
    root, state, evidence = reach(case, 'assess')
    state['development_graph']['requirements']['actor_1'].update(role='dps', spec='balance_druid')
    event = receipt(root, state, evidence, performance_accepted=True,
        baseline_matched=True, unexplained_material_decline=False,
        actor_reviews={'1': {'status': 'reviewed', 'receipt': evidence, 'accepted': True},
                      '2': {'status': 'not_exercised', 'reason': 'separate role'}})
    with pytest.raises(graph.GraphError, match='95% DPS gate'):
        graph.reduce(root, state, event)


def test_paused_support_refresh_preserves_native_unit_and_requires_new_tests(case):
    root, state, evidence = reach(case, 'implement')
    g = state['development_graph']
    prior = graph.git(root, 'rev-parse', 'HEAD')
    path = 'tools/raid_program/repair.py'
    (root/path).parent.mkdir(parents=True)
    (root/path).write_text('fixed workflow')
    review = put(root/'support-review.json', {'verdict': 'approved', 'reviewer_session_id': 'separate',
        'review_report': evidence, 'file_hashes': graph.snapshot(root, [path])})
    rec = put(root/'refresh.json', {'reason': 'user paused for reviewed workflow repair',
        'prior_commit': prior, 'supporting_review': review,
        'owned_file_hashes': graph.snapshot(root, ['code.cpp']),
        'prior_operation': {'ownership_checked': True, 'active_operation': False,
                            'operation_id': g['claim']['operation_id']}})
    event = {'action': 'refresh_support', 'revision': g['revision'], 'unit_id': g['unit']['id'],
             'claim_token': g['claim']['token'], 'receipt': rec}
    refreshed = graph.reduce(root, state, event)['development_graph']
    assert refreshed['stage'] == 'implement' and 'claim' not in refreshed
    assert refreshed['unit'] == g['unit']
    assert refreshed['assignment']['base_commit'] == g['assignment']['base_commit']
    assert refreshed['requirements'] == g['requirements']
    assert refreshed['assignment']['supporting_files'] == graph.snapshot(root, [path])
    assert not refreshed.get('tested_commit')
    (root/'code.cpp').write_text('different native code')
    with pytest.raises(graph.GraphError, match='cannot change native'):
        graph.reduce(root, state, event)


@pytest.mark.parametrize('stage,changes,match',[
    ('diagnose',{'producer':'jev'},'model advice'),
    ('diagnose',{'advice':{'jev':{}}},'adjudication'),
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


def test_diagnosis_can_advance_without_model_advice(case):
    root, state, evidence = case
    result = graph.reduce(root, state, receipt(root, state, evidence, advice={}))
    assert result['development_graph']['stage'] == 'implement'
    assert result['development_graph']['requirements'] == state['development_graph']['requirements']


def test_changed_code_invalidates_review(case):
    root,state,evidence=reach(case,'review')
    (root/'code.cpp').write_text('unreviewed change')
    with pytest.raises(graph.GraphError,match='commit source changes'):
        graph.reduce(root,state,receipt(root,state,evidence))


def test_renaming_producer_does_not_supply_a_separate_review(case):
    root, state, evidence = reach(case, 'review')
    with pytest.raises(graph.GraphError, match='reviewer_session_id'):
        graph.reduce(root, state, receipt(root, state, evidence, producer='independent-sounding-name', reviewer_session_id=None))
    with pytest.raises(graph.GraphError, match='separate reviewer response'):
        graph.reduce(root, state, receipt(root, state, evidence, review_report=state['development_graph']['receipts']['tests']))


def test_real_review_verifier_rejects_invented_session_label(case, monkeypatch):
    root, state, evidence = reach(case, 'review')
    monkeypatch.undo()  # Use real session verifier at this graph boundary.
    with pytest.raises(graph.GraphError, match='independent review execution'):
        graph.reduce(root, state, receipt(root, state, evidence,
            producer='looks-independent', reviewer_session_id='looks-independent'))


@pytest.mark.parametrize('mutation', ['content', 'symlink', 'executable'])
def test_separately_reviewed_support_preserves_native_delta_and_remains_frozen(case, mutation):
    root, state, evidence=case
    base=graph.git(root,'rev-parse','HEAD')
    support_file='tools/raid_program/workflow.py'
    (root/support_file).parent.mkdir(parents=True)
    (root/support_file).write_text('reviewed workflow fix')
    (root/'code.cpp').write_text('reviewed workflow fix')
    graph.git(root,'add',support_file,'code.cpp')
    graph.git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','separate changes')
    state['development_graph']['source_base_commit']=base
    review=put(root/'support-review.json',{'verdict':'approved','reviewer_session_id':'separate-reviewer',
        'review_report':evidence,'file_hashes':graph.snapshot(root,[support_file])})
    state=graph.reduce(root,state,receipt(root,state,evidence,base_commit=base,supporting_review=review))
    assignment=state['development_graph']['assignment']
    assert assignment['base_commit']==base and assignment['owned_files']==['code.cpp']
    assert set(assignment['supporting_files'])=={support_file}
    assert graph.git(root,'diff',base,'--','code.cpp') # Native patch was not hidden in a new base.
    graph.source_binding(root,assignment)
    if mutation == 'symlink':
        (root/support_file).unlink()
        (root/support_file).symlink_to('../../code.cpp') # Identical bytes, different source identity.
    elif mutation == 'executable':
        (root/support_file).chmod(0o755)
    else:
        (root/support_file).write_text('unreviewed support edit')
    graph.git(root,'add',support_file)
    graph.git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','changed support')
    with pytest.raises(graph.GraphError,match='supporting files changed'):
        graph.source_binding(root,assignment)


def test_reviewed_executable_precommit_hook_is_bounded_support(case):
    root, state, evidence = case
    base = graph.git(root, 'rev-parse', 'HEAD')
    path = '.githooks/pre-commit'
    (root/path).parent.mkdir()
    (root/path).write_text('#!/bin/sh\nexit 0\n')
    (root/path).chmod(0o755)
    graph.git(root, 'add', path)
    graph.git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
              'commit', '-qm', 'reviewed hook')
    state['development_graph']['source_base_commit'] = base
    review = put(root/'support-review.json', {'verdict': 'approved',
        'reviewer_session_id': 'separate-reviewer', 'review_report': evidence,
        'file_hashes': graph.snapshot(root, [path])})
    state = graph.reduce(root, state, receipt(root, state, evidence,
        base_commit=base, supporting_review=review))
    graph.source_binding(root, state['development_graph']['assignment'])
    (root/path).write_text('#!/bin/sh\nexit 1\n')
    graph.git(root, 'add', path)
    graph.git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
              'commit', '-qm', 'unreviewed hook')
    with pytest.raises(graph.GraphError, match='supporting files changed'):
        graph.source_binding(root, state['development_graph']['assignment'])


@pytest.mark.parametrize('path,selected', [('src/unowned.cpp',False), ('runtime.conf',False),
                                        ('tools/raid_program/input.py',True)])
def test_supporting_review_cannot_admit_native_or_selected_inputs(case,path,selected):
    root,state,evidence=case
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('unreviewed input')
    review=put(root/'support-review.json',{'verdict':'approved','reviewer_session_id':'separate-reviewer',
        'review_report':evidence,'file_hashes':graph.snapshot(root,[path])})
    event=receipt(root,state,evidence,supporting_review=review)
    if selected:
        r=graph.read(root/event['receipt']['path'])
        r['validation_identity']['extra_input']={'path':path,'sha256':graph.digest(target.read_bytes())}
        event['receipt']=put(root/event['receipt']['path'],r)
    with pytest.raises(graph.GraphError,match='supporting changes are limited'):
        graph.reduce(root,state,event)


def test_new_output_publication_does_not_invalidate_closed_run(case):
    root, state, evidence = reach(case, 'validate')
    event = receipt(root, state, evidence)
    folder = root/'artifacts/cata_raid_program'
    folder.mkdir(parents=True)
    (folder/'closed-run.tar.gz.dvc').write_text('outs:\n- md5: abc123\n  path: closed-run.tar.gz\n  size: 42\n')
    (folder/'.gitignore').write_text('/closed-run.tar.gz\n')
    graph.git(root,'add',str(folder))
    graph.git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','publish evidence')
    result = graph.reduce(root, state, event)
    assert result['development_graph']['stage'] == 'assess'
    assert result['development_graph']['build_identity'] == state['development_graph']['build_identity']


def test_retry_history_survives_edge_rename(case):
    root, state, evidence = case
    state = graph.reduce(root,state,{'action':'rework','revision':0,'unit_id':'u1','receipt':evidence,'reason':'observation absent'})
    root, state, evidence = reach((root,state,evidence), 'publish')
    state = graph.reduce(root,state,receipt(root,state,evidence))
    g=state['development_graph']
    state=graph.reduce(root,state,{'action':'route','revision':g['revision'],'unit_id':'u1','reason':'new actor cause',
        'unit':{'id':'u2','edge':'renamed-edge','requirements':['actor_1'],'next_action':'inspect'}})
    put(root/graph.STATE_PATH,state)
    resumed=graph.resume(root)
    assert resumed['same_edge_failures'] == 0
    assert resumed['failure_counts_by_edge']['edge1'] == 1
    assert resumed['recent_attempts'][0]['reason'] == 'observation absent'


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
    # Actor requirements close only from a scoreboard verdict, never a free-form review.
    with pytest.raises(graph.GraphError,match='only from a scoreboard verdict'):
        graph.reduce(root,state,receipt(root,state,evidence,accepted_requirements=['actor_1'],performance_accepted=True,baseline_matched=True,unexplained_material_decline=False,
            actor_reviews={'1':{'status':'reviewed','receipt':evidence,'accepted':True},'2':{'status':'not_exercised','reason':'fixture'}}))


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


def test_build_claim_rejects_stale_validation_before_claiming(case):
    root, state, evidence = reach(case, 'review')
    state = graph.reduce(root, state, receipt(root, state, evidence))
    (root / evidence['path']).write_text('{"changed":true}')
    with pytest.raises(graph.GraphError, match='pre-build validation failed.*hash mismatch'):
        claimed(root, state)
    assert not state['development_graph'].get('claim')


def test_build_claim_uses_real_calibration_preflight_and_preserves_failure(case, monkeypatch):
    from tools.bot_ml import run_live_bot_validation as live
    from tools.raid_program import workflow_build
    root, state, evidence = reach(case, 'review')
    monkeypatch.setattr(workflow_build, 'ROOT', root)
    state = graph.reduce(root, state, receipt(root, state, evidence))
    state['development_graph']['assignment']['validation_identity'].update(
        scenario_kind='dummy', spec='balance_druid', reference=evidence)
    monkeypatch.setattr(live, 'load_reference_request_binding', lambda spec: {
        'valid': False, 'reasons': ['catalog_fixture_contract_content_hash']})
    with pytest.raises(graph.GraphError, match='catalog_fixture_contract_content_hash'):
        claimed(root, state)
    assert not state['development_graph'].get('claim')
    monkeypatch.setattr(live, 'load_reference_request_binding', lambda spec: {'valid': True})
    assert claimed(root, state)['development_graph']['claim']['stage'] == 'build'


def test_dummy_prebuild_cannot_validate_another_checkouts_catalog(case):
    from tools.raid_program.workflow_build import preflight
    root, state, evidence = reach(case, 'review')
    assignment = state['development_graph']['assignment']
    assignment['validation_identity'].update(scenario_kind='dummy', spec='balance_druid', reference=evidence)
    with pytest.raises(ValueError, match="coordinator checkout's module"):
        preflight(root, assignment)


@pytest.mark.parametrize('outcome', ['success', 'configure_failure', 'source_changed', 'dirty_claim'])
def test_workflow_build_uses_one_source_and_queue_owned_receipts(case, monkeypatch, outcome):
    from tools.raid_program import workflow_build, queued_build as queue
    root, state, evidence=reach(case, 'build')
    policy_ref=put(root/'policy.json', json.loads(queue.DEFAULT_POLICY.read_text()))
    state['development_graph']['assignment']['policy']=policy_ref
    put(root/graph.STATE_PATH,state)
    graph.git(root,'add','-f',str(graph.STATE_PATH))
    graph.git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','claim')
    commands=[]
    def run(worktree, policy, kind, command, ticket, output, timeout):
        commands.append((kind, command))
        assert ticket is None and output is None
        queue.validate_command(command, policy['parallelism']['maximum_compiler_jobs'], resource_class=kind, policy=policy)
        if outcome == 'source_changed': (root/'code.cpp').write_text('changed after configure')
        failed=outcome == 'configure_failure'
        ticket = {'ticket_id':kind, 'resource_class':kind, 'worktree':str(root), 'classification':'failed' if failed else 'success',
                  'commit':graph.git(root,'rev-parse','HEAD'), 'exit_code':int(failed),
                  'source_identity_stable':True, 'test_mode':False,
                  'output_artifacts':[{'kind':'worldserver_elf','sha256':'b'*64,'produced_by_ticket':True,
                                       'path':str(root/'build/src/server/worldserver/worldserver')}]}
        put(queue.Paths.for_worktree(root).receipts / (kind+'.json'),ticket)
        return int(failed), ticket
    monkeypatch.setattr(queue,'run_ticket',run)
    if outcome == 'dirty_claim':
        saved=json.loads((root/graph.STATE_PATH).read_text()); saved['pending_note']='new claim state'
        put(root/graph.STATE_PATH,saved)
        with pytest.raises(ValueError,match='commit source, review and build claim'):
            workflow_build.run_build(root)
        assert not commands
    elif outcome == 'source_changed':
        with pytest.raises(ValueError,match='source changed between configure and build'):
            workflow_build.run_build(root)
        assert len(commands)==1
    else:
        result=workflow_build.run_build(root)
        assert result['success'] == (outcome=='success')
        assert [kind for kind,_ in commands] == (['configure','worldserver_build'] if outcome=='success' else ['configure'])
        if outcome=='success':
            assert commands[-1][1][-2:]==['--parallel','12']
            assert all('.git' in row['receipt'] for row in result['steps'])
            assert result['validated_transition'] == {'from':'build','to':'validate'}
            assert '--expect' in result['next_command']
            from tools.raid_program.build_handoff import finish_build
            assert finish_build(root)['receipt'] == result['receipt']
            with pytest.raises(ValueError, match='already has queue results'):
                workflow_build.run_build(root)
            assert len(commands) == 2


def test_published_unit_routes_to_next_task_without_losing_parent_or_assessment(case):
    # Exercise legitimate progress instead of pinning the live repository to a
    # historical Balance edge that must eventually close.
    root, state, evidence = reach(case, 'publish')
    assessment = state['development_graph']['receipts']['assessment']
    state = graph.reduce(root, state, receipt(root, state, evidence))
    g = state['development_graph']
    state = graph.reduce(root, state, {'action': 'route', 'revision': g['revision'],
        'unit_id': g['unit']['id'], 'reason': 'next proven actor edge',
        'unit': {'id': 'actor-next', 'edge': 'stat-application', 'requirements': ['actor_1'],
                 'owner_skill': 'raid-class-mechanics-implementation', 'next_action': 'Inspect retained stat producer'}})
    put(root/graph.STATE_PATH, state)
    output = subprocess.check_output([sys.executable, '-m', 'tools.raid_program.raid_workloop',
        '--root', str(root), 'resume', '--full'], cwd=Path(__file__).resolve().parents[1], text=True)
    status = json.loads(output)
    assert status['coordinator_skill'] == 'trinity-orchestrator'
    assert status['owner_skill'] == 'raid-class-mechanics-implementation'
    assert status['unit']['id'] == 'actor-next' and status['stage'] == 'diagnose'
    assert not status['parent_objective_complete']
    assert status['latest_assessment'] == assessment
    assert graph.file_ref(root, status['latest_assessment']).is_file()
    assert set(status['open_requirements']) == {'actor_1', 'actor_2'}
    assert status['completed_measurements'][0]['spec'] == 'Survival'
