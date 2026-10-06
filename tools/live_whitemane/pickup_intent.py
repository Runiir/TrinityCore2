"""Retain Laya's collection intent through the same find's range correction."""


def retained(session,row,pending):
    intent=session.get('accepted_pickup_intent')
    if not pending:
        session.pop('accepted_pickup_intent',None);return None
    if (not intent or intent['runtime']!=row['runtime']
            or intent['find_observed_at']!=pending['observed_at']
            or pending.get('out_of_range') or row['archaeology']['casting']
            or row['movement']['in_combat']
            or pending.get('tooltip_search_misses',0)>intent['tooltip_search_misses']):
        return None
    return intent['action'],intent['model'],intent['request'],{
        **intent['response'],'model_decision_reused':True,
        'selection_method':'retained_Laya_collection_for_same_uncollected_find'}


def offer(session,row,pending,action,model,request,response):
    if action!='loot' or not pending:return
    session['accepted_pickup_intent']={'runtime':row['runtime'],
        'find_observed_at':pending['observed_at'],'action':action,'model':model,
        'request':request,'response':response,
        'tooltip_search_misses':pending.get('tooltip_search_misses',0)}
