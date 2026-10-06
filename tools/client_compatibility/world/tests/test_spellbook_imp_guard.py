"""Reject unknown, hidden or ambiguous Imp controls before any input."""
import copy
import pytest
from tools.client_compatibility.interaction_spellbook_pet_probe import observed_imp


def probe():
    return {'flyout':{'visible':True,'parent':'SpellButton1','buttons':[
        {'id':688,'button':'SpellFlyoutButton1','name':'Summon Imp','known':True,
         'enabled':True,'point':[8191,14836]}]}}


def test_imp_guard_uses_one_exact_observed_trained_native_spell():
    row,control=observed_imp(probe(),{688})
    assert row['id']==688 and control=={'name':'SpellFlyoutButton1','x':8191,'y':14836}


@pytest.mark.parametrize('mutation',['unknown','hidden','duplicate','disabled','untrained','wrong_id','wrong_name',
    'wrong_button','wrong_parent','missing_point','outside_point'])
def test_imp_guard_rejects_each_unbound_control(mutation):
    value=copy.deepcopy(probe());flyout=value['flyout'];row=flyout['buttons'][0];known={688}
    if mutation=='unknown':known=set()
    elif mutation=='hidden':flyout['visible']=False
    elif mutation=='duplicate':flyout['buttons'].append(copy.deepcopy(row))
    elif mutation=='disabled':row['enabled']=False
    elif mutation=='untrained':row['known']=False
    elif mutation=='wrong_id':row['id']=697
    elif mutation=='wrong_name':row['name']='Summon Voidwalker'
    elif mutation=='wrong_button':row['button']='SpellButton1'
    elif mutation=='wrong_parent':flyout['parent']='ActionButton1'
    elif mutation=='missing_point':row.pop('point')
    elif mutation=='outside_point':row['point']=[65535,0]
    with pytest.raises(RuntimeError):observed_imp(value,known)
