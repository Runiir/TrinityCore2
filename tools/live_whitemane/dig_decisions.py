"""Original Laya head chooses legal digging actions with recent outcomes."""
import math
import random
from . import laya_ui,decisions
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
    if ((state.get('survey_ready') or state.get('instrument_current')) and not state['artifact_visible']
            and not (state.get('pickup') or {}).get('uncollected')):
        # Keep the already-trained navigation schema. Pickup and new UI
        # operations use the original head below; navigation does not ask an
        # untrained general UI head to rediscover its existing task policy.
        navigation={key:state[key] for key in
            ('task','available','casting','artifact_visible','instrument_current')}
        tool=state.get('telescope')
        navigation['telescope']=({key:tool[key] for key in ('color','heading_relative_to_player')}
            if tool and state['instrument_current'] else None)
        return decisions.choose(navigation)
    options={'observe':'Wait if the client is unavailable or casting',
        'inspect':'Search the minimap if an artifact was discovered but cannot be located'}
    if state['available'] and not state['casting']:
        options['camera_forward']='Restore the camera if it has not been aligned recently'
        if state['artifact_visible'] or (state.get('pickup') or {}).get('uncollected'):
            options['loot']='Interact if a discovered artifact is uncollected and nearby; verify gathering cast or fragments'
        if state.get('mouseover_artifact'):
            options['mouseover_interact']='Press Mouse Button 5 on the artifact under the cursor'
        if (state.get('can_survey') and state.get('survey_ready')
                and not (state.get('pickup') or {}).get('uncollected')):
            options['survey']='Cast Survey if Survey is ready, no artifact is pending, and the guide has been reached'
        if state.get('telescope') and not state.get('guide_arrived'):
            options.update(forward_short='Approach if the current marker, telescope or artifact has not been reached',
                forward_long='Fly toward the current guide if it is red or far; otherwise approach it on foot')
    action,request,response=laya_ui.choose(state,
        'Collect discovered finds before more Survey or travel. A missed tooltip means locate the same find again. '
        'Estimated arrival is not pickup. A gathering cast confirms interaction range. '
        'Retain useful movement; steer with the camera. Prefer markers, then telescope: red fly, green approach. '
        'When guide_arrived is true and no artifact is pending, Survey here. '
        'Camera alignment without travel cannot discover an artifact. '
        'Resume digging after confirmed collection.',options)
    action=explore(action,response,options,state)
    return action,{'model':MODEL,'revision':REVISION,'adapter':None},request,response
