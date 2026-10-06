"""The private diagnostic accepts only the reviewed synthetic owned request."""
from copy import deepcopy
import pytest
from tools.client_compatibility.interaction_hunter_rename_capture import request,dialog_matches,CONFIRM
from tools.client_compatibility.interaction_pet_command_probe import expected_guid
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid

PET={'guid':(0xf14<<52)|(42717<<32)|77,'map':0}


def body(name='Harnesswolf',number=4,guid=None,declined=0,padding=0):
    return (Writer().guid(*(guid or modern_guid(PET['guid'],0))).pack('i',number)
        .bits(len(name),8).bits(declined,1).bits(padding,7).raw(name.encode()).finish())


def test_exact_private_capture_decodes_owned_identity_and_synthetic_name():
    assert request({'body':body().hex()},PET)=={'guid':list(modern_guid(PET['guid'],0)),
        'pet_number':4,'name':'Harnesswolf','declined_names':False}


@pytest.mark.parametrize('data',[
    body(name='Privatewolf'),body(number=2),body(guid=(1,2)),body(declined=1),body(padding=1),
    body()+b'extra',body()[:-1],b'',body(name='Harnesswol'),
])
def test_foreign_ambiguous_or_incomplete_capture_is_rejected(data):
    with pytest.raises((RuntimeError,ValueError)):
        request({'body':data.hex()},PET)


@pytest.mark.parametrize('fault',('none','entry_dialog','wrong_pet','wrong_name','disabled_yes','edit_present',
    'wrong_button','duplicate_yes','lua_error','blocked_action'))
def test_submission_requires_the_second_exact_owned_confirmation(fault):
    state={'panels':['StaticPopup2'],'target':{'guid':expected_guid(PET)},'edit_fields':[]}
    rows=[{'name':'StaticPopup2Button'+str(i),'text':label,'context':CONFIRM,'enabled':True}
        for i,label in enumerate(('Yes','No'),1)]
    if fault=='entry_dialog':state['panels']=['StaticPopup1']
    elif fault=='wrong_pet':state['target']['guid']='foreign'
    elif fault=='wrong_name':rows[0]['context']="Name your pet 'Otherwolf'?"
    elif fault=='disabled_yes':rows[0]['enabled']=False
    elif fault=='edit_present':state['edit_fields']=[{'text':'Harnesswolf'}]
    elif fault=='wrong_button':rows[0]['name']='StaticPopup1Button1'
    elif fault=='duplicate_yes':rows.append(deepcopy(rows[0]))
    elif fault=='lua_error':state['lua_errors']=['error']
    elif fault=='blocked_action':state['blocked_actions']=['blocked']
    assert dialog_matches(state,rows,'hunter_rename_confirmation_open',PET)==(fault=='none')
