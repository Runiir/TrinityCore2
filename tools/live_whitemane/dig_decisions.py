"""Original Laya head chooses legal digging actions with recent outcomes."""
import math
import random
from . import laya_ui
from .ui_choice import MODEL,REVISION


def explore(action, response, options, state):
    """Sample Laya's full policy after repeated actions without progress."""
    if state.get('consecutive_actions_without_progress', state.get('consecutive_turns_without_approach', 0)) < 3:
        return action
    probabilities = response['answers']['action']['probabilities']
    if (set(probabilities) != set(options) or any(not isinstance(p, (int, float))
            or not math.isfinite(p) or p < 0 for p in probabilities.values())
            or not .99 <= sum(probabilities.values()) <= 1.01):
        raise RuntimeError('Laya exploration requires a complete legal action distribution')
    selected = random.choices(list(options), weights=[probabilities[key] for key in options], k=1)[0]
    response['policy_selection'] = {'method': 'sample_Laya_probabilities_after_stalled_actions',
        'argmax_action': action, 'selected_action': selected,
        'probabilities_modified': False, 'actions_removed': []}
    return selected


def choose(state):
    options={'observe':'Wait without input','inspect':'Read minimap blips'}
    if state['available'] and not state['casting']:
        if state['artifact_visible']:options['loot']='Interact with named find; observe range or gathering cast'
        if state.get('can_survey') and state.get('survey_ready'):
            options['survey']='Survey using Mouse Button 4'
        if state.get('telescope'):
            options.update(turn_left='Rotate left; position unchanged',turn_right='Rotate right; position unchanged',
                forward_short='Walk closer in a small step',
                forward_long='Approach guide; fly if red or far')
    action,request,response=laya_ui.choose(state,
        'Collect archaeology finds. Test pickup range by interacting with a named find. '
        'Turns change facing, never distance. Use bearing and outcomes to improve the approach. '
        'An estimated endpoint does not prove pickup range. After pickup, Survey again. '
        'Prefer GatherMate markers; red fly, green small steps.',options)
    action=explore(action,response,options,state)
    return action,{'model':MODEL,'revision':REVISION,'adapter':None},request,response
