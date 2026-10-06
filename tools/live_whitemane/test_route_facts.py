from . import route_facts,farm_policy
from .dig_policy import SolveBatches
from .test_farm_loop import row


def mossy():
    r=row();r['archaeology']['falling']=False
    portal={'key':'org-uldum','destination':'Ramkahen','from':r['archaeology']['world'],
        'to':{'instance':1,'north':-9444,'west':-959}}
    r['farm_ui']['flyable']=True
    r['farm_ui']['route']={'kind':'taxi','origin':{'id':23,'master_name':'Doras','name':'Orgrimmar',
        'point':{'instance':1,'north':400,'west':0}},'exit':{'id':386,'name':'Mossy Pile'},
        'fare_copper':1241,'known_portals':[portal],'fare_options':[{'origin_id':652,
            'origin_name':'Ramkahen','origin_point':{'instance':1,'north':-9417,'west':-1039},
            'exit_id':386,'fare_copper':20830,'fare_source':'observed public flight menu'}]}
    return r


def test_comparable_fares_explain_the_current_leg_without_removing_a_legal_portal():
    r=mossy();options=farm_policy.legal_actions(r,SolveBatches())
    facts,choices=route_facts.describe(r['farm_ui']['route'],options)
    assert set(choices)==set(options)
    assert {'flight','portal_org-uldum','flight_portal_org-uldum'}<=choices.keys()
    assert facts['actions']['flight']['follows_addon_next_leg']
    assert facts['actions']['portal_org-uldum']['more_expensive_than_addon_route']
    assert 'Doras' in choices['flight'][0] and '1241 copper' in choices['flight'][0]
    assert '20830 copper' in choices['portal_org-uldum'][0] and '1241' in choices['portal_org-uldum'][0]
    assert all(choices[k][1]==options[k][1] for k in options)


def test_unknown_or_different_destination_fares_are_not_used_as_price_evidence():
    r=mossy();r['farm_ui']['route']['fare_options'][0]['exit_id']=531
    facts,_=route_facts.describe(r['farm_ui']['route'],farm_policy.legal_actions(r,SolveBatches()))
    assert 'fare_copper' not in facts['actions']['portal_org-uldum']
    r['farm_ui']['route']['fare_options'][0]['exit_id']=386
    r['farm_ui']['route'].pop('fare_copper')
    facts,_=route_facts.describe(r['farm_ui']['route'],farm_policy.legal_actions(r,SolveBatches()))
    assert not facts['actions']['portal_org-uldum']['more_expensive_than_addon_route']


def test_full_farm_state_keeps_the_next_leg_and_all_legal_actions_for_laya(monkeypatch):
    r=mossy();seen=[]
    def choose(state,instructions,options):
        seen.append(state)
        assert state['task']=='Reach flight master Doras and fly to Mossy Pile'
        assert state['addon_next_leg']['actions']['portal_org-uldum']['fare_copper']==20830
        assert {'flight','portal_org-uldum'}<=options.keys()
        return 'flight',{},{}
    monkeypatch.setattr(farm_policy.laya_ui,'choose',choose)
    result=farm_policy.choose(r,SolveBatches(),{'via_tolbarad':True})
    assert result[0]=='flight' and len(seen)==1
