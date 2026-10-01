"""Host-load gate of a raid-program batch, and the host snapshot the shard coordinator records.

Round 3 of Blackwing Descent 10N (diag_r3 Q1) ran the same code on the same plan
four times; the world-thread stall count followed the host, not the code
(139 / 101 / 10 / 38 stalls > 500 ms). The noisy batches ran with the RAM-backed
``/tmp`` tmpfs holding ~9.9 GB of stale review scratch, swap 98-100 % used with
active swap-out, and a 1-minute load of 10-14 on 12 CPUs. So a batch is only
launched on a quiet host:

* ``tmpfs``: ``/tmp`` is a tmpfs, so every byte in it is RAM (or swap). The
  headroom check (run_root_headroom) only asks whether the console log fits;
  this gate also caps what the tmpfs already holds, as a fraction of RAM;
* ``memory``: MemAvailable stays above a floor (the build policy's 8 GiB);
* ``swap``: swap used stays below a fraction of the swap size, and pages are
  not being swapped in or out right now (pswpin + pswpout per second);
* ``load``: the 1-minute load average per logical CPU stays below a bound.

The thresholds live here, next to the /tmp headroom constants, not in the frozen
build resource policy (experiments/configs/cata_raid_build_resource_policy_host8_v1.json):
that file's sha256 is bound into every build receipt, so changing it would void
the recorded round build. A busy host is waited out (bounded, each wait logged
with its reasons) and then refused with ``HostBusyError`` (reason ``host_busy``);
the gate never silently proceeds. Every reader is injectable for tests.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.raid_program.development_graph import GraphError

GIB = 1024 ** 3
# Thresholds (diag_r3 Q1: r02 quiet 4.9 GB tmpfs, swap 50 %, load 0.5-1.8;
# r03 noisy 9.9 GB tmpfs, swap 98-100 % with 106 pages/s swapped out, load 10-14).
MAX_TMPFS_USED_FRACTION_OF_RAM = 0.20      # ~6.3 GB on this 31 GB host
MIN_MEMORY_AVAILABLE_BYTES = 8 * GIB       # the build policy's minimum_memory_available_gib
MAX_SWAP_USED_FRACTION = 0.95
MAX_SWAP_IO_PAGES_PER_SECOND = 50.0        # pswpin + pswpout
MAX_LOAD_1M_PER_CPU = 0.5                  # 6.0 on 12 logical CPUs
SAMPLE_SECONDS = 5.0                       # swap-activity window of one gate sample
WAIT_SECONDS = 900                         # a busy host is waited out this long, then refused
POLL_SECONDS = 30

THRESHOLDS = {
    'max_tmpfs_used_fraction_of_ram': MAX_TMPFS_USED_FRACTION_OF_RAM,
    'min_memory_available_bytes': MIN_MEMORY_AVAILABLE_BYTES,
    'max_swap_used_fraction': MAX_SWAP_USED_FRACTION,
    'max_swap_io_pages_per_second': MAX_SWAP_IO_PAGES_PER_SECOND,
    'max_load_1m_per_cpu': MAX_LOAD_1M_PER_CPU,
}


class HostBusyError(GraphError):
    """The host stayed busy past the bounded wait: the batch is refused (typed reason ``host_busy``)."""

    reason = 'host_busy'

    def __init__(self, message: str, reasons: list[str], snapshot: Mapping[str, Any]):
        super().__init__(message)
        self.reasons, self.snapshot = list(reasons), dict(snapshot)


def _meminfo(path: Path = Path('/proc/meminfo')) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        name, _, raw = line.partition(':')
        fields = raw.split()
        if fields and fields[0].isdigit():
            result[name] = int(fields[0]) * (1024 if fields[1:2] == ['kB'] else 1)
    return result


def _vmstat(path: Path = Path('/proc/vmstat')) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        name, _, value = line.partition(' ')
        if value.strip().isdigit():
            result[name] = int(value)
    return result


def _mount_type(path: Path, mounts: Path = Path('/proc/mounts')) -> str | None:
    """The filesystem type of the longest mount point containing path."""
    target = str(Path(path).resolve())
    best, kind = '', None
    for line in mounts.read_text(encoding='utf-8').splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        point = fields[1].replace('\\040', ' ')
        inside = target == point or target.startswith(point.rstrip('/') + '/')
        if inside and len(point) >= len(best):
            best, kind = point, fields[2]
    return kind


def _tmpfs(path: Path) -> dict[str, Any]:
    kind = _mount_type(path)
    stats = os.statvfs(path)
    return {'path': str(path), 'fs_type': kind, 'ram_backed': kind == 'tmpfs',
            'used_bytes': (int(stats.f_blocks) - int(stats.f_bfree)) * int(stats.f_frsize),
            'size_bytes': int(stats.f_blocks) * int(stats.f_frsize)}


def snapshot(run_root: Path = Path('/tmp'), *, previous: Mapping[str, Any] | None = None,
             meminfo: Callable[[], dict[str, int]] = _meminfo, vmstat: Callable[[], dict[str, int]] = _vmstat,
             loadavg: Callable[[], tuple[float, float, float]] = os.getloadavg,
             cpus: Callable[[], int | None] = os.cpu_count, tmpfs: Callable[[Path], dict] = _tmpfs,
             clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """One host reading. Swap activity is the page rate since ``previous`` (None without one). Never raises."""
    row: dict[str, Any] = {'schema': 'raid_host_load_v1', 'at_unix': round(clock(), 3)}
    try:
        memory = meminfo()
        swap_total = int(memory.get('SwapTotal', 0))
        swap_used = swap_total - int(memory.get('SwapFree', 0))
        row |= {'memory_total_bytes': int(memory['MemTotal']), 'memory_available_bytes': int(memory['MemAvailable']),
                'shmem_bytes': int(memory.get('Shmem', 0)), 'swap_total_bytes': swap_total,
                'swap_used_bytes': swap_used,
                'swap_used_fraction': round(swap_used / swap_total, 4) if swap_total else 0.0}
    except (OSError, KeyError, ValueError) as error:
        row['memory_error'] = f'{type(error).__name__}: {error}'
    try:
        counters = vmstat()
        row['vmstat'] = {name: int(counters.get(name, 0)) for name in ('pswpin', 'pswpout', 'pgmajfault')}
        before = (previous or {}).get('vmstat')
        elapsed = row['at_unix'] - float((previous or {}).get('at_unix') or 0)
        if isinstance(before, Mapping) and elapsed > 0:
            pages = sum(row['vmstat'][name] - int(before.get(name, 0)) for name in ('pswpin', 'pswpout'))
            row['swap_io_pages_per_second'] = round(max(0, pages) / elapsed, 2)
            row['major_faults_per_second'] = round(
                max(0, row['vmstat']['pgmajfault'] - int(before.get('pgmajfault', 0))) / elapsed, 2)
    except (OSError, ValueError) as error:
        row['vmstat_error'] = f'{type(error).__name__}: {error}'
    try:
        load1, load5, load15 = loadavg()
        count = int(cpus() or 0)
        row |= {'load_1m': round(load1, 2), 'load_5m': round(load5, 2), 'load_15m': round(load15, 2),
                'cpu_count': count, 'load_1m_per_cpu': round(load1 / count, 3) if count else None}
    except (OSError, ValueError, TypeError) as error:
        row['load_error'] = f'{type(error).__name__}: {error}'
    try:
        row['tmpfs'] = tmpfs(Path(run_root))
    except OSError as error:
        row['tmpfs'] = {'path': str(run_root), 'error': f'{type(error).__name__}: {error}'}
    return row


def busy_reasons(row: Mapping[str, Any], thresholds: Mapping[str, float] = THRESHOLDS) -> list[str]:
    """Why the host is too busy for a batch; an unreadable value is a reason (fail closed)."""
    reasons = []
    total = row.get('memory_total_bytes')
    tmpfs = row.get('tmpfs') or {}
    if 'error' in tmpfs or tmpfs.get('used_bytes') is None:
        reasons.append('tmpfs_unreadable')
    elif tmpfs.get('ram_backed') and (not total or tmpfs['used_bytes']
                                      > thresholds['max_tmpfs_used_fraction_of_ram'] * total):
        reasons.append('tmpfs_ram_use')
    if row.get('memory_available_bytes') is None:
        reasons.append('memory_unreadable')
    elif row['memory_available_bytes'] < thresholds['min_memory_available_bytes']:
        reasons.append('memory_available')
    if row.get('swap_used_fraction') is None:
        reasons.append('swap_unreadable')
    elif row['swap_used_fraction'] > thresholds['max_swap_used_fraction']:
        reasons.append('swap_used')
    if row.get('swap_io_pages_per_second') is None:
        reasons.append('swap_activity_unmeasured')
    elif row['swap_io_pages_per_second'] > thresholds['max_swap_io_pages_per_second']:
        reasons.append('swap_activity')
    if row.get('load_1m_per_cpu') is None:
        reasons.append('load_unreadable')
    elif row['load_1m_per_cpu'] > thresholds['max_load_1m_per_cpu']:
        reasons.append('load_average')
    return reasons


def sample(run_root: Path = Path('/tmp'), *, sample_seconds: float = SAMPLE_SECONDS,
           sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """A gate reading: two snapshots ``sample_seconds`` apart, so swap activity is measured."""
    first = snapshot(run_root)
    sleep(sample_seconds)
    return snapshot(run_root, previous=first)


def _describe(row: Mapping[str, Any], reasons: list[str]) -> str:
    tmpfs = row.get('tmpfs') or {}
    return (f"{', '.join(reasons)} (load_1m {row.get('load_1m')} on {row.get('cpu_count')} CPUs, swap used "
            f"{row.get('swap_used_fraction')}, swap io {row.get('swap_io_pages_per_second')} pages/s, "
            f"MemAvailable {row.get('memory_available_bytes')}, tmpfs {tmpfs.get('path')} used "
            f"{tmpfs.get('used_bytes')} bytes)")


def wait_for_quiet_host(sampler: Callable[[], dict[str, Any]] | None = None, *,
                        thresholds: Mapping[str, float] = THRESHOLDS, wait_seconds: float = WAIT_SECONDS,
                        poll_seconds: float = POLL_SECONDS, sleep: Callable[[float], None] = time.sleep,
                        clock: Callable[[], float] = time.monotonic,
                        log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Return the quiet host's snapshot (with ``gate``); wait out a busy host (bounded), then HostBusyError."""
    read = sampler or sample
    say = log or (lambda message: print('host-load: ' + message, file=sys.stderr, flush=True))
    start = clock()
    waits = 0
    while True:
        row = read()
        reasons = busy_reasons(row, thresholds)
        elapsed = clock() - start
        waited = round(elapsed, 1)
        if not reasons:
            return row | {'gate': {'passed': True, 'waited_seconds': waited, 'busy_samples': waits,
                                   'thresholds': dict(thresholds)}}
        if elapsed >= wait_seconds:
            gated = row | {'gate': {'passed': False, 'reason': HostBusyError.reason, 'reasons': reasons,
                                    'waited_seconds': waited, 'busy_samples': waits + 1,
                                    'thresholds': dict(thresholds)}}
            raise HostBusyError(f'host_busy after {waited} s: {_describe(row, reasons)}. Free the /tmp tmpfs '
                                '(archive old run directories with DVC and remove them), let other heavy work '
                                'finish, then run program run-batches again', reasons, gated)
        waits += 1
        say(f'host busy, waiting {poll_seconds} s (waited {waited} of {wait_seconds} s): {_describe(row, reasons)}')
        sleep(poll_seconds)
