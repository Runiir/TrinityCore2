"""The private diagnostic accepts only the reviewed synthetic owned request."""
import pytest
from tools.client_compatibility.interaction_hunter_rename_capture import request
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
