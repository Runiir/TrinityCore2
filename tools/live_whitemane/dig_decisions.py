"""Original Laya head chooses legal digging actions with recent outcomes."""
from . import laya_ui
from .ui_choice import MODEL,REVISION


def choose(state):
    options={'observe':'Wait and observe without input','inspect':'Inspect minimap blips'}
    if state['available'] and not state['casting']:
        if state['artifact_visible']:options['loot']='Interact with the discovered archaeology artifact'
        if state.get('can_survey') and state.get('survey_ready'):
            options['survey']='Use Mouse Button 4 for a fresh Survey'
        if state.get('telescope'):
            options.update(turn_left='Turn left toward the guide',turn_right='Turn right toward the guide',
                forward_short='Move a small distance toward the guide',
                forward_long='Approach the guide endpoint; fly for red or distant markers')
    action,request,response=laya_ui.choose(state,
        'Recover archaeology artifacts. Prefer GatherMate markers. For red, fly along the telescope line; '
        'for green, take small steps. Approach a discovered artifact until its gathering cast starts. '
        'Use recent outcomes to change an approach that is not making progress.',options)
    return action,{'model':MODEL,'revision':REVISION,'adapter':None},request,response
