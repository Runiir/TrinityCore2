"""Summon attribution must distinguish the requested cast from triggered copies."""
import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility.interaction_pet_summon import cast_identity,summon_checks,public_pet_matches
from tools.client_compatibility.world.objects import INDEX

FIXTURE=Path(__file__).parent/'fixtures/native_pet_summon_cleanup_ui121.json'


def oracle():
    data=json.loads(FIXTURE.read_text());guid=0xf14001a000000012
    fields={INDEX['UNIT_FIELD_SUMMONEDBY']:5,INDEX['UNIT_FIELD_SUMMONEDBY']+1:0,
        INDEX['UNIT_FIELD_PETNUMBER']:2}
    return SimpleNamespace(owner=5,casts=data['packets'],pet={'guid':guid,'map':0,'fields':fields},
        creations={guid:1791280937.2},present=lambda:True)


def checks(o=None,absence=True,selected='summon'):
    return summon_checks(o or oracle(),1791280930,0xf14001a000000011,{'id':2},selected,absence)[0]


def test_actual_cleanup_cast_prefixes():
    data=json.loads(FIXTURE.read_text());parsed=[cast_identity(p) for p in data['packets']]
    assert parsed[0]['spell']==688
    assert parsed[1]=={'counter':1,'spell':688,'misc':0,'flags':0,'target_flags':0}
    assert parsed[2]=={'caster':5,'unit':5,'counter':1,'spell':688}
    assert parsed[3] is None
    assert parsed[4]=={'caster':5,'unit':5,'counter':0,'spell':688}


def test_one_matching_completion_with_triggered_counter_zero():
    assert all(checks().values())


@pytest.mark.parametrize('absence',[False,None,{},0])
def test_absence_is_required(absence):
    assert checks(absence=absence)['confirmed_absence_before_input'] is False


@pytest.mark.parametrize('index,key',[(0,'one_modern_cast'),(1,'one_native_cast'),(2,'matching_native_completion')])
def test_duplicate_request_or_matching_completion_rejects(index,key):
    o=oracle();o.casts=copy.deepcopy(o.casts);o.casts.append(copy.deepcopy(o.casts[index]))
    assert checks(o)[key] is False


def test_triggered_go_does_not_replace_missing_requested_completion():
    o=oracle();o.casts=[p for i,p in enumerate(o.casts) if i!=2]
    assert checks(o)['matching_native_completion'] is False


def test_foreign_caster_does_not_complete_owned_cast():
    o=oracle();o.casts=copy.deepcopy(o.casts);o.casts[2]['body']='01060106'+o.casts[2]['body'][8:]
    assert checks(o)['matching_native_completion'] is False


def test_cast_failure_prevents_acceptance():
    o=oracle();o.casts=o.casts+[{'name':'SMSG_CAST_FAILED','direction':'from_native',
        'time':1791280937.3,'body':'01b00200000d'}]
    assert checks(o)['matching_native_completion'] is False


def test_old_creation_is_not_new_summon():
    o=oracle();o.creations[o.pet['guid']]=1791280920
    assert checks(o)['new_native_pet'] is False


@pytest.mark.parametrize('field,value',[(INDEX['UNIT_FIELD_SUMMONEDBY'],4),(INDEX['UNIT_FIELD_PETNUMBER'],1)])
def test_wrong_owner_or_saved_pet_number_rejects(field,value):
    o=oracle();o.pet['fields'][field]=value
    assert checks(o)['owned_retained_pet'] is False


def test_missing_native_link_rejects():
    o=oracle();o.present=lambda:False
    assert checks(o)['native_summon_link'] is False


def test_public_guid_name_and_presence_must_agree():
    o=oracle();public={'exists':True,'guid':'Pet-0-1-0-0-416-0000000012','name':'Yaztog'}
    assert public_pet_matches(o,public,{'name':'Yaztog'})
    for key,value in [('exists',False),('guid','Pet-0-1-0-0-416-0000000011'),('name','Volrot')]:
        changed=dict(public);changed[key]=value
        assert not public_pet_matches(o,changed,{'name':'Yaztog'})
