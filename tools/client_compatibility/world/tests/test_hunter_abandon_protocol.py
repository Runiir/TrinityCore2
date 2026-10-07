"""Source-derived Abandon ABI must never grant authority over another pet."""
from copy import deepcopy
import struct
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_hunter_rename_protocol import F,PET,CATALOG,owned
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec
from tools.client_compatibility.world.tests.test_pet_protocol import action

BODY=Writer().guid(*F['request']['decoded']['guid']).finish()
EXPECTED={'packet':['CMSG_PET_ABANDON',struct.pack('<Q',PET).hex()],'rejection':''}


def abandon(body=BODY):return action('translate_pet_abandon','CMSG_PET_ABANDON',body)


def test_pinned_packed_guid_request_preserves_native_pet_identity(codec):
    assert owned(codec,[abandon()])[-1]==EXPECTED


@pytest.mark.parametrize('body',[b'',BODY[:-1],BODY+b'x',BODY+BODY,
    Writer().guid(0,0).finish(),Writer().guid(PET,0).finish(),
    Writer().guid(F['request']['decoded']['guid'][0]+1,F['request']['decoded']['guid'][1]).finish()])
def test_foreign_truncated_or_extra_guid_body_does_not_lose_session(codec,body):
    rows=owned(codec,[abandon(body),abandon()])
    assert rows[1]['packet'] is None and rows[1]['rejection'] and rows[2]==EXPECTED


@pytest.mark.parametrize('fault',['unseen','foreign_owner','wrong_summon','no_number','wrong_kind','wrong_map',
    'warlock','no_abandon','rename_only'])
def test_current_native_hunter_permission_and_ownership_required(codec,fault):
    pet=deepcopy(F['native_pet_create']);player=deepcopy(F['native_owner_snapshot']);f=pet['fields'];p=player['fields']
    if fault=='foreign_owner':f[str(INDEX['UNIT_FIELD_SUMMONEDBY'])]=5
    elif fault=='wrong_summon':p[str(INDEX['UNIT_FIELD_SUMMON'])]=(PET+1)&0xffffffff
    elif fault=='no_number':f[str(INDEX['UNIT_FIELD_PETNUMBER'])]=0
    elif fault=='wrong_kind':pet['kind']=4
    elif fault=='wrong_map':pet['map']=1
    elif fault=='warlock':p[str(INDEX['UNIT_FIELD_BYTES_0'])]=1|(9<<8)
    elif fault=='no_abandon':f[str(INDEX['UNIT_FIELD_BYTES_2'])]=0
    elif fault=='rename_only':f[str(INDEX['UNIT_FIELD_BYTES_2'])]=1<<16
    row=owned(codec,[abandon()],pet=pet,player=player,units=[] if fault=='unseen' else None)[-1]
    assert row['packet'] is None and row['rejection']


def test_renamed_hunter_pet_can_abandon_without_rename_permission(codec):
    pet=deepcopy(F['native_pet_create']);pet['fields'][str(INDEX['UNIT_FIELD_BYTES_2'])]=2<<16
    assert owned(codec,[abandon()],pet=pet)[-1]==EXPECTED


def test_catalog_release_and_native_clear_control_authority(codec):
    rows=owned(codec,[abandon(),action('pet_response','SMSG_PET_SPELLS',CATALOG),abandon(),
        action('pet_response','SMSG_PET_SPELLS',struct.pack('<Q',0)),abandon()],catalog=None)
    assert rows[0]['packet'] is None and rows[2]==EXPECTED and rows[-1]['packet'] is None
