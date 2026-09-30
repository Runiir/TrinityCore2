"""``program run-batches``: the whole run loop of a raid-program round in one command.

For each batch it:

1. waits (bounded) until no ``worldserver*`` process runs. A stray pytest fake
   (its executable under ``/tmp/pytest-of-*`` or ``~/.cache``) is waited out; a
   real worldserver refuses the run at once (never stop a live play server);
2. checks the run root's writable headroom (``/tmp`` is a tmpfs with a quota);
3. runs ``shard_coordinator --plan <round plan> --output-dir /tmp/<label>-bN-<utc>
   --gdb-backtrace`` (its log is ``<output-dir>.coordinator.log``); on every exit
   path, Ctrl-C and SIGTERM included, its process group and any worldserver or
   gdb of the batch are reaped and verified gone (raid_program_batch_process);
4. records ``shard_run.json`` (``program run``), or the batch as failed when there
   is none (``program run --failed-batch``);
5. ingests the round's kills (``program ingest``).

Every planned batch runs once (assess needs a run per batch); then the batches
holding a boss with a raid target that is short of its ``kills_per_measurement``
counted kills (the verdict's own count) repeat. It stops when every target boss
has its kills, after ``--max-batches`` batch runs (default 5), when a batch adds
no counted kill for any short boss, when a batch produced no shard_run.json, on
an ingest error, or when the batch's processes could not be shown gone (the
batch is then recorded as failed, ``cleanup_unverified``).

Signals: the whole loop runs under a signal guard, so SIGINT, SIGTERM and SIGHUP
are recorded, never acted on mid-step. A signal during a batch ends it with a
verified cleanup (or ``cleanup_unverified``); any other signal stops the loop at
the next step boundary (before a launch, while waiting out fakes, after the
record, after the ingest). No batch is launched after a signal. It never
commits: it lists the files to commit. The coordinator, ingest, process
inventory, headroom and kill counter are injectable, so tests never launch a
worldserver.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from tools.raid_program import raid_program_ingest as ingests
from tools.raid_program import raid_program_rounds as rounds
from tools.raid_program import raid_program_runs as runs
from tools.raid_program import raid_program_state as store
from tools.raid_program.development_graph import GraphError
from tools.raid_program.raid_program_batch_process import (  # noqa: F401 - run_coordinator is patched by name
    BatchInterrupted, CleanupUnverified, describe, run_coordinator, signal_guard)

RUN_ROOT = Path('/tmp')
MAX_BATCHES = 5
WAIT_SECONDS = 600
POLL_SECONDS = 10
BATCH_TIMEOUT_SECONDS = 11400  # emergency cap only; the shard watchdogs end a run long before it
COMMIT_PATHS = ('artifacts/cata_raid_program',)
CLEAN_STOPS = ('targets_met', 'no_target_bosses')
Coordinator = Callable[[Path, str, Path, Path, int], int]


def _log(message: str) -> None:
    print('run-batches: ' + message, file=sys.stderr, flush=True)


def fake_root(path: str | None, home: Path | None = None) -> bool:
    """A pytest fake's executable lives under /tmp/pytest-of-* or ~/.cache."""
    if not path:
        return False
    candidate = Path(path.strip().removesuffix(' (deleted)'))
    if not candidate.is_absolute():
        return False
    parts = candidate.parts
    cache = (home or Path.home()) / '.cache'
    return (len(parts) > 2 and parts[1] == 'tmp' and parts[2].startswith('pytest-of-')) or candidate.is_relative_to(cache)


def _process_paths(proc: Path, pid: int) -> list[str]:
    """The worldserver-named paths of one process: its executable and argv entries."""
    from tools.raid_program.raid_shard_preflight import is_worldserver_name
    paths = []
    try:
        paths.append(os.readlink(proc / str(pid) / 'exe'))
    except OSError:
        pass
    try:
        paths += [arg.decode(errors='replace') for arg in (proc / str(pid) / 'cmdline').read_bytes().split(b'\0') if arg]
    except OSError:
        pass
    return [path for path in paths if is_worldserver_name(path)]


def worldserver_inventory(proc: Path = Path('/proc'), home: Path | None = None) -> list[dict]:
    """Every running worldserver, classified: ``fake`` only when every worldserver path is a pytest fake's."""
    from tools.raid_program.raid_shard_preflight import worldserver_processes
    found = worldserver_processes(proc)
    if found['returncode'] is None:
        raise GraphError('the worldserver process inventory is incomplete (' + str(found['error'])
                         + '); cannot prove no worldserver runs')
    rows = []
    for pid in found['pids']:
        paths = _process_paths(proc, pid)
        rows.append({'pid': pid, 'paths': paths, 'fake': bool(paths) and all(fake_root(path, home) for path in paths)})
    return rows


def wait_for_no_worldserver(inventory: Callable[[], list[dict]] | None = None, *, wait_seconds: int = WAIT_SECONDS,
                            poll_seconds: int = POLL_SECONDS, sleep: Callable[[float], None] = time.sleep,
                            clock: Callable[[], float] = time.monotonic) -> dict:
    """Return once no worldserver runs; wait out stray pytest fakes (bounded); refuse a real one at once."""
    look = inventory or worldserver_inventory
    start = clock()
    seen: list[dict] = []
    while True:
        rows = look()
        real = [row for row in rows if not row['fake']]
        if real:
            raise GraphError('a real worldserver is running (' + ', '.join(
                f"pid {row['pid']} {row['paths'][:1] or 'unknown executable'}" for row in real)
                + '); a raid run needs none. Never stop a live play server without asking the user; stop your own '
                  'leftover run only after checking what it is, then run program run-batches again')
        if not rows:
            return {'waited_seconds': round(clock() - start, 1), 'stray_fakes_seen': seen}
        seen = rows
        if clock() - start >= wait_seconds:
            raise GraphError(f'stray pytest fake worldserver(s) still run after {wait_seconds} s ('
                             + ', '.join(f"pid {row['pid']} {row['paths'][0]}" for row in rows)
                             + '); they block provisioning. They are test leftovers under /tmp/pytest-of-* or '
                               '~/.cache: kill them, then run program run-batches again')
        _log(f"waiting for {len(rows)} stray pytest fake worldserver(s) to exit: {[row['pid'] for row in rows]}")
        sleep(poll_seconds)


def check_headroom(run_root: Path = RUN_ROOT, reader: Callable[[Path], dict] | None = None,
                   minimum: int | None = None) -> dict:
    from tools.raid_program.run_root_headroom import DEFAULT_MIN_HEADROOM_BYTES, safe_headroom
    headroom = (reader or safe_headroom)(run_root)
    needed = DEFAULT_MIN_HEADROOM_BYTES if minimum is None else minimum
    available = headroom.get('headroom_bytes')
    if available is None or available < needed:
        raise GraphError(f'run root {run_root} has {available} writable bytes (need {needed}; filesystem '
                         f"{headroom.get('filesystem_available_bytes')}, quota {headroom.get('quota_available_bytes')}). "
                         'Archive old /tmp run directories with DVC and remove them, then run program run-batches again')
    return headroom


def verdict_count(root: Path, scenario: str, label: str) -> tuple[int, int]:
    """(counted kills, kills_per_measurement) of a label, as the scoreboard verdict counts them."""
    try:
        from tools.raid_program.scoreboard_verdict import evaluate_target
        verdict = evaluate_target(root, scenario, label)
        return int(verdict['kills']), int(verdict['kills_per_measurement'])
    except (SystemExit, ValueError, KeyError, OSError, TypeError):
        from tools.raid_program.scoreboard_core import counted_kills, label_kills, load_records, load_target
        needed = int(load_target(root, scenario)['kills_per_measurement'])
        return len(counted_kills(label_kills(load_records(root, scenario), label))), needed


def target_units(root: Path, program: dict, plans: list[dict]) -> dict:
    """Bosses with a raid target in this round's plans: {boss: {scenario, cohort_id, batches}}."""
    targets = {}
    for unit in rounds.discover(root, program)['units']:
        batches = [plan['batch'] for plan in plans if unit['cohort_id'] in plan['cohorts']]
        if unit['raid_target']['present'] and batches:
            targets[unit['boss_key']] = {'scenario': unit['raid_target']['scenario'], 'cohort_id': unit['cohort_id'],
                                         'batches': batches}
    return targets


def count_kills(root: Path, targets: dict, label: str, counter=None) -> dict:
    count = counter or verdict_count
    result = {}
    for boss, row in targets.items():
        counted, needed = count(root, row['scenario'], label)
        result[boss] = {'counted': counted, 'needed': needed}
    return result


def kill_summary(root: Path, program: dict) -> str | None:
    """'boss n/m' per target boss of the current round's label (short ones with their exclusion reasons); None
    before any ingest. Read-only and cheap: resume shows it so the coordinator sees why run-batches continues."""
    holder = rounds.current_round(program)
    label = holder.get('label')
    if not label or not holder.get('run_plans'):
        return None
    targets = target_units(root, program, holder['run_plans'])
    kills = count_kills(root, targets, label)
    parts = []
    for boss, row in kills.items():
        text = f"{boss} {row['counted']}/{row['needed']}"
        if row['counted'] < row['needed']:
            try:
                from tools.raid_program.scoreboard_verdict import evaluate_target
                details = evaluate_target(root, targets[boss]['scenario'], label)['kills_detail']
                reasons = sorted({str(kill['exclusion_reason']) for kill in details if not kill['counted']})
                text += f" (excluded: {', '.join(reasons)})" if reasons else ''
            except (SystemExit, ValueError, KeyError, OSError, TypeError):
                pass
        parts.append(text)
    return ', '.join(parts)


def _next_plan(plans: list[dict], holder: dict, targets: dict, short: set[str]) -> tuple[dict | None, str | None]:
    recorded = {run['batch'] for run in holder['runs']}
    unrun = [plan for plan in plans if plan['batch'] not in recorded]
    if unrun:
        return unrun[0], None
    if not targets:
        return None, 'no_target_bosses'
    if not short:
        return None, 'targets_met'
    batch = min(number for boss in short for number in targets[boss]['batches'])
    return next(plan for plan in plans if plan['batch'] == batch), None


def _tail(path: Path, limit: int = 400) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')[-limit:].strip()
    except OSError:
        return ''


def changed_paths(root: Path, paths: tuple[str, ...] = COMMIT_PATHS) -> list[str]:
    completed = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=all', '--', *paths],
                               capture_output=True, text=True, check=False)
    return sorted(line[3:] for line in completed.stdout.splitlines() if len(line) > 3)


def _state_sha(root: Path) -> str:
    return store.state_sha256(store.load(root)[1])


def _preflight(root: Path, label: str, expected_sha256: str | None, max_batches: int) -> tuple[dict, list[dict]]:
    _, program, data = rounds.load_active(root)
    rounds.require(program, 'run')
    rounds.check_expected(data, expected_sha256)
    holder = rounds.current_round(program)
    if not holder.get('plans_written'):
        raise GraphError('write the run plans first: program run-plan --expect <state_sha256>')
    if not holder['run_plans']:
        raise GraphError('no shard is ready to run this round; close it with program assess --expect <state_sha256>')
    if not label:
        raise GraphError('program run-batches needs --label')
    if holder.get('label') and holder['label'] != label:
        raise GraphError(f"this round ingests under label {holder['label']}; use that label")
    if not (holder.get('build') or {}).get('worldserver_sha256'):
        raise GraphError('the round has no recorded build to run')
    if max_batches < 1:
        raise GraphError('--max-batches must be at least 1')
    return program, holder['run_plans']


def run_batches(root: Path, label: str, expected_sha256: str | None = None, max_batches: int = MAX_BATCHES, *,
                coordinator: Coordinator | None = None, ingest=None, inventory=None, headroom=None, counter=None,
                sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                stamp: Callable[[], str] | None = None, wait_seconds: int = WAIT_SECONDS,
                batch_timeout: int = BATCH_TIMEOUT_SECONDS) -> dict:
    """Run, record and ingest batches until the target bosses have their kills or a stop condition holds."""
    program, plans = _preflight(root, label, expected_sha256, max_batches)
    targets = target_units(root, program, plans)
    run = coordinator or run_coordinator
    do_ingest = ingest or ingests.ingest
    now = stamp or (lambda: time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    batches: list[dict] = []
    stop, error = None, None
    kills = count_kills(root, targets, label, counter)
    with signal_guard() as guard:  # from here every SIGINT/SIGTERM/SIGHUP stops the loop at the next step boundary

        def interrupted(where: str) -> str | None:
            return f"signal {', '.join(guard.signals)} {where}" if guard.signals else None

        def guarded_sleep(seconds: float) -> None:
            if guard.signals:
                raise BatchInterrupted(interrupted('while waiting for worldservers to exit'))
            sleep(seconds)
        for _ in range(max_batches):
            error = interrupted('before the next batch started')
            if error:
                stop = 'interrupted'
                break
            holder = rounds.current_round(rounds.active(store.load(root)[0]))
            short = {boss for boss, row in kills.items() if row['counted'] < row['needed']}
            plan, stop = _next_plan(plans, holder, targets, short)
            if plan is None:
                break
            row: dict = {'batch': plan['batch']}
            try:  # launch preconditions: refuse outright before the first batch, else stop and report what ran
                row['waited'] = wait_for_no_worldserver(inventory, wait_seconds=wait_seconds, sleep=guarded_sleep,
                                                        clock=clock)
                check_headroom(reader=headroom)
            except BatchInterrupted as interrupt:
                stop, error = 'interrupted', interrupt.reason
                break
            except GraphError as refusal:
                if not batches:
                    raise
                stop, error = 'refused', str(refusal)
                break
            try:
                output = RUN_ROOT / f"{label}-b{plan['batch']}-{now()}"
                log = output.with_name(output.name + '.coordinator.log')
                row |= {'output_dir': str(output), 'log': str(log)}
                _log(f"batch {plan['batch']}: shard_coordinator -> {output} (log {log})")
                try:
                    row['exit_status'] = code = run(root, plan['path'], output, log, batch_timeout)
                except CleanupUnverified as unverified:  # always wins over an interrupt: never claim a stop
                    reason = (f'batch processes not verified gone after shard_coordinator exited {unverified.code}'
                              + (f" (interrupted by {', '.join(unverified.signals)})" if unverified.signals else '')
                              + f': {describe(unverified.cleanup)} (log {log})')
                    runs.record_run(root, None, _state_sha(root), failed_batch=plan['batch'], reason=reason[:1000])
                    batches.append(row | {'exit_status': unverified.code, 'failed': reason[:1000],
                                          'cleanup': unverified.cleanup})
                    stop, error = 'cleanup_unverified', reason
                    break
                except BatchInterrupted as interrupt:  # its processes are shown gone; nothing is recorded or ingested
                    row |= {'interrupted': interrupt.reason, 'cleanup': interrupt.cleanup}
                    batches.append(row)
                    stop, error = 'interrupted', f"{interrupt.reason} during batch {plan['batch']}"
                    break
                summary = output / 'shard_run.json'
                if summary.is_file():
                    runs.record_run(root, summary, _state_sha(root))
                    row['shard_run'] = str(summary)
                else:
                    reason = f'shard_coordinator exited {code} without shard_run.json (log {log}): {_tail(log)}'
                    runs.record_run(root, None, _state_sha(root), failed_batch=plan['batch'], reason=reason[:1000])
                    row['failed'] = reason[:1000]
                error = interrupted(f"after batch {plan['batch']} was recorded; it is not ingested")
                if error:
                    batches.append(row | {'interrupted': error})
                    stop = 'interrupted'
                    break
                _log(f"batch {plan['batch']}: recorded; ingesting under {label}")
                ingested = do_ingest(root, label)
                row['ingest'] = {'kills': len(ingested.get('ingested') or []), 'errors': ingested.get('errors') or []}
            except (GraphError, OSError, subprocess.SubprocessError) as failure:
                stop, error = 'error', f'{type(failure).__name__}: {failure}'
                if 'exit_status' in row:  # the coordinator ran: keep what is known about this batch
                    batches.append(row | {'error': error})
                break
            after = count_kills(root, targets, label, counter)
            batch_short = sorted(boss for boss in short if plan['batch'] in targets[boss]['batches'])
            row['gained'] = {boss: after[boss]['counted'] - kills[boss]['counted'] for boss in batch_short}
            batches.append(row)
            kills = after
            error = interrupted(f"during batch {plan['batch']} (recorded and ingested)")
            if error:
                stop = 'interrupted'
                break
            if row['ingest']['errors']:
                stop = 'ingest_errors'
                break
            if row.get('failed'):
                stop = 'batch_failed'
                break
            if batch_short and not any(value > 0 for value in row['gained'].values()):
                stop = 'no_progress'
                break
        else:
            holder = rounds.current_round(rounds.active(store.load(root)[0]))
            short = {boss for boss, row in kills.items() if row['counted'] < row['needed']}
            stop = _next_plan(plans, holder, targets, short)[1] or 'max_batches'
        final = interrupted('before the loop ended')  # the last checkpoint: a recorded signal is never a success
        if final and stop not in ('interrupted', 'cleanup_unverified'):  # an unverified cleanup still wins
            stop, error = 'interrupted', final + (f' (loop outcome was {stop}' + (f': {error}' if error else '')
                                                  + ')' if stop else '')
    return _report(root, program, label, batches, stop, error, kills)


NEXT = {
    'targets_met': 'Every target boss has its counted kills.',
    'no_target_bosses': 'Every planned batch ran; no boss of this round has a raid target to count kills for.',
    'max_batches': ('--max-batches was reached with bosses still short: run program run-batches again to continue, or '
                    'assess now (the short bosses stay open).'),
    'no_progress': ('The last batch added no counted kill for a short boss (see batches[-1].gained and the verdict '
                    'reasons): read why (wipes, stalls, void or unmeasured kills) before running more; assess to close '
                    'the round, or fix an infrastructure cause and run program run-batches again.'),
    'batch_failed': ('The last batch produced no shard_run.json and is recorded as failed (see batches[-1].failed and its '
                     'log). An infrastructure cause (DB, headroom, crash): fix it and run program run-batches again; '
                     'otherwise assess.'),
    'ingest_errors': ('ingest reported errors (batches[-1].ingest.errors): resolve each (its retry command), run program '
                      'ingest --label L again, then run-batches or assess.'),
    'error': 'The loop stopped on an error (see error); fix its cause, then run program run-batches again.',
    'interrupted': ('A signal stopped the loop at a safe point (error says where). Every batch it started was stopped '
                    'and its processes were shown gone (batches[-1].cleanup). A batch interrupted while running is not '
                    'recorded and its /tmp output directory is kept: record it with program run --shard-run '
                    '<output_dir>/shard_run.json (or --failed-batch N --reason ...) and program ingest, or run program '
                    'run-batches again for a new batch. A batch recorded but not ingested needs program ingest --label '
                    'L.'),
    'cleanup_unverified': ('A process of the last batch could not be shown gone (see error: coordinator group members or '
                           'a worldserver/gdb naming its output directory). The batch is recorded as failed. Check '
                           'those pids yourself (ps -o pid,pgid,args -p <pids>); never touch a play server. Once they '
                           'are gone, run program run-batches again. Its output directory is kept; if it holds a '
                           'shard_run.json you may record it with program run --shard-run and ingest it.'),
    'refused': ('A later batch could not launch (see error: a worldserver is running or /tmp lacks headroom); the '
                'batches before it are recorded. Resolve the cause, then run program run-batches again.'),
}


def _report(root: Path, program: dict, label: str, batches: list[dict], stop: str, error: str | None,
            kills: dict) -> dict:
    files = changed_paths(root)
    name = f"{program['name']} {program['mode']} round {program['round']}"
    return {'schema': 'raid_program_run_batches_v1', 'label': label, 'stopped': stop, 'error': error,
            'batches': batches, 'kills': kills,
            'short': sorted(boss for boss, row in kills.items() if row['counted'] < row['needed']),
            'exit_status': 0 if stop in CLEAN_STOPS else 1,
            'files_to_commit': files,
            'commit': (f"git add -A {' '.join(COMMIT_PATHS)} && git commit -m '{name}: batch runs and ingest'"
                       if files else None),
            'next_action': NEXT[stop] + ' This command does not commit: commit the listed files, then '
                           f'program assess --label {label} --expect <state_sha256 from resume> and commit again.'}
