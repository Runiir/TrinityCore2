"""Stock control targets require typed public agreement, including native CVars."""
import pytest
from tools.client_compatibility.interaction_settings_controls import agrees


@pytest.mark.parametrize('wanted',[False,True])
def test_move_pad_requires_public_setting_and_cvar_agreement(wanted):
    probe={'values':{'enableMovePad':wanted},'cvars':{'enableMovePad':str(int(wanted))}}
    assert agrees(probe,'enableMovePad',wanted)
    probe['cvars']['enableMovePad']=str(int(not wanted))
    assert not agrees(probe,'enableMovePad',wanted)


def test_move_pad_cannot_pass_without_its_cvar():
    assert not agrees({'values':{'enableMovePad':True},'cvars':{}},'enableMovePad',True)


@pytest.mark.parametrize('actual',[1,'1',None])
def test_proxy_setting_does_not_accept_an_untyped_truthy_value(actual):
    assert not agrees({'values':{'PROXY_ENABLE_INTERACT':actual}},'PROXY_ENABLE_INTERACT',True)


@pytest.mark.parametrize('wanted',[False,True])
def test_proxy_setting_uses_its_registered_public_boolean(wanted):
    assert agrees({'values':{'PROXY_ENABLE_INTERACT':wanted}},'PROXY_ENABLE_INTERACT',wanted)
    assert not agrees({'values':{'PROXY_ENABLE_INTERACT':not wanted}},'PROXY_ENABLE_INTERACT',wanted)


@pytest.mark.parametrize('wanted',[0,1])
def test_non_boolean_requested_targets_are_rejected(wanted):
    with pytest.raises(ValueError,match='boolean'):agrees({},'enableMovePad',wanted)
