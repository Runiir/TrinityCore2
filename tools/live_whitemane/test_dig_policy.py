from .dig_policy import DigProgress, SolveBatches


def test_marker_loop_falls_back_and_stays_until_looted_find():
    progress = DigProgress()
    assert progress.guidance(site_id=41, looted_finds=0, visible_marker='old') == 'gathermate_minimap_marker'
    assert not progress.failed_marker_survey('old')
    assert progress.failed_marker_survey('old')
    assert progress.guidance(site_id=41, looted_finds=0, visible_marker='old') == 'telescope'
    assert progress.guidance(site_id=41, looted_finds=0, visible_marker='other') == 'telescope'
    assert progress.guidance(site_id=41, looted_finds=1, visible_marker='new') == 'gathermate_minimap_marker'


def test_position_stall_falls_back_after_three_repeated_decisions():
    progress = DigProgress(site_id=41)
    assert not progress.decision_outcome(action='forward_long', position=(1, 2), progress=False)
    assert not progress.decision_outcome(action='forward_long', position=(1, 2), progress=False)
    assert progress.decision_outcome(action='forward_long', position=(1, 2), progress=False)


def test_solve_batch_continues_below_trigger_with_maximum_bag_stones():
    batches = SolveBatches()
    race = {'index': 9, 'fragments': 149, 'cost': 45, 'sockets': 2,
            'keystones_in_bags': 5, 'project_spell': 123}
    assert batches.next_project(race) is None
    race['fragments'] = 150
    assert batches.next_project(race)['keystones'] == 2
    race.update(fragments=30, keystones_in_bags=1, project_spell=124)
    assert batches.next_project(race) is None
    race.update(fragments=33)
    assert batches.next_project(race) is None  # New batch needs the 150 trigger again.


def test_race_batches_are_independent_and_recheck_project_affordability():
    batches = SolveBatches()
    race = {'index': 1, 'fragments': 150, 'cost': 45, 'sockets': 0,
            'keystones_in_bags': 0, 'project_spell': 10}
    assert batches.next_project(race)['fragments_required'] == 45
    race.update(fragments=105, cost=100, project_spell=11)
    assert batches.next_project(race)['project_spell'] == 11
    other = dict(race, index=9, fragments=19)
    assert batches.next_project(other) is None
