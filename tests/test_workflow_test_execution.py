"""Run real subprocesses and graph transitions; never certify native gameplay."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from tests.test_development_graph import case, put, receipt, claimed
from tests.test_workflow_handoffs import commit
from tools.raid_program import development_graph as graph
from tools.raid_program.workflow_step import apply_step, main
from tools.raid_program.workflow_tests import amend, run_tests


def command(code):
    return shlex.join([sys.executable, '-c', code])


def ready(case, commands):
    root, state, evidence = case
    state = graph.reduce(root, state, receipt(root, state, evidence, required_test_commands=commands))
    state = claimed(root, state)
    put(root/graph.STATE_PATH, state)
    return root, state


def run(root, behavior, **kwargs):
    return run_tests(root, owner='fixture-tab', producer='actual-implementer-session',
                     behavior_command=behavior, **kwargs)


def test_required_fixture_amendment_then_real_execution_preserves_objective(case):
    behavior = command("import runpy; assert runpy.run_path('tests/support.py')['result'] == [100, 80]")
    root, state = ready(case, [behavior])
    prior = state['development_graph']
    failed = run(root, behavior)
    assert not failed['success'] and failed['next_command'] is None
    # Repeating unchanged commands returns the retained failure, not another execution.
    assert run(root, behavior) == failed
    fixture = root/'tests/support.py'
    fixture.parent.mkdir()
    fixture.write_text('result = [100, 80]\n')
    result = amend(root, files=['tests/support.py'], commands=[behavior],
                   reason='Existing behavior fixture requires the new dependency', owner='fixture-tab')
    current = graph.read(root/graph.STATE_PATH)['development_graph']
    assert result['from_stage'] == result['to_stage'] == 'implement'
    for key in ('claim', 'unit', 'requirements', 'failures', 'source_base_commit'):
        assert current.get(key) == prior.get(key)
    assert current['assignment']['base_commit'] == prior['assignment']['base_commit']
    assert current['assignment']['required_test_commands'] == [behavior]
    commit(root, 'tests/support.py')
    passed = run(root, behavior)
    assert passed['success'] and '--expect' in passed['next_command']
    assert run(root, behavior) == passed
    r = graph.read(root/passed['receipt'])
    assert r['producer'] == 'actual-implementer-session'
    assert set(r['file_hashes']) == {'code.cpp', 'tests/support.py'}
    assert (root/failed['receipt']).is_file()
    transition = apply_step(root, passed['receipt'], owner='fixture-tab')
    assert transition['stage'] == 'review'
    assert graph.read(root/graph.STATE_PATH)['development_graph']['requirements'] == prior['requirements']


@pytest.mark.parametrize('problem', ['source', 'escape', 'link', 'missing_reason', 'wrong_owner', 'stale', 'no_addition', 'review'])
def test_amendment_rejects_broader_changes_and_stale_ownership(case, problem):
    cmd = command('pass')
    root, state = ready(case, [cmd])
    (root/'tests').mkdir()
    (root/'tests/support.py').write_text('pass')
    files, reason, owner, expect = ['tests/support.py'], 'dependency', 'fixture-tab', None
    if problem == 'source': files = ['code.cpp']
    if problem == 'escape': files = ['tests/../code.cpp']
    if problem == 'link':
        (root/'tests/link.py').symlink_to(root/'code.cpp'); files = ['tests/link.py']
    if problem == 'missing_reason': reason = ''
    if problem == 'wrong_owner': owner = 'other'
    if problem == 'stale': expect = '0'*64
    if problem == 'no_addition': files = []
    if problem == 'review':
        state['development_graph']['stage'] = 'review'
        state['development_graph'].pop('claim')
        put(root/graph.STATE_PATH, state)
    before = (root/graph.STATE_PATH).read_bytes()
    with pytest.raises(graph.GraphError):
        amend(root, files=files, commands=[cmd], reason=reason, owner=owner, expected=expect)
    assert (root/graph.STATE_PATH).read_bytes() == before


def test_amendment_preview_and_cli_preserve_original_tests(case, capsys):
    one, two = command('pass'), command('assert 1 == 1')
    root, state = ready(case, [one])
    argv = ['--root', str(root), 'amend-tests', '--command', two, '--reason', 'neighboring boundary', '--owner', 'fixture-tab']
    before = (root/graph.STATE_PATH).read_bytes()
    assert main(argv + ['--dry-run']) == 0
    assert (root/graph.STATE_PATH).read_bytes() == before
    assert main(argv) == 0
    assert graph.read(root/graph.STATE_PATH)['development_graph']['assignment']['required_test_commands'] == [one, two]
    from tools.raid_program.evidence_task import task_summary
    assert task_summary(root, 'unit')['test_plan']['required_test_commands'] == [one, two]
    assert main(['--root', str(root), 'tests', '--owner', 'fixture-tab', '--producer', 'session', '--behavior-command', two]) == 0
    assert len(capsys.readouterr().out) < 6000


def test_runner_retains_all_failures_even_if_later_test_passes(case):
    bad, good = command("raise AssertionError('counterexample')"), command('pass')
    root, state = ready(case, [bad, good])
    result = run(root, good)
    assert [t['exit_status'] for t in result['tests']] == [1, 0]
    assert not result['success'] and result['next_command'] is None
    with pytest.raises(graph.GraphError, match='required test did not pass'):
        apply_step(root, result['receipt'], owner='fixture-tab')


@pytest.mark.parametrize('mutation', ["open('code.cpp','w').write('changed')", "import json; p='experiments/configs/cata_raid_active_work_unit_v1.json'; d=json.load(open(p)); d['note']='changed'; json.dump(d,open(p,'w'))"])
def test_runner_detects_source_or_state_mutation_during_test(case, mutation):
    cmd = command(mutation)
    root, state = ready(case, [cmd])
    result = run(root, cmd)
    assert result['tests'][0]['exit_status'] == 0
    assert not result['success'] and not result['source_and_state_stable']
    assert result['next_command'] is None


def test_timeout_and_pipe_failure_are_not_success(case):
    slow = command('import time; time.sleep(10)')
    root, state = ready(case, [slow, 'false | true'])
    result = run(root, slow, timeout=.1)
    assert result['tests'][0]['timed_out']
    assert [t['exit_status'] for t in result['tests']] == [124, 1]
    assert not result['success']


def test_large_output_stays_in_hash_bound_artifact_and_cache_checks_it(case, capsys):
    cmd = command("print('x'*1000000)")
    root, state = ready(case, [cmd])
    result = run(root, cmd)
    assert result['success']
    assert len(json.dumps(result)) < 2000
    assert not capsys.readouterr().out
    r = graph.read(root/result['receipt'])
    ref = r['evidence'][0]
    assert len(''.join(graph.read(root/ref['path'])['output_chunks'])) == 1000001
    (root/ref['path']).write_text('{}')
    with pytest.raises(graph.GraphError, match='hash'):
        run(root, cmd)


def test_unselected_behavior_command_never_executes(case):
    cmd = command('pass')
    root, _ = ready(case, [cmd])
    with pytest.raises(graph.GraphError, match='declared command'):
        run(root, 'undeclared command')
    assert not (root/'artifacts').exists()


def test_interruption_preserves_raw_output_without_polluting_source(case, monkeypatch):
    cmd = command('import time; time.sleep(10)')
    root, state = ready(case, [cmd])
    original = subprocess.Popen.wait
    interrupted = False

    def wait(process, *args, **kwargs):
        nonlocal interrupted
        if process.args[0] == 'bash' and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return original(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, 'wait', wait)
    before = (root/graph.STATE_PATH).read_bytes()
    with pytest.raises(KeyboardInterrupt):
        run(root, cmd)
    assert (root/graph.STATE_PATH).read_bytes() == before
    pending = next((root/'artifacts/cata_raid_program').glob('tests-*/pending.json'))
    raw = Path(graph.read(pending)['raw_output'])
    assert raw.is_file() and '.git' in raw.parts
    graph.source_binding(root, state['development_graph']['assignment'])
    with pytest.raises(graph.GraphError, match='capture interrupted'):
        run(root, cmd)


def test_duplicate_pass_cannot_hide_failure_and_unstable_receipt_rejected(case):
    cmd = command('pass')
    root, state = ready(case, [cmd])
    for changes in ({'tests': [{'command': cmd, 'exit_status': 1}, {'command': cmd, 'exit_status': 0}]},
                    {'tests': [{'command': cmd, 'exit_status': 0}], 'source_and_state_stable': False}):
        with pytest.raises(graph.GraphError):
            graph.reduce(root, state, receipt(root, state, {'path': 'native.json', 'sha256': graph.digest((root/'native.json').read_bytes())}, **changes))
