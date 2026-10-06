"""Outcome-admission tests with deliberately adversarial transition records."""
import copy
import unittest

from .archeolog_dataset import candidate, digest, group_splits, rlvr_admission, verifier


def observation(at, north, facing=0, surveys=0, finds=0, fragments=0):
    return {'observed_at': at, 'runtime': {'pid': 1, 'start_ticks': '1'},
        'movement': {'in_world': True, 'dead': False, 'client_uptime_ms': at * 1000,
                     'facing_radians': facing},
        'archaeology': {'client_uptime_ms': at * 1000, 'site_id': 7,
            'world': {'instance': 1, 'north': north, 'west': 0},
            'successful_surveys': surveys, 'last_survey_uptime_ms': at * 1000 - 200,
            'looted_finds': finds, 'races': [{'index': 1, 'fragments': fragments}]},
        'channel_ages': {'M': .1, 'A': .2}}


def step(action='forward_short'):
    return {'action': action, 'started_at': 10.1, 'finished_at': 11.1,
        'completed': True, 'input_evidence': True,
        'before': observation(10, 0), 'after': observation(11, 4),
        'guide': {'world': {'instance': 1, 'north': 10, 'west': 0}},
        'request': {'state': {'distance_yards': 10}, 'questions': {'action': {
            'type': 'choice', 'instructions': 'Reach the retained destination',
            'criteria': {'forward_short': 'Move forward', 'observe': 'Wait'}}}}}


class ArcheologAdmissionTests(unittest.TestCase):
    def test_completion_flag_without_progress_is_rejected(self):
        row = step()
        row['after']['archaeology']['world']['north'] = 0
        self.assertEqual(verifier(row, row['action'])[1], 'no_measured_approach')

    def test_approach_is_measured_toward_original_target(self):
        row = step()
        reward, reason = verifier(row, row['action'])
        self.assertIsNone(reason)
        self.assertEqual(reward['after_yards'], 6)
        row['guide']['world']['north'] = -10
        self.assertEqual(verifier(row, row['action'])[1], 'no_measured_approach')

    def test_failures_are_not_positive_even_if_distance_improves(self):
        row = step()
        row['failure'] = 'tooltip observation did not follow the cursor'
        self.assertEqual(verifier(row, row['action'])[1], 'runtime_or_action_failure')

    def test_stale_or_repeated_frame_is_rejected(self):
        row = step()
        row['after']['movement']['client_uptime_ms'] = 10000
        self.assertEqual(verifier(row, row['action'])[1], 'unchanged_or_missing_public_frame')
        row = step()
        row['before']['channel_ages']['M'] = 5
        self.assertEqual(verifier(row, row['action'])[1], 'stale_public_channel')

    def test_pickup_requires_fragments_counter_and_interaction(self):
        row = step('loot')
        row['after'] = observation(11, 0, finds=1, fragments=5)
        self.assertIsNotNone(verifier(row, 'loot')[0])
        row['input_evidence'] = False
        self.assertEqual(verifier(row, 'loot')[1], 'pickup_not_independently_attributed')

    def test_survey_requires_fresh_counter_and_actual_input(self):
        row = step('survey')
        row['after'] = observation(11, 0, surveys=1)
        self.assertIsNotNone(verifier(row, 'survey')[0])
        row['after']['archaeology']['last_survey_uptime_ms'] = 999
        self.assertEqual(verifier(row, 'survey')[1], 'survey_not_fresh_or_not_successful')

    def test_known_assistance_and_client_lifetime_changes_rejected(self):
        row = step()
        row['manual_input'] = True
        self.assertEqual(verifier(row, row['action'])[1], 'known_intervention')
        row = step()
        row['after']['runtime']['start_ticks'] = '2'
        self.assertEqual(verifier(row, row['action'])[1], 'client_lifetime_changed_or_missing')

    def test_admitted_input_never_contains_current_outcome(self):
        row = step()
        result, reason = candidate(row, {'member': 'episode/session.json'})
        self.assertIsNone(reason)
        self.assertEqual(result['state'], row['request']['state'])
        self.assertNotIn('after_yards', result['state'])
        self.assertFalse(result['rlvr_eligible'])

    def test_omitted_pickup_fact_blocks_travel_label(self):
        row = step('flight')
        row['request']['questions']['action']['criteria'] = {'flight': 'Fly', 'observe': 'Wait'}
        row['state'] = {'pending_pickup': True}
        self.assertEqual(candidate(row, {'member': 'episode/session.json'})[1], 'omitted_pending_pickup_fact')

    def test_lifetimes_and_known_sites_do_not_cross_training_and_test(self):
        rows = [{'id': 'a', 'client_lifetime': 'old', 'site_id': 1, 'started_at': 1},
                {'id': 'b', 'client_lifetime': 'old', 'site_id': 2, 'started_at': 2},
                {'id': 'c', 'client_lifetime': 'new', 'site_id': 2, 'started_at': 3}]
        splits, _, purged = group_splits(rows)
        self.assertEqual([row['id'] for row in splits['train']], ['a'])
        self.assertEqual([row['id'] for row in splits['test']], ['c'])
        self.assertEqual([row['id'] for row in purged], ['b'])
        self.assertEqual(splits['validation'], [])

    def test_rlvr_requires_gap_free_unassisted_on_policy_evidence(self):
        transition = step()
        question = transition['request']['questions']['action']
        trajectory = {'policy': {'weights_sha256': 'a' * 64, 'config_sha256': 'b' * 64},
            'intervention_ledger': {'complete': True, 'events': []},
            'transition_gap_free': True, 'terminal_state': 'progress',
            'input_sha256': digest({'state': transition['request']['state'], 'question': question}),
            'selected_action_probability': .8, 'rollout_source': 'on_policy',
            'behavior_policy_probabilities': {'forward_short': .8, 'observe': .2},
            'transition': transition}
        self.assertIsNone(rlvr_admission(trajectory)[1])
        unknown = copy.deepcopy(trajectory)
        unknown['intervention_ledger']['complete'] = False
        self.assertEqual(rlvr_admission(unknown)[1], 'rlvr_intervention_ledger_incomplete_or_assisted')
        fabricated = copy.deepcopy(trajectory)
        fabricated['selected_action_probability'] = 1.
        self.assertEqual(rlvr_admission(fabricated)[1], 'rlvr_on_policy_distribution_missing_or_inconsistent')

    def test_rlvr_valid_no_progress_has_zero_reward_but_failure_is_quarantined(self):
        transition = step()
        transition['after']['archaeology']['world']['north'] = 0
        question = transition['request']['questions']['action']
        trajectory = {'policy': {'weights_sha256': 'a' * 64, 'config_sha256': 'b' * 64},
            'intervention_ledger': {'complete': True, 'events': []},
            'transition_gap_free': True, 'terminal_state': 'no_progress',
            'input_sha256': digest({'state': transition['request']['state'], 'question': question}),
            'selected_action_probability': .8, 'rollout_source': 'on_policy',
            'behavior_policy_probabilities': {'forward_short': .8, 'observe': .2},
            'transition': transition}
        self.assertEqual(rlvr_admission(trajectory)[0]['outcome']['reward'], 0.)
        transition['failure'] = 'stale frame'
        self.assertEqual(rlvr_admission(trajectory)[1], 'runtime_or_action_failure')


if __name__ == '__main__':
    unittest.main()
