"""Round-4 coordinator fix 1 (diag_r3 Q1): a batch launches only on a quiet host, and the host is recorded."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.raid_program import host_load
from tools.raid_program import shard_coordinator as sc

from tests.test_raid_program_batches import (  # noqa: F401 - fixtures are used by name
    QUIET_HOST, Loop, program, quiet_host, ready, rounds, world)
from tests.test_shard_coordinator import FakeWorld, proof_plan

# The round-3 batch-1 host: 9.9 GB of review scratch in the /tmp tmpfs, swap full and active, load 11 on 12 CPUs.
R03_BATCH1 = {'memory_total_bytes': 31 << 30, 'memory_available_bytes': 5 << 30, 'swap_used_fraction': 0.99,
              'swap_io_pages_per_second': 106.0, 'load_1m': 11.2, 'cpu_count': 12, 'load_1m_per_cpu': 0.933,
              'tmpfs': {'path': '/tmp', 'ram_backed': True, 'used_bytes': 9_860_000_000}}


def test_the_round3_noisy_host_is_busy_for_every_reason_and_the_quiet_host_is_not():
    assert host_load.busy_reasons(R03_BATCH1) == [
        'tmpfs_ram_use', 'memory_available', 'swap_used', 'swap_activity', 'load_average']
    assert host_load.busy_reasons(QUIET_HOST) == []


def test_unreadable_values_fail_closed_and_a_disk_backed_run_root_is_not_ram():
    assert host_load.busy_reasons({}) == ['tmpfs_unreadable', 'memory_unreadable', 'swap_unreadable',
                                          'swap_activity_unmeasured', 'load_unreadable']
    disk = dict(QUIET_HOST, tmpfs={'path': '/srv', 'ram_backed': False, 'used_bytes': 1 << 40})
    assert host_load.busy_reasons(disk) == []


def test_snapshot_counts_tmpfs_swap_and_load_and_measures_swap_activity(tmp_path):
    mem = {'MemTotal': 32 << 30, 'MemAvailable': 20 << 30, 'Shmem': 1 << 30, 'SwapTotal': 8 << 30,
           'SwapFree': 2 << 30}
    counters = iter([{'pswpin': 100, 'pswpout': 200, 'pgmajfault': 5}, {'pswpin': 150, 'pswpout': 450, 'pgmajfault': 9}])
    clock = iter([1000.0, 1005.0])
    reading = dict(meminfo=lambda: mem, vmstat=lambda: next(counters), loadavg=lambda: (3.0, 2.0, 1.0),
                   cpus=lambda: 12, tmpfs=lambda path: {'path': str(path), 'ram_backed': True, 'used_bytes': 7},
                   clock=lambda: next(clock))
    first = host_load.snapshot(tmp_path, **reading)
    second = host_load.snapshot(tmp_path, previous=first, **reading)
    assert 'swap_io_pages_per_second' not in first
    assert second['swap_io_pages_per_second'] == 60.0 and second['major_faults_per_second'] == 0.8
    assert second['swap_used_fraction'] == 0.75 and second['load_1m_per_cpu'] == 0.25
    assert second['tmpfs']['ram_backed'] and second['shmem_bytes'] == 1 << 30


def test_real_tmp_mount_type_is_read(tmp_path):
    assert host_load._tmpfs(Path('/tmp'))['fs_type'] is not None
    assert host_load._mount_type(Path('/')) is not None


def test_a_busy_host_is_waited_out_then_launches():
    readings = [dict(R03_BATCH1), dict(QUIET_HOST)]
    logged, slept = [], []
    ticks = iter([0, 0, 30])
    row = host_load.wait_for_quiet_host(lambda: readings.pop(0), wait_seconds=600, poll_seconds=30,
                                        sleep=slept.append, clock=lambda: next(ticks), log=logged.append)
    assert row['gate']['passed'] and row['gate']['busy_samples'] == 1 and slept == [30]
    assert 'tmpfs_ram_use' in logged[0] and 'load_average' in logged[0]


def test_a_host_that_stays_busy_is_refused_with_a_typed_reason():
    ticks = iter([0, 0, 30, 60])
    with pytest.raises(host_load.HostBusyError, match='host_busy after 60') as refused:
        host_load.wait_for_quiet_host(lambda: dict(R03_BATCH1), wait_seconds=60, poll_seconds=30,
                                      sleep=lambda s: None, clock=lambda: next(ticks), log=lambda m: None)
    assert refused.value.reason == 'host_busy' and 'swap_activity' in refused.value.reasons
    assert refused.value.snapshot['gate']['passed'] is False


def test_run_batches_refuses_a_busy_host_before_launching(ready):
    root = ready['root']
    loop = Loop(root)
    ticks = iter(range(0, 10_000, 30))
    result = loop.run(root, host=lambda: dict(R03_BATCH1), host_wait_seconds=60, sleep=lambda s: None,
                      clock=lambda: next(ticks))
    assert result['stopped'] == 'host_busy' and result['exit_status'] == 1 and loop.calls == []
    assert result['batches'][0]['refused'] == 'host_busy'
    assert result['batches'][0]['host']['gate']['reasons'][:1] == ['tmpfs_ram_use']
    assert rounds.current_round(program(root))['runs'] == []


def test_run_batches_records_the_host_snapshot_in_the_batch_row(ready):
    root = ready['root']
    loop = Loop(root)
    result = loop.run(root, max_batches=1)
    assert len(loop.calls) == 1
    host = result['batches'][0]['host']
    assert host['gate']['passed'] and host['load_1m'] == 1.0 and host['tmpfs']['used_bytes'] == 1 << 30


def test_every_status_heartbeat_appends_a_host_snapshot(tmp_path):
    world = FakeWorld()
    spec = proof_plan().shards[0]
    world.cohorts[spec.cohort_id] = {"active": True, "attempt": 1, "instance": 7}
    transport = sc.ShardTransport(sc.SerializedConsole(world), spec, tmp_path)
    seen = []

    def fake_snapshot(path, previous=None):
        seen.append(previous)
        return {'schema': 'raid_host_load_v1', 'load_1m': 2.0 + len(seen), 'tmpfs': {'path': str(path)}}
    transport.host_snapshot = fake_snapshot
    transport(f".botauto status {spec.cohort_id}", 5)
    transport(f".botauto diagnose {spec.cohort_id} all", 5)
    transport(f".botauto status {spec.cohort_id}", 5)
    rows = [json.loads(line) for line in (tmp_path / "host_load.jsonl").read_text().splitlines()]
    assert [row['load_1m'] for row in rows] == [3.0, 4.0]
    assert rows[0]['cohort_id'] == spec.cohort_id and seen[0] is None and seen[1]['load_1m'] == 3.0
