"""Measured navigation and pickup feedback for Laya, without action selection."""
import math
from . import guide as routes
from . import pending_find


def bearing_error(row, guide):
    if not guide:
        return None
    world = row['archaeology']['world']
    target = guide['world']
    bearing = math.atan2(target['west'] - world['west'], target['north'] - world['north'])
    error = (bearing - row['movement']['facing_radians'] + math.pi) % math.tau - math.pi
    return round(math.degrees(error), 1)


def model_state(row, guide, visible_find, pending, steps):
    state = routes.model_state(row, guide, visible_find)
    ui = row.get('farm_ui') or {}
    state['camera_recovery_macro_available']=bool(ui.get('camera_macros'))
    state['camera_zoom']=ui.get('camera_zoom')
    state['camera_input']=ui.get('camera_input')
    state.update(combat=row['movement']['in_combat'],can_survey=row['archaeology']['can_survey'],
        survey_ready=bool((ui.get('survey') or {}).get('ready')),
        guide_source=guide['source'] if guide else None, pending_pickup=bool(pending),
        named_artifact=ui.get('soft_interact', {}).get('name') or ui.get('tooltip'),
        pickup_range='out_of_range' if pending and pending['out_of_range'] else 'unknown')
    state.update({key:row['archaeology'].get(key) for key in ('mounted','flying','falling','swimming')})
    state['height_yards']=(row.get('owned_pose') or {}).get('height_yards')
    state.update(pending_find.pickup_position_facts(row))
    state['Survey_dismounts_on_ground']=bool(row['archaeology']['mounted'] and
        not row['archaeology'].get('flying') and not row['archaeology'].get('falling'))
    if pending:
        state['pickup']=pending_find.facts(row,pending)
        state['pickup_activity']=pending_find.stage(state['pickup'],row['archaeology']['casting'])
    if ui.get('tooltip') in pending_find.FIND_NAMES:
        state['mouseover_artifact']=ui['tooltip']
        state['mouseover_interact_binding']='Mouse Button 5'
    if guide:
        state['telescope'] = {key: guide[key] for key in ('color', 'heading_relative_to_player')}
        state['telescope'].update(distance_yards=round(guide['distance_yards'], 2),
            bearing_error_degrees=bearing_error(row, guide))
        state['guide_position_is_estimate'] = guide['source'] != 'visible owned archaeology find'
        state['guide_arrived'] = guide['arrived']
        state['recorded_marker_matches'] = guide.get('recorded_marker_matches')
        state['artifact_height_error_yards']=guide.get('height_error_yards')
        state['survey_range'] = ui.get('survey_guidance')
    recent = []
    for step in steps[-3:]:
        result = {'action': step['action'], 'moved_yards': round(max(step.get('walked_yards', 0),step.get('vertical_yards',0)), 2),
                  'pickup_confirmed': bool(step.get('confirmed_looted_find'))}
        if step.get('guide') and step.get('after'):
            before = bearing_error(step['before'], step['guide'])
            after = bearing_error(step['after'], step['guide'])
            result['bearing_improvement_degrees'] = round(abs(before) - abs(after), 1)
        if step.get('outcome'):
            result['outcome'] = {'waypoint_already_arrived_no_movement': 'already_arrived',
                'out_of_range_approach_same_pending_find': 'out_of_range',
                'Survey_deferred_until_cooldown_ready': 'cooldown',
                'waiting_for_public_survey_cooldown': 'cooldown'}.get(step['outcome'], step['outcome'])
        if step.get('failure'):
            result['outcome']='tooltip_search_missed' if 'no matching public tooltip' in step['failure'] else 'action_interrupted'
        recent.append(result)
    state['recent_outcomes'] = recent
    state['camera_recently_aligned'] = any(step['action'] in ('camera_forward','camera_macro') and step.get('completed')
        for step in steps[-3:])
    state['ground_view_recently_adjusted'] = any(step['action']=='camera_ground' and step.get('completed')
        for step in steps[-3:])
    turns = 0
    for step in reversed(steps):
        if (not step.get('completed') or not step['action'].startswith('turn_')
                or max(step.get('walked_yards', 0),step.get('vertical_yards',0)) > .25 or step.get('confirmed_looted_find')):
            break
        turns += 1
    state['consecutive_turns_without_approach'] = turns
    stalled = 0
    for step in reversed(steps):
        if (not (step.get('completed') or step.get('failure')) or max(step.get('walked_yards', 0),step.get('vertical_yards',0)) > .25
                or step.get('confirmed_looted_find')):
            break
        stalled += 1
    state['consecutive_actions_without_progress'] = stalled
    camera=ui.get('camera_input') or {}
    state['camera_recovery_relevant']=bool(camera.get('mouselooking') or camera.get('right_down')
        or ui.get('camera_zoom') is not None and ui['camera_zoom']<5
        or pending and pending.get('tooltip_search_misses',0)>=2)
    return state
