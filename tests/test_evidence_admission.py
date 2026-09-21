import json

from test_rotation_mechanics_review import _apl, _compute_stats, _gear_fixture, _effective_stats_runtime, _debug_result_with_pet_stats
from tools.raid_program.evidence_admission import admission


def test_existing_stat_policy_is_joined_without_duplicate_previous_bots(tmp_path):
    runtime = _effective_stats_runtime(intellect=9000)
    bots = runtime['combat_calibration']['previous_window']['bots']
    runtime['combat_calibration'].update(bots=bots, window_complete=True, scored_seconds=300)
    request, _ = _gear_fixture()
    request['raid']['parties'][0]['players'][0]['rotation'] = _apl()
    paths = []
    for i, doc in enumerate((runtime, request, _debug_result_with_pet_stats(), _compute_stats())):
        path = tmp_path/f'{i}.json'; path.write_text(json.dumps(doc)); paths.append(str(path))
    summary, full = admission(*paths, 'self_provided_baseline')
    assert summary['actor'] == '1306'
    assert summary['gates']['effective_stat_parity']['status'] == 'match'
    strict, _ = admission(*paths, 'controlled_live_parity')
    assert strict['gates']['effective_stat_parity']['status'] == 'mismatch'
    assert strict['setup_comparison_admitted'] is False
