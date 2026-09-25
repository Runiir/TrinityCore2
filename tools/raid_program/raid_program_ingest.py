"""Record a round's shard kills in the scoreboard with archived evidence.

For every recorded shard run of the round and every shard whose boss has a raid
target, ``ingest`` archives the shard's run directory to DVC under
``artifacts/cata_raid_program/`` (``scoreboard_run.archive_evidence``, the same
path ``scoreboard run`` uses) and appends one kill record with that
``evidence_dvc_pointer``, the run's worldserver sha256 (checked against the
round build) and the round build's source commit. A kill without a pointer is
never counted (``no_evidence``), so an archive failure records nothing and the
command can be repeated. Kill ids are ``<label>-<run_id>-<cohort>``: repeated
runs of one batch never collide. A round uses one label.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError, utc_now

Archiver = Callable[[Path, str, str, list[Path], set[str]], tuple[str | None, str | None]]
Recorder = Callable[..., dict]


def _archive(root: Path, scenario: str, kill_id: str, sources: list[Path], pointers: set[str]):
    from tools.raid_program.scoreboard_run import archive_evidence
    return archive_evidence(root, scenario, kill_id, sources, pointers)


def _record_kill(root: Path, *, scenario: str, label: str, kill_id: str, run_dir: Path, pointer: str,
                 worldserver_sha256: str, source_commit: str) -> dict:
    from tools.raid_program.scoreboard_core import append_record, load_target
    from tools.raid_program.scoreboard_record import record_from_run_dir, write_timeline
    target = load_target(root, scenario)
    options = dict(scenario=scenario, label=label, kill_id=kill_id, run_dir=run_dir, source_commit=source_commit,
                   worldserver_sha256=worldserver_sha256, evidence_pointer=pointer)
    with tempfile.TemporaryDirectory(prefix='raid-program-timeline-') as temp:
        timeline = (write_timeline(run_dir, root / target['wcl_cast_timelines'], Path(temp) / 'timeline.json')
                    if target.get('wcl_cast_timelines') else None)
        record = record_from_run_dir(root, target, timeline_path=timeline, **options)
    record['worldserver_sha256'] = worldserver_sha256
    append_record(root, scenario, record)
    return record


def _recorded(root: Path, scenario: str) -> tuple[dict[str, dict], set[str]]:
    from tools.raid_program.scoreboard_core import load_records
    records = load_records(root, scenario)
    return ({record['kill_id']: record for record in records},
            {record['evidence_dvc_pointer'] for record in records if record.get('evidence_dvc_pointer')})


def ingest(root: Path, label: str, expected_sha256: str | None = None,
           archive: Archiver | None = None, record_kill: Recorder | None = None) -> dict:
    _, program, data = rounds.load_active(root)
    rounds.require(program, 'run')
    rounds.check_expected(data, expected_sha256)
    holder = rounds.current_round(program)
    if not label:
        raise GraphError('program ingest needs --label')
    if holder.get('label') and holder['label'] != label:
        raise GraphError(f"this round already ingests under label {holder['label']}")
    build = holder.get('build') or {}
    if not build.get('worldserver_sha256') or not build.get('source_commit'):
        raise GraphError('the round has no recorded build to bind kills to')
    units = {unit['cohort_id']: unit for unit in rounds.discover(root, program)['units']}
    done = {(row['run_sha256'], row['cohort_id']) for row in holder.get('ingested') or []}
    archive, record_kill = archive or _archive, record_kill or _record_kill
    added, errors, skipped = [], [], []
    for run in holder['runs']:
        if run.get('failed'):
            continue
        for shard in run['shards']:
            unit = units.get(shard['cohort_id'])
            if unit is None or not unit['raid_target']['present']:
                skipped.append({'cohort_id': shard['cohort_id'], 'reason': 'no raid target'})
                continue
            if (run['sha256'], shard['cohort_id']) in done:
                continue
            if run.get('worldserver_sha256') != build['worldserver_sha256']:
                errors.append({'cohort_id': shard['cohort_id'], 'error': 'run binary differs from the round build'})
                continue
            run_dir = Path(str(shard.get('run_dir') or ''))
            scenario = unit['raid_target']['scenario']
            kill_id = f"{label}-{run.get('run_id') or run['sha256'][:12]}-{shard['cohort_id']}"
            known, pointers = _recorded(root, scenario)
            if kill_id in known and known[kill_id].get('evidence_dvc_pointer'):
                pointer = known[kill_id]['evidence_dvc_pointer']  # an earlier ingest recorded it; adopt
            else:
                if kill_id in known:
                    errors.append({'cohort_id': shard['cohort_id'], 'error': f'{kill_id} is recorded without evidence'})
                    continue
                if not run_dir.is_dir():
                    errors.append({'cohort_id': shard['cohort_id'], 'error': f'run dir missing: {run_dir}'})
                    continue
                pointer, error = archive(root, scenario, kill_id, [run_dir], pointers)
                if not pointer:
                    errors.append({'cohort_id': shard['cohort_id'], 'error': error or 'archive failed'})
                    continue
                record_kill(root, scenario=scenario, label=label, kill_id=kill_id, run_dir=run_dir, pointer=pointer,
                            worldserver_sha256=build['worldserver_sha256'], source_commit=build['source_commit'])
            added.append({'run_sha256': run['sha256'], 'cohort_id': shard['cohort_id'], 'boss_key': unit['boss_key'],
                          'scenario': scenario, 'kill_id': kill_id, 'evidence_dvc_pointer': pointer, 'utc': utc_now()})
            done.add((run['sha256'], shard['cohort_id']))

    def reducer(state: dict) -> dict:
        target = rounds.active(state)
        rounds.require(target, 'run')
        current = rounds.current_round(target)
        current['label'] = label
        current.setdefault('ingested', []).extend(added)
        store.history(target, 'ingest', round=target['round'], label=label, kills=len(added), errors=len(errors))
        return state
    store.update(root, reducer)
    return {'label': label, 'ingested': added, 'errors': errors, 'skipped': skipped}
