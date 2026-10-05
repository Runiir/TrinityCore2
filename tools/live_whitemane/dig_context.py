"""Measured navigation and pickup feedback for Laya, without action selection."""
import math
from . import guide as routes


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
    state.update(can_survey=row['archaeology']['can_survey'],
        survey_ready=bool((ui.get('survey') or {}).get('ready')),
        guide_source=guide['source'] if guide else None, pending_pickup=bool(pending),
        named_artifact=ui.get('soft_interact', {}).get('name'),
        pickup_range='out_of_range' if pending and pending['out_of_range'] else 'unknown')
    if guide:
        state['telescope'] = {key: guide[key] for key in ('color', 'heading_relative_to_player')}
        state['telescope'].update(distance_yards=round(guide['distance_yards'], 2),
            bearing_error_degrees=bearing_error(row, guide))
        state['guide_position_is_estimate'] = guide['source'] != 'visible owned archaeology find'
        state['guide_arrived'] = guide['arrived']
    recent = []
    for step in steps[-3:]:
        result = {'action': step['action'], 'moved_yards': round(step.get('walked_yards', 0), 2),
                  'pickup_confirmed': bool(step.get('confirmed_looted_find'))}
        if step.get('guide') and step.get('after'):
            result['bearing_before_deg'] = bearing_error(step['before'], step['guide'])
            result['bearing_after_deg'] = bearing_error(step['after'], step['guide'])
        if step.get('outcome'):
            result['outcome'] = step['outcome']
        recent.append(result)
    state['recent_outcomes'] = recent
    turns = 0
    for step in reversed(steps):
        if (not step.get('completed') or not step['action'].startswith('turn_')
                or step.get('walked_yards', 0) > .25 or step.get('confirmed_looted_find')):
            break
        turns += 1
    state['consecutive_turns_without_approach'] = turns
    stalled = 0
    for step in reversed(steps):
        if (not step.get('completed') or step.get('walked_yards', 0) > .25
                or step.get('confirmed_looted_find')):
            break
        stalled += 1
    state['consecutive_actions_without_progress'] = stalled
    return state
