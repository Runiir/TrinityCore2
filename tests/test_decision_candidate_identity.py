"""Counterexamples for attributing outcomes to the recorded chosen candidate."""
import json

import pytest

from tools.bot_ml.build_decision_dataset import build_rows, chosen_candidate_index


@pytest.mark.parametrize(('candidates', 'chosen', 'activity', 'expected'), [
    ([{'candidate_id': 'a', 'activity': 'cast'}], {'candidate_id': 'missing'}, 'cast', -1),
    ([{'candidate_id': 'a'}, {'candidate_id': 'a'}], {'candidate_id': 'a'}, '', -1),
    ([{'activity': 'cast'}, {'activity': 'cast'}], {}, 'cast', -1),
    ([{'activity': 'cast'}], {}, 'heal', -1),
    ([{}], {}, '', -1),
    ([{'action_id': 7}], {'action_id': 8}, '', -1),
    ([{'action_id': 7}, {'action_id': 7}], {'action_id': 7}, '', -1),
    ([{'candidate_id': 'a', 'action_id': 7}, {'candidate_id': 'b', 'action_id': 7}],
     {'candidate_id': 'b', 'action_id': 7}, '', 1),
    ([{'action_id': 7}, {'action_id': 8}], {'action_id': 8}, '', 1),
    ([{'activity': 'cast'}, {'activity': 'heal'}], {}, 'heal', 1),
])
def test_chosen_identity_requires_a_unique_match(candidates, chosen, activity, expected):
    assert chosen_candidate_index(candidates, chosen, activity) == expected


def test_missing_chosen_candidate_cannot_label_first_candidate_as_success():
    rows = build_rows({
        'candidate_actions_json': json.dumps([{'candidate_id': 'a', 'activity': 'cast'}]),
        'chosen_action_json': json.dumps({'candidate_id': 'missing', 'activity': 'cast'}),
        'reward': 10,
    })
    assert rows[0]['candidate_selection_status'] == 'unresolved'
    assert rows[0]['label_observed'] == rows[0]['is_chosen'] == 0
    assert rows[0]['imitate_teacher'] == 0
    assert rows[0]['action_success'] == 0


def test_dataset_export_quarantines_missing_and_ambiguous_candidates(tmp_path, monkeypatch):
    from tools.bot_ml import build_decision_dataset as builder
    from tools.bot_ml.common import table_path

    def table(name, rows):
        path = table_path(tmp_path, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    table('experiment_bot_runs', [{'id': 1, 'status': 'stopped', 'ended_at': '2026-09-05T12:00:00Z', 'config_json': json.dumps({
        'runtime_mode': 'manual_experiment', 'non_certifying_assistance': False,
    })}])
    decisions = []
    for identity, candidates in enumerate([
        [], [{'candidate_id': 'wrong'}], [{'candidate_id': 'selected'}],
    ], 1):
        decisions.append({'id': identity, 'run_id': 1, 'reward': 10,
                          'candidate_actions_json': json.dumps(candidates),
                          'chosen_action_json': json.dumps({'candidate_id': 'selected'})})
    decisions.append({'id': 4, 'run_id': 1, 'reward': 10,
        'candidate_actions_json': json.dumps({
            'activity_candidates': [{'activity': 'raid'}, {'activity': 'rest'}],
            'combat_action_mask': {'actions': [{'action_id': 7}]},
        }),
        'chosen_action_json': json.dumps({'activity': 'raid', 'structured_action': {'action_id': 7}}),
    })
    table('experiment_bot_decisions', decisions)
    monkeypatch.setattr(builder, 'write_parquet_if_available', lambda *args: False)
    output, manifest = tmp_path / 'dataset.jsonl', tmp_path / 'manifest.json'
    monkeypatch.setattr('sys.argv', ['build_decision_dataset', '--input-dir', str(tmp_path),
                                   '--output', str(output), '--manifest', str(manifest)])
    assert builder.main() == 0
    admitted = [json.loads(line) for line in output.read_text().splitlines()]
    quarantined = [json.loads(line) for line in output.with_name('dataset.quarantine.jsonl').read_text().splitlines()]
    assert [row['decision_id'] for row in admitted] == [3, 4, 4]
    native_rows = [row for row in admitted if row['decision_id'] == 4]
    assert [row['candidate_activity'] for row in native_rows if row['is_chosen']] == ['raid']
    assert all(row['candidate_domain'] == 'activity_selection' for row in native_rows)
    assert [row['decision_id'] for row in quarantined] == [1, 2, 4]
    assert json.loads(manifest.read_text())['candidate_identity_quarantine']['reasons'] == {
        'missing_candidate_set': 1, 'unresolved': 1,
        'unsupported_decision_domain': 1,
    }


def test_exported_outcomes_and_selected_action_do_not_become_policy_inputs():
    from tools.bot_ml.common import numeric_features
    decision = {
        'id': 100, 'run_id': 7, 'bot_guid': 9,
        'candidate_actions_json': json.dumps([{'candidate_id': 'a', 'score': 2}]),
        'chosen_action_json': json.dumps({'candidate_id': 'a', 'spell_id': 17}),
        'raw_state_json': json.dumps({'health_pct': 0.7}),
        'outcome_json': json.dumps({'damage': 900, 'success': True}),
        'reward': 20,
    }
    row = build_rows(decision)[0]
    assert row['json_outcome_damage'] == 900  # retained for diagnosis
    features = numeric_features(row)
    assert features['json_raw_health_pct'] == 0.7
    assert features['json_candidate_score'] == 2
    assert not any(key.startswith(('json_chosen_', 'json_outcome_')) for key in features)
    assert not {'run_id', 'decision_id', 'bot_guid', 'candidate_index', 'no_future_events'} & features.keys()
    # Future outcomes and record identities cannot change the model's input.
    row.update(json_outcome_damage=-500, json_chosen_spell_id=31,
               run_id=123, decision_id=999, no_future_events=1)
    assert numeric_features(row) == features


@pytest.mark.parametrize(('status', 'ended_at', 'admitted'), [
    ('running', None, False), ('running', '2026-09-05T12:00:00Z', False),
    ('stopped', None, False), ('stopped', 'not-a-time', False),
    ('stopped', '2026-09-05T12:00:00Z', True),
])
def test_training_requires_native_run_stop(status, ended_at, admitted):
    from tools.bot_ml.build_decision_dataset import player_like_training_run_ids
    run = {'id': 1, 'status': status, 'ended_at': ended_at, 'config_json': {
        'runtime_mode': 'manual_experiment', 'non_certifying_assistance': False,
    }}
    assert player_like_training_run_ids([run]) == ({1} if admitted else set())


def test_candidate_scores_do_not_inherit_selected_action_or_future_outcome():
    from tools.bot_ml.common import numeric_features
    decision = {
        'candidate_actions_json': [{'candidate_id': 'a'}],
        'chosen_action_json': {'candidate_id': 'a', 'confidence': 0.8, 'activity_score': 17},
        'outcome_json': {'expected_value': 900},
    }
    before = numeric_features(build_rows(decision)[0])
    decision['chosen_action_json'].update(confidence=0.1, activity_score=-99)
    decision['outcome_json']['expected_value'] = -1000
    after = numeric_features(build_rows(decision)[0])
    assert before == after
    assert after['utility_score'] == after['confidence'] == 0


def test_final_outcome_aggregates_do_not_change_policy_inputs():
    from tools.bot_ml.common import numeric_features
    decision = {'area_id': 1, 'bot_guid': 2, 'decision_fingerprint_hash': 3,
                'candidate_actions_json': [{'candidate_id': 'a'}],
                'chosen_action_json': {'candidate_id': 'a'}}
    before = build_rows(decision)[0]
    after = build_rows(decision, semantic_stats={('area', 1): {
        'successes': 999, 'failures': 42, 'avg_reward': 987,
        'features_json': {'future_deaths': 500},
    }}, decision_fingerprints={(2, 3): {'repeat_count': 100, 'failure_count': 99}})[0]
    assert after['stat_area_successes'] == 999  # Retained for audit only.
    assert numeric_features(before) == numeric_features(after)
    assert before['features_hash'] == after['features_hash']


def test_candidate_groups_do_not_collide_across_runs_actors_or_domains():
    from tools.bot_ml.train_policy_model import teacher_choice_training_rows
    from tools.bot_ml.evaluate_policy_model import ranking_metrics
    from tools.bot_ml.validate_data_quality import group_by_decision
    chosen = {'run_id': 1, 'bot_guid': 2, 'decision_id': 3,
              'candidate_domain': 'activity_selection', 'split': 'train',
              'is_chosen': 1, 'imitate_teacher': 1}
    negative = {**chosen, 'is_chosen': 0, 'imitate_teacher': 0}
    unrelated = [{**negative, **change} for change in [
        {'run_id': 9}, {'bot_guid': 9}, {'candidate_domain': 'combat_action'},
    ]]
    rows = [chosen, negative, *unrelated]
    assert teacher_choice_training_rows(rows) == [chosen, negative]
    assert len(group_by_decision(rows)) == 4
    metrics = ranking_metrics(rows, {id(row): {'action_success': 1 if row['is_chosen'] else 0} for row in rows})
    assert metrics['ranked_decisions'] == 1
    assert metrics['unrankable_decisions'] == 3


def test_training_refuses_eval_only_labels_before_writing_model(tmp_path, monkeypatch):
    from tools.bot_ml import train_policy_model as trainer
    rows = [{'run_id': 1, 'split': 'eval', 'label_observed': 1, 'action_success': 1}]
    with pytest.raises(ValueError, match='no observed training labels'):
        trainer.fit_baseline(rows, [])
    dataset = tmp_path / 'dataset.jsonl'
    dataset.write_text(json.dumps(rows[0]) + '\n')
    model_dir = tmp_path / 'models'
    monkeypatch.setattr('sys.argv', ['train_policy_model', '--dataset', str(dataset),
                                   '--model-dir', str(model_dir), '--backend', 'linear_baseline'])
    with pytest.raises(SystemExit, match='no observed training labels'):
        trainer.main()
    assert not model_dir.exists()


@pytest.mark.parametrize('rows', [
    [{'run_id': 1, 'split': 'train', 'label_observed': 1}],
    [{'run_id': 1, 'split': 'eval', 'label_observed': 0}],
])
def test_evaluation_refuses_training_or_unobserved_rows(tmp_path, monkeypatch, rows):
    from tools.bot_ml import evaluate_policy_model as evaluator
    dataset = tmp_path / 'dataset.jsonl'
    dataset.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    monkeypatch.setattr('sys.argv', ['evaluate_policy_model', '--dataset', str(dataset)])
    monkeypatch.setattr(evaluator, 'load_model_artifact', lambda *args: pytest.fail('loaded model before holdout gate'))
    with pytest.raises(SystemExit, match='no observed evaluation labels'):
        evaluator.main()
