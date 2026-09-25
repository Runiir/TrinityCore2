"""Record a round's shard kills in the scoreboard, then archive their evidence.

Mirrors ``scoreboard_run.run_kill`` for every shard of a boss with a raid
target, in this order:

1. build the kill record from the still-present run directory
   (``scoreboard_run.record_kill``, shared with ``run_kill``: ``record_from_run_dir``,
   falling back to ``fallback_record``; timeline and summary go to a kept
   ``<run_dir>-analysis``);
2. archive the evidence (``scoreboard_run.archive_evidence``, which adds, pushes
   and verifies the DVC pointer and then deletes the /tmp sources);
3. append the record with its ``evidence_dvc_pointer``, or with
   ``archive_error`` and ``evidence_paths`` so ``scoreboard archive-pending``
   can retry.

Shards without a raid target and each batch's run-root files (shard_run.json,
console journal, logs) are archived too; their pointers are stored in the
program state. Kill ids are ``<label>-<run_id>-<cohort>``, so repeated runs of
one batch never collide, and a kill already in the scoreboard is adopted
rather than recorded twice. A round uses one label. Post-processing and
archive output (including the archive subprocess) goes to stderr, so the
command's JSON is the only stdout.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_runs as runs
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError, utc_now

Archiver = Callable[[Path, str, str, list[Path], set[str]], tuple[str | None, str | None]]


def _archive(root: Path, scenario: str, kill_id: str, sources: list[Path], pointers: set[str]):
    from tools.raid_program.scoreboard_run import archive_evidence
    return archive_evidence(root, scenario, kill_id, sources, pointers)


def _kill(run_dir: Path, kill_id: str) -> dict:
    """The run_kill layout: the shard dir, a kept analysis dir beside it, no harness stdout/stderr."""
    return {'kill_id': kill_id, 'output_dir': run_dir, 'analysis_dir': Path(f'{run_dir}-analysis'),
            'stdout': Path(f'{run_dir}.stdout'), 'stderr': Path(f'{run_dir}.stderr')}


def record_then_archive(root: Path, *, scenario: str, label: str, kill: dict, worldserver_sha256: str,
                        source_commit: str, archive: Archiver) -> dict:
    """One kill as scoreboard_run.run_kill does it: record from the live dir, archive, then append."""
    from tools.raid_program.play_mode_guard import refuse_play
    from tools.raid_program.scoreboard_core import append_record, load_records, load_target
    from tools.raid_program.scoreboard_run import evidence_sources, record_kill
    refuse_play(kill['output_dir'], f"raid program ingest {kill['kill_id']}")
    target = load_target(root, scenario)
    record = record_kill(root, target, scenario=scenario, label=label, kill=kill, sha=worldserver_sha256,
                         source_commit=source_commit)
    record['worldserver_sha256'] = worldserver_sha256  # the round binary the run was bound to
    record['evidence_paths'] = [str(path) for path in evidence_sources(kill) if path.exists()]
    pointers = {row['evidence_dvc_pointer'] for row in load_records(root, scenario) if row.get('evidence_dvc_pointer')}
    try:
        pointer, error = archive(root, scenario, kill['kill_id'], evidence_sources(kill), pointers)
    except Exception as failure:  # noqa: BLE001 - recorded like run_kill; archive-pending retries
        pointer, error = None, f'{type(failure).__name__}: {failure}'
    record['evidence_dvc_pointer'] = pointer
    if error:
        record['archive_error'] = error
    append_record(root, scenario, record)
    return record


def ingest(root: Path, label: str, expected_sha256: str | None = None, archive: Archiver | None = None) -> dict:
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
    from tools.raid_program.scoreboard_core import load_records
    units = {unit['cohort_id']: unit for unit in rounds.discover(root, program)['units']}
    done = {(row['run_sha256'], row['cohort_id']): row for row in holder.get('ingested') or []}
    archived = {(row['run_sha256'], row['cohort_id']) for row in holder.get('shard_evidence') or []}
    archive = archive or _archive
    slug = program['program_id'].replace(':', '_').lower()
    added, shard_evidence, batch_evidence, errors, voided = [], [], {}, [], []
    for run in holder['runs']:
        if run.get('failed'):
            continue
        for shard in run['shards']:
            key, run_dir = (run['sha256'], shard['cohort_id']), Path(str(shard.get('run_dir') or ''))
            unit = units.get(shard['cohort_id'])
            if unit is None or not unit['raid_target']['present']:
                if key in archived or not run_dir.is_dir():
                    continue
                with runs.stdout_to_stderr():
                    pointer, error = archive(root, f'{slug}_shards', f"{run.get('run_id')}-{shard['cohort_id']}", [run_dir], set())
                shard_evidence.append({'run_sha256': run['sha256'], 'cohort_id': shard['cohort_id'],
                                       'evidence_dvc_pointer': pointer, 'archive_error': error})
                if error:
                    errors.append({'cohort_id': shard['cohort_id'], 'error': 'shard evidence archive: ' + error})
                continue
            if key in done:
                scenario, kill_id = done[key]['scenario'], done[key]['kill_id']
                recorded = next((row for row in load_records(root, scenario) if row['kill_id'] == kill_id), {})
                if recorded.get('voided'):  # excluded with an audited reason: reported, never an exit error
                    voided.append({'cohort_id': shard['cohort_id'], 'kill_id': kill_id, 'voided': recorded['voided']})
                elif not recorded.get('evidence_dvc_pointer'):
                    errors.append({'cohort_id': shard['cohort_id'], 'kill_id': kill_id, 'error': 'evidence still not archived',
                                   'retry': f'pixi run python -m tools.raid_program.scoreboard archive-pending --scenario {scenario}'})
                continue
            if run.get('worldserver_sha256') != build['worldserver_sha256']:
                errors.append({'cohort_id': shard['cohort_id'], 'error': 'run binary differs from the round build'})
                continue
            scenario = unit['raid_target']['scenario']
            kill_id = f"{label}-{run.get('run_id') or run['sha256'][:12]}-{shard['cohort_id']}"
            known = {row['kill_id']: row for row in load_records(root, scenario)}
            if kill_id in known:  # recorded earlier (its archive may be pending): adopt, never record twice
                record = known[kill_id]
            elif not run_dir.is_dir():
                errors.append({'cohort_id': shard['cohort_id'], 'error': f'run dir missing: {run_dir}'})
                continue
            else:
                try:
                    with runs.stdout_to_stderr():
                        record = record_then_archive(root, scenario=scenario, label=label, kill=_kill(run_dir, kill_id),
                                                     worldserver_sha256=build['worldserver_sha256'],
                                                     source_commit=build['source_commit'], archive=archive)
                except (Exception, SystemExit) as failure:  # noqa: BLE001 - one shard's failure must not hide the others
                    errors.append({'cohort_id': shard['cohort_id'], 'error': f'{type(failure).__name__}: {failure}'})
                    continue
            if record.get('voided'):
                voided.append({'cohort_id': shard['cohort_id'], 'kill_id': kill_id, 'voided': record['voided']})
            elif not record.get('evidence_dvc_pointer'):
                errors.append({'cohort_id': shard['cohort_id'], 'kill_id': kill_id,
                               'error': 'evidence not archived: ' + str(record.get('archive_error')),
                               'retry': f'pixi run python -m tools.raid_program.scoreboard archive-pending --scenario {scenario}'})
            added.append({'run_sha256': run['sha256'], 'cohort_id': shard['cohort_id'], 'boss_key': unit['boss_key'],
                          'scenario': scenario, 'kill_id': kill_id, 'outcome': record.get('outcome'),
                          'evidence_dvc_pointer': record.get('evidence_dvc_pointer'), 'utc': utc_now()})
            done[key] = added[-1]
        if not (run.get('evidence') or {}).get('pointer'):
            batch = runs.batch_sources(run)
            if batch:
                with runs.stdout_to_stderr():
                    pointer, error = archive(root, f'{slug}_runs', f"r{program['round']:02d}-b{run['batch']}-{run.get('run_id')}",
                                             batch, set())
                batch_evidence[run['sha256']] = {'pointer': pointer, 'error': error, 'paths': [str(p) for p in batch]}
                if error:
                    errors.append({'run': run['sha256'], 'error': 'batch evidence archive: ' + error})

    def reducer(state: dict) -> dict:
        target = rounds.active(state)
        rounds.require(target, 'run')
        current = rounds.current_round(target)
        current['label'] = label
        current.setdefault('ingested', []).extend(added)
        current.setdefault('shard_evidence', []).extend(row for row in shard_evidence if row['evidence_dvc_pointer'])
        for run in current['runs']:
            if run.get('sha256') in batch_evidence:
                run['evidence'] = batch_evidence[run['sha256']]
        store.history(target, 'ingest', round=target['round'], label=label, kills=len(added), errors=len(errors))
        return state
    store.update(root, reducer)
    return {'label': label, 'ingested': added, 'shard_evidence': shard_evidence, 'batch_evidence': batch_evidence,
            'errors': errors, 'voided': voided,
            'next_action': ('Resolve every error, then run program ingest again with the same label '
                            '(recorded kills are adopted, not duplicated; archive failures retry with '
                            'scoreboard archive-pending)') if errors else 'Continue with the next batch run or program assess.'}
