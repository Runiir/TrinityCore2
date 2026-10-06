"""A recreated public pet must match the saved pet, with a fresh runtime GUID."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility.interaction_pet_persistence import checks
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility import interaction_pet_persistence as module


@pytest.mark.parametrize('change',('none','old_counter','pet_number','entry','owner','summon','public_guid','public_absent',
    'native_missing','saved_name','public_name','saved_owner','saved_id'))
def test_saved_pet_persistence_cannot_be_supplied_by_stale_or_foreign_pet(change):
    guid=0xf14001a000000007;owner=4
    fields={INDEX['UNIT_FIELD_PETNUMBER']:1,INDEX['UNIT_FIELD_SUMMONEDBY']:owner,INDEX['UNIT_FIELD_SUMMONEDBY']+1:0}
    pet={'guid':guid,'map':0,'fields':fields}
    player={INDEX['UNIT_FIELD_SUMMON']:guid&0xffffffff,INDEX['UNIT_FIELD_SUMMON']+1:guid>>32}
    oracle=SimpleNamespace(pet=pet,player=player,owner=owner)
    previous={'guid':guid-1,'name':'Volrot'}
    retained={'id':1,'entry':416,'owner':owner,'name':'Volrot'}
    public={'exists':True,'guid':'Pet-0-1-0-0-416-0000000007','name':'Volrot'}
    if change=='old_counter':previous['guid']=guid
    elif change=='pet_number':fields[INDEX['UNIT_FIELD_PETNUMBER']]=2
    elif change=='entry':pet['guid']+=1<<32
    elif change=='owner':fields[INDEX['UNIT_FIELD_SUMMONEDBY']]=5
    elif change=='summon':player[INDEX['UNIT_FIELD_SUMMON']]+=1
    elif change=='public_guid':public['guid']='Pet-0-1-0-0-416-0000000006'
    elif change=='public_absent':public['exists']=False
    elif change=='native_missing':oracle.pet=None
    elif change=='saved_name':retained['name']='Different'
    elif change=='public_name':public['name']='Different'
    elif change=='saved_owner':retained['owner']=5
    elif change=='saved_id':retained['id']=2
    assert all(checks(previous,retained,oracle,public).values())==(change=='none')


@pytest.mark.parametrize('change',('none','empty_preparation_checks','park_runtime','finish_missing','old_failed',
    'old_restoration_false','power_check_renamed','wrong_owner','wrong_number','wrong_public_guid','source_hash','old_entry_hash','overlap'))
def test_persistence_requires_closed_whole_trial_and_exact_logout_reentry_chain(tmp_path,monkeypatch,change):
    origin={'guid':2,'account_id':2};actor={'guid':4,'account_id':2};runtime={'client':{'pid':3}}
    paths=[tmp_path/n/'episode.json' for n in ('prior','park','finish','power','old-entry')]
    prior={'actor':origin,'origin_actor':origin,'class_actor':actor,'runtime':runtime,
        'phase':'await_owned_class_lobby_review','finished_at':1}
    keys=('original_character','original_saved_rows','native_worldserver','class_offline')
    retained=[{'id':1,'entry':416,'owner':4,'name':'Volrot'}]
    park={'actor':actor,'runtime':runtime,'fixture_source':{'sha256':'prior'},'phase':'await_original_selection_review',
        'checks':dict.fromkeys(keys,True),'retained_class_pets':retained,'started_at':3,'finished_at':4}
    finish={'actor':origin,'runtime':runtime,'fixture_source':{'sha256':'prior'},
        'checks':{**park['checks'],'origin_registration':True},'started_at':5,'finished_at':6}
    prep={'origin_actor':origin,'sources':[{'path':str(p),'sha256':p.parent.name} for p in paths[:3]],
        'checks':dict.fromkeys((*keys,'retained_character','retained_saved_rows','retained_pets','origin_registration'),True),
        'retained_class_pets':retained,'started_at':7}
    power={'actor':actor,'runtime':runtime,'phase':'owned_pet_target_health_power_complete','finished_at':2,
        'fixture_source':{'sha256':'prior'},'sources':[{'path':str(paths[4]),'sha256':'old-entry'}],
        'restoration_checks':dict.fromkeys(('original_character','original_saved_rows','native_worldserver','empty_selection',
            'resources','saved_rows','position','panels_closed','ui_clean'),True),
        'cases':[{'id':'pets.pet_power','status':'native_owned_pet_power_pass','oracle':{'checks':dict.fromkeys(
            ('native_target','owned_pet','public_target','public_pet','mana_type','power','visible_target','ui_clean','detail_ui_clean'),True)}}],
        'native_pet':{'guid':0xf14001a000000006,'map':0,'fields':{str(INDEX['UNIT_FIELD_PETNUMBER']):1,
            str(INDEX['UNIT_FIELD_SUMMONEDBY']):4}},'public_pet':{'guid':'Pet-0-1-0-0-416-0000000006'},'native_session':'session'}
    if change=='empty_preparation_checks':prep['checks']={}
    elif change=='park_runtime':park['runtime']={'client':{'pid':9}}
    elif change=='finish_missing':finish['checks'].pop('origin_registration')
    elif change=='old_failed':power['phase']='failed'
    elif change=='old_restoration_false':power['restoration_checks']['resources']=False
    elif change=='power_check_renamed':power['cases'][0]['oracle']['checks']['other']=power['cases'][0]['oracle']['checks'].pop('power')
    elif change=='wrong_owner':power['native_pet']['fields'][str(INDEX['UNIT_FIELD_SUMMONEDBY'])]=5
    elif change=='wrong_number':power['native_pet']['fields'][str(INDEX['UNIT_FIELD_PETNUMBER'])]=2
    elif change=='wrong_public_guid':power['public_pet']['guid']='old'
    elif change=='source_hash':prep['sources'][1]['sha256']='wrong'
    elif change=='old_entry_hash':power['sources'][0]['sha256']='wrong'
    elif change=='overlap':prep['started_at']=4
    rows=dict(zip(paths[:4],(prior,park,finish,power)))
    monkeypatch.setattr(module,'closed',lambda p:rows[p])
    monkeypatch.setattr(module.lab,'sha256',lambda p:p.parent.name)
    calls=[];monkeypatch.setattr(module,'entry_source',lambda *a:calls.append(a[1]))
    t=SimpleNamespace(fixture=actor,receipt={'runtime':runtime})
    if change=='none':assert module.previous_source(t,prep,paths[3])==power and calls==[paths[4]]
    else:
        with pytest.raises(RuntimeError):module.previous_source(t,prep,paths[3])
        assert calls==[]
