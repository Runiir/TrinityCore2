"""Containment must fail closed and preserve command failure outcomes."""
import subprocess
import sys
import types

import pytest

from tools.client_compatibility import bounded_run as budget
from tools.client_compatibility import checkpoint_interactions as checkpoint


def test_missing_scope_launcher_cannot_run_unbounded(monkeypatch):
    monkeypatch.setattr(budget.shutil, 'which', lambda _: None)
    monkeypatch.setattr(budget.subprocess, 'run', lambda *a, **k: pytest.fail('executed without containment'))
    with pytest.raises(RuntimeError, match='unbounded execution is refused'):
        budget.run(['pixi', 'run', 'python', '-V'])


def test_memory_reserve_rejects_before_launch(monkeypatch):
    monkeypatch.setattr(budget, 'available_mib', lambda: 6143)
    monkeypatch.setattr(budget.subprocess, 'run', lambda *a, **k: pytest.fail('launched without reserve'))
    with pytest.raises(RuntimeError, match='4 GiB available reserve'):
        budget.run(['true'])


@pytest.mark.parametrize('code,expected', [(0, 0), (1, 1), (137, 137), (-9, 137)])
def test_failure_status_is_not_reported_as_success(monkeypatch, code, expected):
    monkeypatch.setattr(budget, 'available_mib', lambda: 8192)
    monkeypatch.setattr(budget.subprocess, 'run', lambda args, **kw: subprocess.CompletedProcess(args, code))
    assert budget.run(['true']) == expected


def test_metric_logger_disables_repository_experiment_snapshot(monkeypatch):
    seen = []
    monkeypatch.setitem(sys.modules, 'dvclive', types.SimpleNamespace(Live=lambda **kw: seen.append(kw)))
    checkpoint.tracking_live(dir='/tmp/bounded-metrics', dvcyaml=False, report=None)
    assert seen[0]['save_dvc_exp'] is False
    with pytest.raises(ValueError, match='automatic DVC experiment saving'):
        checkpoint.tracking_live(save_dvc_exp=True)
    assert len(seen) == 1
