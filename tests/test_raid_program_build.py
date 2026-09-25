"""Raid-program build ownership check, build adoption (--finish) and evidence-backed ingest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.raid_program import raid_program_build as builds, raid_program_ingest as ingests
from tools.raid_program import raid_program_rounds as rounds, raid_program_runs as runs
from tools.raid_program.development_graph import GraphError

from tests.test_raid_program_rounds import (  # noqa: F401 - the world fixture is used by name
    BINARY, RAID, both, commit_all, fake_build, program, runner, shard_run, world,
)

GOOD = lambda path, policy: {'gate_bearing': True, 'classification': 'success'}  # noqa: E731


def to_build(root: Path) -> None:
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, external_reason='work in the commits below')


def test_build_refuses_a_file_two_packets_can_own(world):
    root = world['root']
    commit_all(root, 'program selected')
    rounds.plan(root)
    assert rounds.current_round(program(root))['plan_commit']
    to_build(root)
    (root / 'sql/w').mkdir(parents=True)
    (root / 'sql/w/2026_alpha.sql').write_text('-- alpha only\n')
    commit_all(root, 'alpha work')
    dry = builds.build(root, dry_run=True)
    assert dry['ownership']['owned'] == {'sql/w/2026_alpha.sql': 'boss:alpha'} and not dry['ownership']['conflicts']
    (root / 'sql/w/alpha_beta.sql').write_text('-- both\n')
    commit_all(root, 'ambiguous file')
    assert builds.build(root, dry_run=True)['ownership']['conflicts'] == {'sql/w/alpha_beta.sql': ['boss:alpha', 'boss:beta']}
    with pytest.raises(GraphError, match='two packets'):
        fake_build(root)
    assert program(root)['stage'] == 'build'


def _ticket(tmp: Path, root: Path, commit: str, **overrides) -> Path:
    ticket = {'worktree': str(root), 'resource_class': 'worldserver_build', 'commit': commit,
              'output_artifacts': [{'kind': 'worldserver_elf', 'produced_by_ticket': True, 'sha256': BINARY}]} | overrides
    path = tmp / 'ticket.json'
    path.write_text(json.dumps(ticket))
    return path


def test_finish_adopts_a_completed_ticket_of_this_round(world, tmp_path_factory):
    root, tmp = world['root'], tmp_path_factory.mktemp('queue')
    planned = commit_all(root, 'program selected')
    rounds.plan(root)
    to_build(root)
    launched = commit_all(root, 'build stage committed')
    with pytest.raises(GraphError, match='another worktree'):
        builds.finish(root, _ticket(tmp, root, launched, worktree=str(tmp)), verifier=GOOD)
    with pytest.raises(GraphError, match="round's build stage"):
        builds.finish(root, _ticket(tmp, root, planned), verifier=GOOD)
    with pytest.raises(GraphError, match='gate-bearing'):
        builds.finish(root, _ticket(tmp, root, launched), verifier=lambda path, policy: {'gate_bearing': False})
    (root / 'src').mkdir()
    (root / 'src/late.cpp').write_text('// late\n')
    commit_all(root, 'a source change after the ticket')
    with pytest.raises(GraphError, match='more than coordination files'):
        builds.finish(root, _ticket(tmp, root, launched), verifier=GOOD)
    (root / 'src/late.cpp').unlink()
    commit_all(root, 'revert the source change')
    # The tree comparison is what binds the binary: a reverted source change leaves it valid.
    assert builds.finish(root, _ticket(tmp, root, launched), verifier=GOOD)['source_commit'] == launched


def test_finish_adopts_after_coordination_only_commits(world, tmp_path_factory):
    root, tmp = world['root'], tmp_path_factory.mktemp('queue')
    commit_all(root, 'program selected')
    rounds.plan(root)
    to_build(root)
    launched = commit_all(root, 'build stage committed')
    (root / 'artifacts/cata_raid_program/note.json').write_text('{}\n')
    commit_all(root, 'coordination-only commit')
    record = builds.finish(root, _ticket(tmp, root, launched), verifier=GOOD)
    assert record['adopted'] and record['success'] and record['worldserver_sha256'] == BINARY
    assert program(root)['stage'] == 'run' and rounds.current_round(program(root))['build']['source_commit'] == launched


def test_finish_refuses_ownership_conflicts_like_build(world, tmp_path_factory):
    root, tmp = world['root'], tmp_path_factory.mktemp('queue')
    commit_all(root, 'program selected')
    rounds.plan(root)
    to_build(root)
    (root / 'sql/w').mkdir(parents=True)
    (root / 'sql/w/alpha_beta.sql').write_text('-- both\n')
    launched = commit_all(root, 'build stage with an ambiguous file')
    with pytest.raises(GraphError, match='two packets'):
        builds.finish(root, _ticket(tmp, root, launched), verifier=GOOD)
    assert program(root)['stage'] == 'build'


def test_ingest_records_before_a_deleting_archiver_with_the_real_recorder(world):
    """The archiver removes its /tmp sources (as experiments.archive_run_evidence does); records are built first."""
    import shutil
    from tools.raid_program.scoreboard_core import exclusion_reason, load_records
    root = world['root']
    seen = []

    def deleting(root, scenario, kill_id, sources, pointers):
        seen.append({Path(path).name: sorted(child.name for child in Path(path).iterdir()) if Path(path).is_dir() else None
                     for path in sources if Path(path).exists()})
        for path in sources:
            if Path(path).is_dir():
                shutil.rmtree(path)
            elif Path(path).exists():
                Path(path).unlink()
        return f'artifacts/cata_raid_program/scoreboard_{scenario}_{kill_id}.tar.gz.dvc', None
    rounds.plan(root)
    to_build(root)
    fake_build(root)
    runs.run_plans(root)
    first, second = shard_run(root, 'r1a', both()), shard_run(root, 'r1b', both())
    runs.record_run(root, first)
    runs.record_run(root, second)  # the same batch again, a new output directory
    result = ingests.ingest(root, 'round1', archive=deleting)
    assert not result['errors'] and len(result['ingested']) == 4
    for boss in ('alpha', 'beta'):
        records = load_records(root, f'{RAID}_10n_{boss}')
        assert len({record['kill_id'] for record in records}) == 2
        for record in records:
            assert record['outcome'] == 'clear' and record['native_clear'] is True, record.get('postprocess_error')
            assert record['evidence_dvc_pointer'] and exclusion_reason(record) is None
            assert record['worldserver_sha256'] == BINARY and record['source_commit'] == 'c' * 40
            assert not Path(record['run_dir']).exists(), 'the archiver removed the run dir after the record was built'
    kills = [entry for entry in seen if any(name.endswith('-analysis') for name in entry)]
    assert len(kills) == 4 and all('summary.json' in next(v for k, v in entry.items() if k.endswith('-analysis'))
                                   for entry in kills), 'the kept analysis dir is archived with the kill'
    assert not first.exists() and not second.exists(), 'batch files are archived too'
    assert ingests.ingest(root, 'round1', archive=deleting)['ingested'] == [], 'recorded kills are adopted, not redone'


def test_ingest_needs_a_recorded_build(world):
    root = world['root']
    rounds.plan(root)
    to_build(root)
    with pytest.raises(GraphError, match='not run'):
        ingests.ingest(root, 'lbl')
