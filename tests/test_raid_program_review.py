"""Round review (review-diff, review, the build gate), user decisions, handoff self-path and next actions."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools.raid_program import raid_program, raid_program_build as builds, raid_program_review as review
from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError

from tests.test_raid_program_rounds import (  # noqa: F401 - the world fixture is used by name
    accept_review, commit_all, fake_build, handoff, program, runner, sha, world)

REAL = Path(__file__).resolve().parents[1]
ALPHA_DIR = 'src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Alpha'
DECISION = {'id': 'nef_pillar', 'question': 'Hold the healerless pillar with the two tanks alone?',
            'options': ['tanks alone', 'add a healer'], 'recommendation': 'tanks alone',
            'context': 'WCL kills do both; the user tactic says tanks alone.'}


def planned(root: Path) -> None:
    """A committed checkout, then the plan (its commit is the round base)."""
    (root / '.gitignore').write_text('build/\n')
    (root / ALPHA_DIR).mkdir(parents=True)
    (root / ALPHA_DIR / 'alpha.cpp').write_text('// alpha v1\n')
    commit_all(root, 'program selected')
    rounds.plan(root)


def hand_off_all(root: Path) -> None:
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, external_reason='work in the tree')


def test_review_diff_sha_is_identical_before_and_after_the_commit(world, tmp_path_factory):
    root, out = world['root'], tmp_path_factory.mktemp('review')
    planned(root)
    hand_off_all(root)
    (root / ALPHA_DIR / 'alpha.cpp').write_text('// alpha v2\n')              # tracked change
    (root / ALPHA_DIR / 'alpha_new.cpp').write_text('// new file\n')          # untracked, included
    (root / 'build').mkdir()
    (root / 'build/object.o').write_text('ignored')                            # gitignored, excluded
    bookkeeping = root / 'artifacts/cata_raid_program/raid_programs/blackwing_descent_10n/round01'
    bookkeeping.mkdir(parents=True, exist_ok=True)
    (bookkeeping / 'note.json').write_text('{}\n')                             # program bookkeeping, excluded
    before = review.review_diff(root, out / 'before.diff')
    assert before['files'] == [f'{ALPHA_DIR}/alpha.cpp', f'{ALPHA_DIR}/alpha_new.cpp'] and not before['committed']
    assert (out / 'before.diff').read_bytes().startswith(b'diff --git a/')
    assert review.sha256((out / 'before.diff').read_bytes()) == before['diff_sha256']
    commit_all(root, 'round work and the program state')
    after = review.review_diff(root, out / 'after.diff')
    assert after['diff_sha256'] == before['diff_sha256'] == after['committed_diff_sha256'] and after['committed']
    assert review.committed_sha(root, program(root)) == before['diff_sha256']
    store.update(root, lambda state: state | {'focus': 'boss'})  # a state-only change never moves the sha
    assert review.review_diff(root, out / 'again.diff')['diff_sha256'] == before['diff_sha256']


def test_review_diff_output_stays_outside_the_tree(world):
    root = world['root']
    planned(root)
    with pytest.raises(GraphError, match='outside the source tree'):
        review.review_diff(root, root / 'review.diff')
    inside = root / 'artifacts/cata_raid_program/raid_programs/x/review.diff'  # bookkeeping is allowed
    assert review.review_diff(root, inside)['bytes'] == 0


def test_build_needs_an_accepted_review_of_exactly_the_committed_diff(world, tmp_path_factory):
    root, out = world['root'], tmp_path_factory.mktemp('review')
    planned(root)
    hand_off_all(root)
    (root / ALPHA_DIR / 'alpha.cpp').write_text('// alpha v2\n')
    reviewed = review.review_diff(root, out / 'r.diff')
    report = out / 'report.md'
    report.write_text('accept\n')
    review.record_review(root, 'accept', reviewed['diff_sha256'], 'reviewer-a', report)
    assert program(root)['stage'] == 'build'
    commit_all(root, 'reviewed round')
    (root / ALPHA_DIR / 'alpha.cpp').write_text('// alpha v3, after the review\n')
    commit_all(root, 'a source change after the review')
    with pytest.raises(GraphError, match='review: the committed round diff changed since the accepted review'):
        fake_build(root)
    again = review.review_diff(root, out / 'r2.diff')
    review.record_review(root, 'accept', again['diff_sha256'], 'reviewer-a', report)
    record = fake_build(root)
    assert record['success'] and record['gates']['review_diff_sha256'] == again['diff_sha256']
    assert record['gates']['reviewer'] == 'reviewer-a'


def test_an_accept_must_match_the_tree_and_a_reject_keeps_the_round_in_review(world, tmp_path_factory):
    root, out = world['root'], tmp_path_factory.mktemp('review')
    planned(root)
    hand_off_all(root)
    (root / ALPHA_DIR / 'alpha.cpp').write_text('// alpha v2\n')
    report = out / 'findings.md'
    report.write_text('P1: alpha.cpp breaks the tank swap\n')
    with pytest.raises(GraphError, match='matches neither the working tree nor HEAD'):
        review.record_review(root, 'accept', 'a' * 64, 'reviewer-a', report)
    with pytest.raises(GraphError, match='--report'):
        review.record_review(root, 'reject', 'a' * 64, 'reviewer-a', None)
    reviewed = review.review_diff(root, out / 'r.diff')['diff_sha256']
    review.record_review(root, 'reject', reviewed, 'reviewer-a', report, sha(root))
    view = raid_program.resume(root)
    assert view['stage'] == 'review' and view['review']['latest']['verdict'] == 'reject'
    assert 'rejected the round' in view['next_action'] and 'program reopen' in view['next_action']
    assert 'program fix' in view['next_action'] and 're-reviewed' in view['next_action']
    assert any('program reopen --id' in command for command in view['commands'])
    with pytest.raises(GraphError, match='not build'):  # a rejected round cannot build
        builds.build(root, runner=runner(), worktree_state=lambda root: {'clean': True, 'commit': 'c' * 40})
    rounds.reopen_packet(root, 'boss:alpha', 'P1: alpha.cpp breaks the tank swap')
    assert program(root)['stage'] == 'implement'
    rounds.record_handoff(root, 'boss:alpha', None, external_reason='fixed P1')
    assert program(root)['stage'] == 'review'
    accept_review(root, worktree=True)
    review.record_review(root, 'reject', reviewed, 'reviewer-b', report)  # a reject at build goes back to review
    assert program(root)['stage'] == 'review'


def test_a_round_without_source_change_is_closed_with_empty_diff(world):
    root = world['root']
    planned(root)
    hand_off_all(root)
    review.record_review(root, None, None, None, None, sha(root), empty_diff=True)
    latest = review.latest_review(rounds.current_round(program(root)))
    assert latest['automatic'] and latest['verdict'] == 'accept' and program(root)['stage'] == 'build'
    assert fake_build(root)['success']


def test_empty_diff_is_refused_when_the_round_changed_something(world):
    root = world['root']
    planned(root)
    hand_off_all(root)
    (root / ALPHA_DIR / 'alpha.cpp').write_text('// changed\n')
    with pytest.raises(GraphError, match='--empty-diff needs a round with no source change'):
        review.record_review(root, None, None, None, None, empty_diff=True)


def test_user_decisions_are_asked_block_the_build_and_are_recorded_verbatim(world):
    root = world['root']
    planned(root)
    rounds.record_handoff(root, 'boss:alpha', handoff(root, 'boss:alpha', [], needs_user_decision=[DECISION]))
    rounds.record_handoff(root, 'boss:beta', None, external_reason='x')
    view = raid_program.resume(root)
    assert view['next_action'].startswith('ASK THE USER') and DECISION['question'] in view['next_action']
    assert 'Recommendation: tanks alone' in view['next_action']
    assert view['commands'][0].startswith('pixi run python -m tools.raid_program.raid_workloop program decide '
                                          '--decision-id nef_pillar --answer')
    assert view['open_user_decisions'][0]['packet_id'] == 'boss:alpha'
    with pytest.raises(GraphError, match='decisions: ASK THE USER first: nef_pillar'):
        fake_build(root)
    words = 'Tanks alone.  The Feral pops Survival Instincts at 30%, not before!'
    raid_program.command(root, ['decide', '--decision-id', 'nef_pillar', '--answer', words, '--expect', sha(root)])
    row = rounds.current_round(program(root))['user_decisions'][0]
    assert row['answer']['text'] == words and row['answer']['source'] == 'user'
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['answer']['date'])
    assert not raid_program.resume(root)['next_action'].startswith('ASK THE USER')
    assert fake_build(root)['success']
    with pytest.raises(GraphError, match='no user decision'):
        review.decide(root, 'unknown', 'yes')


def test_decisions_are_validated_and_ids_stay_unique_across_packets(world):
    root = world['root']
    planned(root)
    for bad in ('not a list', [{'id': 'x'}], [DECISION, DECISION], [DECISION | {'options': [1]}]):
        with pytest.raises(GraphError, match='needs_user_decision'):
            rounds.record_handoff(root, 'boss:alpha', handoff(root, 'boss:alpha', [], needs_user_decision=bad))
    rounds.record_handoff(root, 'boss:alpha', handoff(root, 'boss:alpha', [], needs_user_decision=[DECISION]))
    with pytest.raises(GraphError, match='already used by boss:alpha'):
        rounds.record_handoff(root, 'boss:beta', handoff(root, 'boss:beta', [], needs_user_decision=[DECISION]))
    review.decide(root, 'nef_pillar', 'first answer')
    review.decide(root, 'nef_pillar', 'second answer')
    row = rounds.current_round(program(root))['user_decisions'][0]
    assert row['answer']['text'] == 'second answer' and row['previous_answers'][0]['text'] == 'first answer'


def test_a_handoff_may_list_its_own_save_as_path(world):
    root = world['root']
    planned(root)
    save_as = raid_program.packet(root, 'boss:alpha')['handoff']['save_as']
    own = handoff(root, 'boss:alpha', [f'{ALPHA_DIR}/alpha.cpp', save_as], new_files=[save_as])
    rounds.record_handoff(root, 'boss:alpha', own)
    record = rounds.current_round(program(root))['packets']['boss:alpha']['handoff']
    assert record['changed_files'] == [f'{ALPHA_DIR}/alpha.cpp'], 'the self path is bookkeeping, not a change'
    with pytest.raises(GraphError, match='outside its packet'):  # only a packet's own save_as is exempt
        rounds.record_handoff(root, 'boss:beta', handoff(root, 'boss:beta', [save_as]))
    beta_own = save_as.replace('boss_alpha.handoff.json', 'boss_beta.handoff.json')
    rounds.record_handoff(root, 'boss:beta', handoff(root, 'boss:beta', [], new_files=[beta_own]))
    assert program(root)['stage'] == 'review'


def test_the_worker_packet_advertises_decisions_and_the_self_path(world):
    root = world['root']
    planned(root)
    contract = raid_program.packet(root, 'boss:alpha')['handoff']
    assert contract['optional_fields'] == {'needs_user_decision': 'list'}
    assert set(contract['needs_user_decision_item']) == {'id', 'question', 'options', 'recommendation', 'context'}
    assert 'save_as' in contract['self_path']


def test_every_stage_names_its_tracker_commands(world):
    root = world['root']
    planned(root)
    hand_off_all(root)
    view = raid_program.resume(root)
    text, commands = view['next_action'], ' '.join(view['commands'])
    for name in ('program refresh-data', 'program review-diff', 'program review', '--empty-diff', 'test_baseline check'):
        assert name in text + commands, name
    assert '--verdict accept|reject --diff-sha256' in commands and '--output ~/.cache/' in commands
    accept_review(root)
    build = raid_program.resume(root)
    assert 'program build --dry-run' in ' '.join(build['commands']) and 'gates' in build['next_action']
    fake_build(root)
    from tools.raid_program import raid_program_runs as runs
    runs.run_plans(root)
    run = raid_program.resume(root)
    assert run['commands'][0].startswith('pixi run python -m tools.raid_program.raid_workloop program run-batches '
                                         '--label ')
    assert 'program assess --label' in run['commands'][1] and '--gdb-backtrace' in ' '.join(run['commands'])
    for view in (build, run):
        assert not re.search(r'/tmp/\S+\.py', view['next_action'] + ' '.join(view['commands'])), 'no /tmp scripts'


def test_the_saved_round2_program_loads_and_is_not_gated(world):
    """Migration: the real state (round 2, built without a review, at run/assess) loads unchanged."""
    root = world['root']
    real = json.loads((REAL / store.STATE_PATH).read_text())
    real['coordinator_worktree'] = str(root)
    (root / store.STATE_PATH).write_text(json.dumps(real, indent=2) + '\n')
    state, _ = store.load(root)
    store.check(root, state)
    current = rounds.active(state)
    if current['stage'] != 'run' or current['round'] != 2:
        pytest.skip('the saved program has moved past round 2 run')
    assert not rounds.current_round(current).get('reviews') and rounds.current_round(current)['build']['success']
    view = raid_program.resume(root)
    assert view['stage'] == 'run' and view['review'] is None and not view['open_user_decisions']
    assert view['commands'][0].split(' --label ')[0].endswith('program run-batches')


def test_a_pre_review_state_in_build_is_gated_from_its_next_build(world):
    root = world['root']
    planned(root)
    hand_off_all(root)
    store.update(root, lambda state: (rounds.active(state).update(stage='build'), state)[1])  # saved before 'review'
    with pytest.raises(GraphError, match='review: no review of this round is recorded'):
        fake_build(root)
    accept_review(root)  # program review is accepted at the build stage too
    assert fake_build(root)['success']
