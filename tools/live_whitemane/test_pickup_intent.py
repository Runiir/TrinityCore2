import copy
from . import pickup_intent
from .test_farm_loop import row


def test_selected_collection_survives_range_correction_but_not_a_new_find():
    r=row();pending={'observed_at':1,'out_of_range':False};session={}
    pickup_intent.offer(session,r,pending,'loot',{'model':'Laya'},{'state':'observed'}, {'choice':'loot'})
    pending['out_of_range']=True
    assert pickup_intent.retained(session,r,pending) is None
    pending['out_of_range']=False
    action,model,request,response=pickup_intent.retained(session,r,pending)
    assert action=='loot' and model=={'model':'Laya'} and response['model_decision_reused']
    assert pickup_intent.retained(session,r,dict(pending,observed_at=2)) is None
    assert pickup_intent.retained(session,r,None) is None and not session


def test_missing_tooltip_or_combat_requires_a_new_choice_instead_of_blind_retries():
    r=row();pending={'observed_at':1,'out_of_range':False};session={}
    pickup_intent.offer(session,r,pending,'loot',{}, {}, {})
    missed=dict(pending,tooltip_search_misses=1)
    assert pickup_intent.retained(session,r,missed) is None
    combat=copy.deepcopy(r);combat['movement']['in_combat']=True
    assert pickup_intent.retained(session,combat,pending) is None


def test_movement_and_specific_mouseover_commands_do_not_invent_collection_intents():
    r=row();pending={'observed_at':1,'out_of_range':False};session={}
    for action in ('forward_short','mouseover_interact','camera_ground'):
        pickup_intent.offer(session,r,pending,action,{}, {}, {})
    assert session=={}
