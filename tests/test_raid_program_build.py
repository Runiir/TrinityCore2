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


def _scoreboard_fakes(monkeypatch, archive_error: list[str]):
    from tools.raid_program import scoreboard_core, scoreboard_record, scoreboard_run

    def archive(root, scenario, kill_id, sources, pointers):
        if archive_error:
            return None, archive_error.pop()
        return f'artifacts/cata_raid_program/scoreboard_{scenario}_{kill_id}.tar.gz.dvc', None

    def record(root, target, *, scenario, label, kill_id, run_dir, timeline_path, source_commit,
               worldserver_sha256=None, evidence_pointer=None, summary_output=None):
        return {'schema': scoreboard_core.KILL_SCHEMA, 'kill_id': kill_id, 'scenario': scenario, 'label': label,
                'run_dir': str(run_dir), 'evidence_dvc_pointer': evidence_pointer, 'source_commit': source_commit,
                'worldserver_sha256': worldserver_sha256, 'native_clear': True, 'outcome': 'clear',
                'measurement_validity': {'valid_for_dps': True}}
    monkeypatch.setattr(scoreboard_run, 'archive_evidence', archive)
    monkeypatch.setattr(scoreboard_core, 'load_target', lambda root, scenario: {'encounter_route_node_id': 'n'})
    monkeypatch.setattr(scoreboard_record, 'record_from_run_dir', record)


def test_ingest_records_counted_kills_with_evidence(world, monkeypatch):
    from tools.raid_program.scoreboard_core import exclusion_reason, load_records
    root = world['root']
    failures = ['archive_run_evidence failed (exit 1)']
    _scoreboard_fakes(monkeypatch, failures)
    rounds.plan(root)
    to_build(root)
    fake_build(root)
    runs.run_plans(root)
    runs.record_run(root, shard_run(root, 'r1a', both()))
    runs.record_run(root, shard_run(root, 'r1b', both()))  # the same batch again, a new output directory
    first = ingests.ingest(root, 'round1')
    assert len(first['errors']) == 1 and len(first['ingested']) == 3, 'one failed archive records nothing'
    second = ingests.ingest(root, 'round1')
    assert len(second['ingested']) == 1 and not second['errors'], 'the retry records only the missing kill'
    assert ingests.ingest(root, 'round1')['ingested'] == [], 'ingest is idempotent'
    with pytest.raises(GraphError, match='already ingests under label round1'):
        ingests.ingest(root, 'other')
    for boss in ('alpha', 'beta'):
        records = load_records(root, f'{RAID}_10n_{boss}')
        assert len({record['kill_id'] for record in records}) == 2
        for record in records:
            assert record['evidence_dvc_pointer'].endswith('.tar.gz.dvc') and exclusion_reason(record) is None
            assert record['worldserver_sha256'] == BINARY and record['source_commit'] == 'c' * 40
    assert rounds.current_round(program(root))['label'] == 'round1'


def test_ingest_needs_a_recorded_build(world):
    root = world['root']
    rounds.plan(root)
    to_build(root)
    with pytest.raises(GraphError, match='not run'):
        ingests.ingest(root, 'lbl')
