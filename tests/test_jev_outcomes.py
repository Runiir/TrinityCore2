import json

import pytest

from tools.raid_program import jev_outcomes


def record(**changes):
    return {'unit': 'u1', 'candidates': ['fire_combustion_gap', 'elemental_cadence_gap'],
            'jev_pick': 'fire_combustion_gap', 'laya_pick': 'elemental_cadence_gap',
            'chosen': 'fire_combustion_gap', 'label_before': 'batch1', 'label_after': 'batch2',
            'party_delta': 812.5, 'actor_delta': 403.0} | changes


def test_append_and_summary_compare_each_model_against_the_scoreboard_delta(tmp_path):
    jev_outcomes.append(tmp_path, record())
    jev_outcomes.append(tmp_path, record(chosen='elemental_cadence_gap', party_delta=-100.0,
                                         actor_delta={'30010': -50.0}))
    jev_outcomes.append(tmp_path, record(laya_pick=None, party_delta=20.0))  # Laya offline
    rows = [json.loads(line) for line in (tmp_path / jev_outcomes.PATH).read_text().splitlines()]
    assert [r['laya_pick'] for r in rows] == ['elemental_cadence_gap', 'elemental_cadence_gap', None]
    assert all('recorded_at' in r for r in rows)
    result = jev_outcomes.summary(tmp_path)
    assert result['records'] == 3
    assert result['jev'] == {'n': 3, 'followed': {'n': 2, 'mean_party_delta': 416.25},
                             'overridden': {'n': 1, 'mean_party_delta': -100.0}}
    assert result['laya'] == {'n': 2, 'followed': {'n': 1, 'mean_party_delta': -100.0},
                              'overridden': {'n': 1, 'mean_party_delta': 812.5}}
    assert result['jev_laya_agreement'] == {'n': 2, 'agree': 0}


@pytest.mark.parametrize('changes,match', [
    ({'candidates': ['only_one']}, 'two distinct'),
    ({'candidates': ['a', 'a']}, 'two distinct'),
    ({'jev_pick': 'third_gap'}, 'null or one of the candidates'),
    ({'laya_pick': 'third_gap'}, 'null or one of the candidates'),
    ({'jev_pick': None, 'laya_pick': None}, 'at least one model pick'),
    ({'chosen': 'third_gap'}, 'chosen'),
    ({'party_delta': float('nan')}, 'finite'),
    ({'actor_delta': 'big'}, 'actor_delta'),
    ({'label_after': ''}, 'label_after'),
    ({'extra': 1}, 'exactly'),
])
def test_incomplete_or_unsanctioned_records_are_rejected(tmp_path, changes, match):
    with pytest.raises(ValueError, match=match):
        jev_outcomes.append(tmp_path, record(**changes))
    assert not (tmp_path / jev_outcomes.PATH).exists()


def test_cli_append_without_laya(tmp_path, capsys):
    assert jev_outcomes.main(['--root', str(tmp_path), 'append', '--unit', 'u1', '--candidate', 'a', '--candidate', 'b',
                              '--jev-pick', 'a', '--chosen', 'b', '--label-before', 'l0', '--label-after', 'l1',
                              '--party-delta', '5', '--actor-delta', '{"30001": 2.5}']) == 0
    row = json.loads(capsys.readouterr().out)
    assert row['actor_delta'] == {'30001': 2.5} and row['laya_pick'] is None
    assert jev_outcomes.main(['--root', str(tmp_path), 'summary']) == 0
    assert json.loads(capsys.readouterr().out)['jev']['overridden']['n'] == 1
