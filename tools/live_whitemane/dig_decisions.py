"""Original Laya head chooses legal digging actions with recent outcomes."""
import math
import random
from . import laya_ui,decisions
from .ui_choice import MODEL,REVISION


def explore(action, response, options, state):
    """Sample Laya's full policy after repeated actions without progress."""
    if state.get('consecutive_actions_without_progress', state.get('consecutive_turns_without_approach', 0)) < 3:
        return action
    recent=state.get('recent_outcomes')
    if recent and not any(s['action']==action and s.get('moved_yards',0)<=.25
            and not s.get('pickup_confirmed') for s in recent):
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
    pickup=state.get('pickup') or {}
    named_pickup=(state['artifact_visible'] and pickup.get('uncollected')
        and pickup.get('interaction_in_range') is not False)
    vertical=state.get('artifact_height_error_yards')
    adjust_depth=state.get('swimming') and pickup.get('uncollected') and (
        vertical is not None and abs(vertical)>.5 or
        pickup.get('interaction_in_range') is False and state.get('guide_arrived'))
    if not adjust_depth and (named_pickup or ((state.get('survey_ready') or state.get('instrument_current'))
            and not state['artifact_visible'] and not pickup.get('uncollected'))):
        # Keep the already-trained navigation schema. Pickup and new UI
        # operations use the original head below; navigation does not ask an
        # untrained general UI head to rediscover its existing task policy.
        # The retained head also learned interaction with a visible find.
        # A current range error needs the separate approach facts below.
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
        options['camera_ground']='Look down toward the nearby ground if artifact tooltip searches missed the pending find'
        if state['artifact_visible'] or (state.get('pickup') or {}).get('uncollected'):
            options['loot']='Interact if a discovered artifact is uncollected and nearby; verify gathering cast or fragments'
        if state.get('mouseover_artifact'):
            options['mouseover_interact']='Press Mouse Button 5 on the artifact under the cursor'
        provisional=(pickup.get('uncollected') and not pickup.get('discovery_confirmed')
            and pickup.get('tooltip_search_misses',0)>0)
        if (state.get('can_survey') and state.get('survey_ready')
                and (not pickup.get('uncollected') or provisional)):
            options['survey']='Cast Survey if Survey is ready, no artifact is pending, and the guide has been reached'
            if provisional:
                options['survey']='Repeat Survey here if a provisional discovery has no named find and tooltip searches failed'
        if state.get('telescope') and not state.get('guide_arrived'):
            options.update(forward_short='Approach if the current marker, telescope or artifact has not been reached',
                forward_long='Fly toward the current guide if it is red or far; otherwise approach it on foot')
        if state.get('swimming'):
            options['swim_up']='Swim upward toward the artifact depth or to test a higher interaction position'
            options['swim_down']='Swim downward toward the artifact depth or to test a lower interaction position'
            if 'forward_long' in options:options['forward_long']='Swim toward the current recorded marker or telescope guide'
    context=state
    instructions=(
        'Collect discovered finds before more Survey or travel. A missed tooltip means locate the same find again. '
        'Estimated arrival is not pickup. A gathering cast confirms interaction range. '
        'Retain useful movement; steer with the camera. Prefer markers, then telescope: red fly, green approach. '
        'When guide_arrived is true and no artifact is pending, Survey here. '
        'Camera alignment without travel cannot discover an artifact. '
        'Resume digging after confirmed collection.')
    if pickup.get('interaction_in_range') is False and state.get('telescope'):
        # Keep the action vocabulary; provide the immediate range correction
        # without unrelated Survey history or a second pickup-priority vote.
        context={k:state.get(k) for k in ('available','casting','named_artifact',
            'mouseover_artifact','pickup_activity','guide_arrived')}
        context.update(in_range=False,distance_yards=state['telescope'].get('distance_yards'),
            swimming=state.get('swimming'),artifact_height_error_yards=vertical,
            facing_target=state['telescope'].get('heading_relative_to_player'),
            camera_aligned=state.get('camera_recently_aligned'),
            ground_visible=state.get('ground_view_recently_adjusted'))
        instructions=('Choose the next action to collect this artifact. If out of range, move closer. '
            'If close enough, interact. When swimming, a negative artifact_height_error_yards means swim down; '
            'positive means swim up. If horizontal distance is already small but depth is unknown, '
            'test a small depth change and recheck interaction. Camera movement alone cannot collect it.')
        descriptions={'observe':'Wait while casting or unavailable',
            'inspect':'Locate an artifact whose position is unknown',
            'camera_forward':'Align the camera with the character','camera_ground':'Look down at the ground',
            'loot':'Interact with the named artifact','mouseover_interact':'Interact with the artifact under the mouse',
            'forward_short':'Walk closer to the artifact','forward_long':'Move toward the destination'}
        descriptions.update(swim_up='Swim upward toward the artifact depth',swim_down='Swim downward toward the artifact depth')
        options={key:descriptions[key] for key in options}
    if state.get('swimming') and vertical is not None and abs(vertical)>.5:
        direction='down' if vertical<0 else 'up'
        context={**context,'direction_to_artifact':direction,
            'artifact_location_relative_to_player':'below' if vertical<0 else 'above',
            'vertical_distance_yards':abs(vertical)}
        for move in ('up','down'):
            key='swim_'+move
            if key in options:options[key]='Swim '+move+(' toward' if move==direction else ' away from')+' the observed artifact depth'
        instructions+=' The artifact is vertically '+direction+' from the current position. Choose movement toward its depth.'
    action,request,response=laya_ui.choose(context,instructions,options)
    action=explore(action,response,options,state)
    return action,{'model':MODEL,'revision':REVISION,'adapter':None},request,response
