import json
import sys
import types

import pytest

from tools.raid_program import jev_outcomes

SCENARIO = 'fixture_10n_fixture'


@pytest.fixture
def scoreboard(monkeypatch):
    """Stand-in for scoreboard.compare_labels(root, scenario, new_label, old_label)."""
    calls = []
    comparisons = {('batch2', 'batch1'): {'party': {'delta': 812.5, 'threshold': 300.0, 'verdict': 'improved'},
                                         'actors': {'30006': {'delta': 403.0, 'threshold': 250.0, 'verdict': 'improved'},
                                                    '30010': {'delta': -50.0, 'threshold': 200.0, 'verdict': 'within_noise'}}},
                   ('batch3', 'batch2'): {'party': {'delta': -100.0, 'threshold': 300.0, 'verdict': 'within_noise'},
                                         'actors': {}}}
    def compare_labels(root, scenario, new_label, old_label):
        calls.append((scenario, new_label, old_label))
        return comparisons[(new_label, old_label)]
    module = types.ModuleType('tools.raid_program.scoreboard')
    module.compare_labels = compare_labels
    monkeypatch.setitem(sys.modules, 'tools.raid_program.scoreboard', module)
    return calls


def record(**changes):
    return {'unit': 'u1', 'scenario': SCENARIO, 'candidates': ['fire_combustion_gap', 'elemental_cadence_gap'],
            'jev_pick': 'fire_combustion_gap', 'laya_pick': 'elemental_cadence_gap',
            'chosen': 'fire_combustion_gap', 'label_before': 'batch1', 'label_after': 'batch2'} | changes


def test_deltas_and_noise_come_from_the_scoreboard(tmp_path, scoreboard):
    row = jev_outcomes.append(tmp_path, record())
    assert scoreboard == [(SCENARIO, 'batch2', 'batch1')]
    assert (row['party_delta'], row['party_noise']) == (812.5, 'improved')
    assert row['actor_delta'] == {'30006': 403.0, '30010': -50.0}
    assert row['actor_noise'] == {'30006': 'improved', '30010': 'within_noise'}
    jev_outcomes.append(tmp_path, record(chosen='elemental_cadence_gap', label_before='batch2', label_after='batch3', laya_pick=None))
    rows = [json.loads(line) for line in (tmp_path / jev_outcomes.PATH).read_text().splitlines()]
    assert [r['laya_pick'] for r in rows] == ['elemental_cadence_gap', None] and all('recorded_at' in r for r in rows)
    result = jev_outcomes.summary(tmp_path)
    assert result['jev']['followed'] == {'n': 1, 'mean_party_delta': 812.5, 'party_improved': 1, 'party_regressed': 0}
    assert result['jev']['overridden'] == {'n': 1, 'mean_party_delta': -100.0, 'party_improved': 0, 'party_regressed': 0}
    assert result['laya'] == {'n': 1, 'followed': {'n': 0, 'mean_party_delta': None, 'party_improved': 0, 'party_regressed': 0},
                              'overridden': {'n': 1, 'mean_party_delta': 812.5, 'party_improved': 1, 'party_regressed': 0}}
    assert result['jev_laya_agreement'] == {'n': 1, 'agree': 0}


@pytest.mark.parametrize('changes,match', [
    ({'candidates': ['only_one']}, 'two distinct'),
    ({'candidates': ['a', 'a']}, 'two distinct'),
    ({'jev_pick': 'third_gap'}, 'null or one of the candidates'),
    ({'laya_pick': 'third_gap'}, 'null or one of the candidates'),
    ({'jev_pick': None, 'laya_pick': None}, 'at least one model pick'),
    ({'chosen': 'third_gap'}, 'chosen'),
    ({'label_after': 'batch1'}, 'must differ'),
    ({'label_after': ''}, 'label_after'),
    ({'party_delta': 5.0}, 'exactly'),  # deltas are measured, never typed in
])
def test_incomplete_or_unsanctioned_records_are_rejected(tmp_path, scoreboard, changes, match):
    with pytest.raises(ValueError, match=match):
        jev_outcomes.append(tmp_path, record(**changes))
    assert not (tmp_path / jev_outcomes.PATH).exists()


def test_labels_without_kills_record_nothing(tmp_path, monkeypatch):
    module = types.ModuleType('tools.raid_program.scoreboard')
    module.compare_labels = lambda *args: {'party': {'delta': None, 'verdict': 'insufficient_kills'}, 'actors': {}}
    monkeypatch.setitem(sys.modules, 'tools.raid_program.scoreboard', module)
    with pytest.raises(ValueError, match='no party delta'):
        jev_outcomes.append(tmp_path, record())
    assert not (tmp_path / jev_outcomes.PATH).exists()


def test_cli_append_without_laya(tmp_path, scoreboard, capsys):
    assert jev_outcomes.main(['--root', str(tmp_path), 'append', '--unit', 'u1', '--scenario', SCENARIO,
                              '--candidate', 'a', '--candidate', 'b', '--jev-pick', 'a', '--chosen', 'b',
                              '--label-before', 'batch1', '--label-after', 'batch2']) == 0
    row = json.loads(capsys.readouterr().out)
    assert row['laya_pick'] is None and row['party_noise'] == 'improved'
    assert jev_outcomes.main(['--root', str(tmp_path), 'summary']) == 0
    assert json.loads(capsys.readouterr().out)['jev']['overridden']['n'] == 1
