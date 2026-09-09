"""Status counts are scalar; calibration/diagnosis bot arrays are not status."""
import io
import json
import time
from types import SimpleNamespace

import pytest
from tools.bot_ml import run_live_bot_validation as live


def output(*rows):
    return '\n'.join(json.dumps(row) for row in rows)


NOISE = [
    {'action': 'botauto_calibrate_status', 'active': True, 'bots': [{'guid': 1306}]},
    {'action': 'botauto_diagnose', 'bots': [{'guid': 1306}]},
    {'bots': [{'guid': 1306}]},
]


@pytest.mark.parametrize('row', [
    {'action': 'botauto_status', 'active': True, 'bots': 5, 'target_bots': 5},
    {'action': 'botexp_status', 'active_bots': '5', 'target_bots': '5'},
    {'active': 1, 'active_bots': 5, 'target_bots': 5},
    {'activeBots': 5, 'targetBots': 5},
    {'bots': 5.0, 'targetBots': '5'},
])
def test_supported_status_scalar_formats_survive_mixed_list_payloads(row):
    parsed = live.bot_status_snapshot(output(*NOISE, row, *NOISE))
    assert parsed == {'active': True, 'active_bots': 5, 'target_bots': 5, 'payload': row}
    assert live.bot_status_ready(output(row, *NOISE))


def test_explicit_zero_beats_nonzero_count_aliases():
    row = {'action': 'botauto_status', 'active': True, 'active_bots': 0,
           'bots': 5, 'activeBots': 6, 'target_bots': 0, 'targetBots': 7}
    parsed = live.bot_status_snapshot(output(row))
    assert parsed['active_bots'] == parsed['target_bots'] == 0
    assert live.bot_status_state(output(row)) is False
    row['active_bots'] = 1
    assert live.bot_status_state(output(row)) is True  # target zero stays zero
    row['active'] = False
    assert live.bot_status_state(output(row)) is False


@pytest.mark.parametrize('value', [None, [], {}, True, -1, 1.2, 'bad', '1.5'])
@pytest.mark.parametrize('field', ['active_bots', 'target_bots'])
def test_malformed_status_counts_never_coerce_or_fall_back(value, field):
    row = {'action': 'botauto_status', 'active': True, 'active_bots': 1,
           'target_bots': 1, 'bots': 1, 'activeBots': 1, 'targetBots': 1, field: value}
    assert live.bot_status_snapshot(output(row)) is None


@pytest.mark.parametrize('row', NOISE + [
    {'action': 'botauto_calibrate_status', 'active': True, 'bots': 1},
    {'action': 'botauto_status', 'active': 'false', 'bots': 1},
    {'action': 'botauto_status'},
])
def test_nonstatus_or_mere_presence_cannot_establish_readiness(row):
    assert not live.bot_status_ready(output(row))


def test_actual_startup_wait_handles_inactive_then_active_with_list_noise(monkeypatch):
    inactive = {'action': 'botauto_status', 'active': False, 'bots': 0, 'target_bots': 1}
    active = {**inactive, 'active': True, 'bots': 1}
    replies = iter([output(*NOISE, inactive, *NOISE), output(*NOISE, active, *NOISE)])
    stdin = io.StringIO()
    process = SimpleNamespace(stdin=stdin, poll=lambda: None)
    sleeps = []
    monkeypatch.setattr(live, 'read_until_console_prompt', lambda *args: next(replies))
    monkeypatch.setattr(live.time, 'sleep', sleeps.append)
    captured = live.wait_for_bot_status_ready(process, time.monotonic() + 30)
    assert stdin.getvalue() == '.botauto status\n' * 2
    assert sleeps == [2.0]
    assert live.bot_status_ready(captured)


def test_actual_poll_waits_for_complete_count_and_preserves_inactive():
    partial = {'action': 'botauto_status', 'active': True, 'bots': 1, 'target_bots': 2}
    ready = {**partial, 'bots': 2}
    replies = iter([output(partial, *NOISE), output(*NOISE, ready, *NOISE)])
    calls = []
    def execute(command, _remaining):
        calls.append(command)
        return next(replies), 0, False
    captured, status, code, timed_out = live.poll_bot_status(execute, time.monotonic() + 30,
                                                          poll_sec=0, sleep=lambda _: None)
    assert len(calls) == 2 and code == 0 and not timed_out
    assert status['active_bots'] == 2 and live.bot_status_ready(captured)
    inactive = {**ready, 'active': False, 'active_bots': 0}
    _, status, code, timed_out = live.poll_bot_status(
        lambda *_: (output(inactive, *NOISE), 0, False), time.monotonic() + 30)
    assert status['active'] is False and status['active_bots'] == 0
    assert code == 0 and not timed_out


@pytest.mark.parametrize('action', ['botauto_status', 'botexp_status'])
@pytest.mark.parametrize('bad', [{'bots': []}, {'active_bots': 'bad'},
                                  {'target_bots': {}}, {'active': 'false'}, {'active': None}])
def test_latest_named_malformed_status_invalidates_earlier_ready_snapshot(action, bad):
    ready = {'action': 'botauto_status', 'active': True, 'bots': 1, 'target_bots': 1}
    latest = {**ready, 'action': action, **bad}
    mixed = output(ready, *NOISE, latest, *NOISE)
    assert live.bot_status_snapshot(mixed) is None
    assert live.bot_status_state(mixed) is None
    assert not live.bot_status_ready(mixed)


def test_actual_startup_wait_does_not_reuse_ready_before_malformed_latest(monkeypatch):
    ready = {'action': 'botauto_status', 'active': True, 'bots': 1, 'target_bots': 1}
    malformed = {**ready, 'bots': []}
    mixed = output(ready, malformed, *NOISE)
    stdin = io.StringIO()
    process = SimpleNamespace(stdin=stdin, poll=lambda: None)
    monkeypatch.setattr(live, 'read_until_console_prompt', lambda *args: mixed)
    monkeypatch.setattr(live.time, 'sleep', lambda _: pytest.fail('unknown status must end this wait'))
    captured = live.wait_for_bot_status_ready(process, time.monotonic() + 30)
    assert stdin.getvalue() == '.botauto status\n'
    assert live.bot_status_state(captured) is None


@pytest.mark.parametrize('action', ['botauto_status', 'botexp_status'])
@pytest.mark.parametrize('field,aliases', [
    ('active_bots', {'bots': 5, 'activeBots': 5}),
    ('target_bots', {'targetBots': 5}),
])
def test_present_null_count_rejects_conflicting_alias_and_older_readiness(action, field, aliases):
    ready = {'action': action, 'active': True, 'active_bots': 5, 'target_bots': 5}
    latest = {**ready, **aliases, field: None}
    assert live.bot_status_snapshot(output(latest)) is None
    mixed = output(ready, latest, *NOISE)
    assert live.bot_status_snapshot(mixed) is None
    assert live.bot_status_state(mixed) is None
