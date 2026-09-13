import copy
import unittest

from tools.bot_ml.rank_raid_damage_gaps import compare, interval_seconds


class GapComparisonTests(unittest.TestCase):
    def fixture(self):
        actor = {'class_spec': 'example', 'damage': {'hostile_originated': 1000},
                 'effective_hps': 5}
        timeline = {'identity': {'server_epoch': 7},
                    'window': {'complete': True, 'first_hostile_at_ms': 1000,
                               'native_boss_death_at_ms': 11000},
                    'summary': {'actors': {'1': actor}},
                    'events': [dict(actor_guid=1, kind='landed', at_ms=2000,
                                    amount=600, spell_id=10, source_is_pet=False),
                               dict(actor_guid=1, kind='landed', at_ms=8000,
                                    amount=400, spell_id=10, source_is_pet=True)]}
        refs = {'native_identity': timeline['identity'], 'actors': {'1': {'url': 'test', 'dps': 130, 'limitations': 'unmatched',
                                'next_check': 'inspect', 'duties': [
                                    {'provenance': 'observed', 'interval_ms': [6000, 11000]}],
                                'components': [{'name': 'owner', 'spell_ids': [10],
                                                'dps': 80}]}}}
        return timeline, refs

    def test_duty_overlap_and_window_clipping(self):
        self.assertEqual(interval_seconds([[0, 4000], [3000, 7000], [9000, 15000]],
                                          1000, 11000), 8)

    def test_pet_tail_during_duty_does_not_inflate_offensive_rate(self):
        timeline, refs = self.fixture()
        actor = compare(timeline, refs)['actors'][0]
        self.assertEqual(actor['native_dps'], 100)
        self.assertEqual(actor['observed_duty_union_seconds'], 5)
        self.assertEqual(actor['components'][0]['native_dps'], 60)
        self.assertIsNone(actor['recoverable_damage'])

    def test_unknown_duty_does_not_become_observed(self):
        timeline, refs = self.fixture()
        refs['actors']['1']['duties'][0]['provenance'] = 'inferred'
        self.assertIsNone(compare(timeline, refs)['actors'][0]['observed_duty_union_seconds'])

    def test_rejects_stale_duty_annotations(self):
        timeline, refs = self.fixture()
        refs['native_identity'] = {'server_epoch': 6}
        with self.assertRaisesRegex(ValueError, 'identity'):
            compare(timeline, refs)

    def test_rejects_missing_damage_and_overlapping_groups(self):
        timeline, refs = self.fixture()
        bad = copy.deepcopy(timeline)
        bad['events'].pop()
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            compare(bad, refs)
        refs['actors']['1']['components'] *= 2
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            compare(timeline, refs)


if __name__ == '__main__':
    unittest.main()
