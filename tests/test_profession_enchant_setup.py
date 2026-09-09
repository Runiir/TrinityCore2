import copy
import json
from pathlib import Path

from tools.bot_ml import build_validation_provisioning as provisioning
from tools.bot_ml.phase8_fixture_contract import materialize_fixture_contract

ROOT = Path(__file__).resolve().parents[1]
SETUP = {'requirements': [{'source_enchant_ids': [4115], 'native_skill_id': 197,
    'required_rank': 500, 'provisioned_value': 525, 'provisioned_max': 525,
    'wowsims_profession': 'Tailoring'}],
    'wowsims_professions': ['Tailoring', 'ProfessionUnknown']}
SECONDARY = [{'id': 129, 'value': 525, 'max': 525}, {'id': 185, 'value': 525, 'max': 525}, {'id': 762, 'value': 300, 'max': 300}]


def test_provisioning_adds_equipped_enchant_profession():
    config = {'default_skills': SECONDARY, 'scenarios': [{'bots': [{'name': 'Elemental', 'gear_profile_id': 'elemental'}]}]}
    profiles = {'elemental': {'equipment': [{'slot': 14, 'item_id': 77096, 'enchant_id': 4115}]}}
    bot = provisioning.apply_gear_profiles(config, profiles)['scenarios'][0]['bots'][0]
    assert bot.get('skills') == SECONDARY + [{'id': 197, 'value': 525, 'max': 525}]


def test_materialized_request_carries_required_profession(tmp_path):
    catalog = json.loads((ROOT / 'experiments/configs/all_spec_targets_cata_p4_v1.json').read_text())
    rows = catalog['targets']
    for row in rows:
        if row['spec_target_id'] == 'elemental_shaman':
            row['provisioning_bot']['profession_setup'] = copy.deepcopy(SETUP)
            row['provisioning_bot']['profession_equipment'] = [{'id': 77096, 'enchant': 4115}]
    path = tmp_path / 'targets.json'
    path.write_text(json.dumps(catalog))
    raw = json.loads((ROOT / 'experiments/configs/phase8_calibration_fixture_contract_v1.json').read_text())
    result = materialize_fixture_contract(raw, target_catalog_path=path)
    assert result['specs']['elemental_shaman']['native_request']['professions'] == SETUP['wowsims_professions']

import pytest
from tools.bot_ml.wowsims_gear_binding import resolve_profession_setup, merge_profession_skills, provisioning_professions


@pytest.mark.parametrize('item,enchant,professions', [(77098,4115,SETUP['wowsims_professions']), (77096,4115,SETUP['wowsims_professions']), (77097,0,['ProfessionUnknown']*2)])
def test_real_dbc_permanent_enchant_projection(item,enchant,professions):
    result = resolve_profession_setup([{'id': item, 'enchant': enchant}])
    assert result['wowsims_professions'] == professions
    assert result['requirements'] == (SETUP['requirements'] if enchant else [])


@pytest.mark.parametrize('equipment,rows,message', [
    ([{'enchant': 1}], {1:(999,500)}, 'unknown required'),
    ([{'enchant': n} for n in [1,2,3]], {1:(197,500),2:(164,500),3:(202,500)}, 'more than two'),
    ([{'enchant': 1}], {1:(197,526)}, 'exceeds'),
    ([{'enchant': 1}], {}, 'unknown permanent'),
])
def test_invalid_dbc_requirement_fails(equipment,rows,message):
    with pytest.raises(ValueError, match=message):
        resolve_profession_setup(equipment,enchant_rows=rows)


@pytest.mark.parametrize('skills', [[{'id':197,'value':499,'max':525}], [{'id':197,'value':525,'max':499}], [{'id':197},{'id':197}]])
def test_conflicting_or_insufficient_skills_fail(skills):
    with pytest.raises(ValueError):
        merge_profession_skills(skills,SETUP)


def test_declared_profession_drift_fails():
    with pytest.raises(ValueError,match='metadata'):
        resolve_profession_setup([{'enchant':0}],declared=SETUP)
    with pytest.raises(ValueError,match='missing equipped'):
        provisioning_professions({'profession_setup':SETUP})


def test_real_diagnostic_provisioning_sql_keeps_secondaries_and_only_required_tailoring():
    config = provisioning.load_config_with_bwd_diagnostic_shards(
        ROOT/'experiments/configs/validation_provisioning_cata_001.json',
        ROOT/'experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json')
    profiles = provisioning.load_gear_profiles(ROOT/'dataset/validation_gear_profiles/profiles.json')
    result = provisioning.apply_gear_profiles(config,profiles)
    scenario = next(row for row in result['scenarios'] if 'magmaw' in row['id'])
    sql = provisioning.build_character_insert_sql({**result,'scenarios':[scenario]})
    dps = [bot for bot in scenario['bots'] if bot['class_spec'] in ['fire_mage','affliction_warlock','elemental_shaman','marksmanship_hunter']]
    assert len(dps) == 5
    for bot in dps:
        skills = {row['id']:row for row in bot['skills']}
        assert all(skills[row['id']] == row for row in SECONDARY)
        tailoring_lines = [line for line in sql.splitlines() if 'SELECT c.`guid`, 197, 525, 525' in line and "= '"+bot['name']+"'" in line]
        assert len(tailoring_lines) == (0 if bot['class_spec']=='marksmanship_hunter' else 1)


def test_runeforging_remains_class_skill_not_primary_profession():
    assert resolve_profession_setup([{'enchant':3368}]) == {'requirements': [], 'wowsims_professions':['ProfessionUnknown']*2}
    assert merge_profession_skills([{'id':776,'value':1,'max':1}], resolve_profession_setup([{'enchant':3368}])) == [{'id':776,'value':1,'max':1}]


def test_materialization_to_native_raid_request_all_four_specs(tmp_path):
    from tools.bot_ml.run_wowsims_exact_references import build_native_raid_sim_request
    catalog = json.loads((ROOT/'experiments/configs/all_spec_targets_cata_p4_v1.json').read_text())
    profiles = json.loads((ROOT/'experiments/configs/wowsims_cata_p4_gear_profiles.json').read_text())['profiles']
    selected = ['fire_mage','affliction_warlock','elemental_shaman','marksmanship_hunter']
    for row in catalog['targets']:
        if row['spec_target_id'] in selected:
            equipment = profiles[row['gear_profile_id']]['items']
            row['provisioning_bot']['profession_equipment'] = equipment
            row['provisioning_bot']['profession_setup'] = resolve_profession_setup(equipment)
    path = tmp_path/'targets.json'
    path.write_text(json.dumps(catalog))
    raw = json.loads((ROOT/'experiments/configs/phase8_calibration_fixture_contract_v1.json').read_text())
    contract = materialize_fixture_contract(raw,target_catalog_path=path)
    expected_professions = {
        'fire_mage': 'Tailoring',
        'affliction_warlock': 'Tailoring',
        'elemental_shaman': 'Tailoring',
        'marksmanship_hunter': 'Blacksmithing',
    }
    for spec in selected:
        native = build_native_raid_sim_request(target_spec=spec, request={},
            native_contract=contract['specs'][spec]['native_request'], class_name='ClassShaman',race_name='RaceDraenei',
            equipment_items=[],talents_string='',glyphs={},rotation={})
        player = native['raid']['parties'][0]['players'][0]
        assert player['profession1'] == expected_professions[spec]
        assert player['profession2'] == 'ProfessionUnknown'


def test_direct_profile_loader_and_inline_equipment_apply_same_setup():
    profiles = provisioning.load_gear_profiles(ROOT/'experiments/configs/wowsims_cata_p4_gear_profiles.json')
    profile = profiles['elemental_shaman']
    assert any(item['enchant_id']==4115 for item in profile['equipment'])
    bot = {'name':'Inline','equipment':profile['equipment']}
    config = {'default_skills':SECONDARY,'scenarios':[{'bots':[bot]}]}
    result = provisioning.apply_gear_profiles(config,{})['scenarios'][0]['bots'][0]
    assert result['skills'] == SECONDARY + [{'id':197,'value':525,'max':525}]


def test_third_primary_profession_and_serialized_low_skill_rejected():
    with pytest.raises(ValueError,match="more than two"):
        merge_profession_skills([{'id':171},{'id':202}],SETUP)
    with pytest.raises(ValueError,match='below required'):
        provisioning_professions({'profession_setup':SETUP,'profession_equipment':[{'enchant':4115}], 'skills':[{'id':197,'value':499}]})


@pytest.mark.parametrize('enchant,configured,expected', [
    (0,[171,202],['Alchemy','Engineering']),
    (4115,[171],['Alchemy','Tailoring']),
    (4115,[202],['Tailoring','Engineering']),
    (0,[171],['Alchemy','ProfessionUnknown']),
])
def test_pipeline_preserves_explicit_primary_professions(tmp_path,enchant,configured,expected):
    skills = SECONDARY + [{'id':skill,'value':525,'max':525} for skill in configured]
    bot = {'name':'Elemental','gear_profile_id':'elemental','skills':skills}
    equipment = [{'slot':14,'item_id':77096,'enchant_id':enchant}]
    config = {'scenarios':[{'bots':[bot]}]}
    resolved = provisioning.apply_gear_profiles(config,{'elemental':{'equipment':equipment}})['scenarios'][0]['bots'][0]
    assert resolved['skills'][:len(skills)] == skills
    assert resolved['profession_setup']['wowsims_professions'] == expected
    catalog = json.loads((ROOT/'experiments/configs/all_spec_targets_cata_p4_v1.json').read_text())
    target = next(row for row in catalog['targets'] if row['spec_target_id']=='elemental_shaman')
    for key in ['skills','profession_setup','profession_equipment']:
        target['provisioning_bot'][key] = resolved[key]
    path = tmp_path/'targets.json'
    path.write_text(json.dumps(catalog))
    raw = json.loads((ROOT/'experiments/configs/phase8_calibration_fixture_contract_v1.json').read_text())
    result = materialize_fixture_contract(raw,target_catalog_path=path)
    assert result['specs']['elemental_shaman']['native_request']['professions'] == expected
    from tools.bot_ml.run_wowsims_exact_references import build_native_raid_sim_request
    native = build_native_raid_sim_request(target_spec='elemental_shaman', request={},
        native_contract=result['specs']['elemental_shaman']['native_request'],
        class_name='ClassShaman',race_name='RaceDraenei',equipment_items=[],
        talents_string='',glyphs={},rotation={})
    player = native['raid']['parties'][0]['players'][0]
    assert [player['profession1'],player['profession2']] == expected
    sql = provisioning.build_character_insert_sql({'scenarios':[{
        'id':'combat_calibration','start_position':{'map_id':0,'x':1,'y':2,'z':3},
        'bots':[target['provisioning_bot']]}]})
    for skill in configured + ([197] if enchant else []):
        assert f"SELECT c.`guid`, {skill}, 525, 525" in sql


def test_profession_only_cli_preserves_catalog_identity_and_explicit_choices(tmp_path,monkeypatch):
    from tools.bot_ml import build_all_spec_phase1_catalogs as catalogs
    target = json.loads(catalogs.TARGET_CATALOG_PATH.read_text())
    reference = json.loads(catalogs.REFERENCE_CATALOG_PATH.read_text())
    for row in target['targets']:
        row['provisioning_bot'].pop('profession_setup',None)
        row['provisioning_bot'].pop('profession_equipment',None)
    for row in reference['references']:
        row['gear'].pop('profession_setup',None)
    gear = json.loads(catalogs.WOWSIMS_GEAR_PROFILES_PATH.read_text())
    elemental = next(row for row in target['targets'] if row['spec_target_id']=='elemental_shaman')
    elemental['provisioning_bot']['skills'] = SECONDARY + [{'id':202,'value':525,'max':525}]
    for constant,document in [('TARGET_CATALOG_PATH',target),('REFERENCE_CATALOG_PATH',reference),('WOWSIMS_GEAR_PROFILES_PATH',gear)]:
        path = tmp_path/(constant+'.json')
        path.write_text(json.dumps(document))
        monkeypatch.setattr(catalogs,constant,path)
    monkeypatch.setattr(catalogs,'fetch_bytes',lambda *_: pytest.fail('profession reconciliation fetched research'))
    monkeypatch.setattr(catalogs,'write_bundle',lambda *_: pytest.fail('profession reconciliation wrote bundle'))
    monkeypatch.setattr('sys.argv',['catalogs','--reconcile-professions'])
    assert catalogs.main()==0
    actual_target = json.loads(catalogs.TARGET_CATALOG_PATH.read_text())
    actual_reference = json.loads(catalogs.REFERENCE_CATALOG_PATH.read_text())
    for before,after in zip(target['targets'],actual_target['targets']):
        profile_id = before['gear_profile_id']
        if profile_id in gear['profiles']:
            bot = after['provisioning_bot']
            expected = resolve_profession_setup(gear['profiles'][profile_id]['items'],configured_skills=before['provisioning_bot'].get('skills',[]))
            assert bot.pop('profession_setup')==expected
            assert bot.pop('profession_equipment')==gear['profiles'][profile_id]['items']
    for before,after in zip(reference['references'],actual_reference['references']):
        if after['gear']['gear_profile_id'] in gear['profiles']:
            assert after['gear'].pop('profession_setup')==resolve_profession_setup(gear['profiles'][after['gear']['gear_profile_id']]['items'])
    assert actual_target==target
    assert actual_reference==reference
    updated = json.loads(catalogs.TARGET_CATALOG_PATH.read_text())
    bot = next(row['provisioning_bot'] for row in updated['targets'] if row['spec_target_id']=='elemental_shaman')
    assert bot['profession_setup']['wowsims_professions']==['Tailoring','Engineering']
    before_bytes = [path.read_bytes() for path in [catalogs.TARGET_CATALOG_PATH,catalogs.REFERENCE_CATALOG_PATH]]
    assert catalogs.main()==0
    assert before_bytes==[path.read_bytes() for path in [catalogs.TARGET_CATALOG_PATH,catalogs.REFERENCE_CATALOG_PATH]]


def test_profession_only_profile_cli_preserves_exact_local_gear(tmp_path,monkeypatch):
    from tools.bot_ml import sync_wowsims_dps_gear_profiles as sync
    original = json.loads(sync.PROFILES_PATH.read_text())
    for profile in original['profiles'].values():
        profile.pop('profession_setup',None)
    path = tmp_path/'profiles.json'
    path.write_text(json.dumps(original))
    monkeypatch.setattr(sync,'PROFILES_PATH',path)
    monkeypatch.setattr(sync.urllib.request,'urlopen',lambda *_args,**_kwargs: pytest.fail('profile reconciliation fetched source'))
    monkeypatch.setattr('sys.argv',['sync','--reconcile-professions'])
    assert sync.main()==0
    actual = json.loads(path.read_text())
    for name,profile in actual['profiles'].items():
        assert profile.pop('profession_setup')==resolve_profession_setup(original['profiles'][name]['items'])
    assert actual==original
    first_bytes = path.read_bytes()
    assert sync.main()==0
    assert path.read_bytes()==first_bytes


def test_profession_reconciliation_rejects_drift_before_writing(tmp_path,monkeypatch):
    from tools.bot_ml import sync_wowsims_dps_gear_profiles as sync
    original = json.loads(sync.PROFILES_PATH.read_text())
    next(iter(original['profiles'].values()))['transformed_manifest_sha256']='stale'
    path = tmp_path/'profiles.json'
    path.write_text(json.dumps(original))
    before = path.read_bytes()
    monkeypatch.setattr(sync,'PROFILES_PATH',path)
    with pytest.raises(ValueError,match='manifest mismatch'):
        sync.reconcile_checked_in_professions()
    assert path.read_bytes()==before


def test_profession_names_belong_to_pinned_proto_enum():
    # Exact enum snapshot from wowsims/cata commit
    # 70d87383a9b92f30fb9e370c4676d3ce33b6e6b6, proto/common.proto:132.
    # This independent wire-contract fixture must not be derived from our map.
    import re
    from tools.bot_ml.wowsims_gear_binding import PRIMARY_PROFESSIONS
    enum_source = 'enum Profession {\n\tProfessionUnknown = 0;\n\tAlchemy = 1;\n\tBlacksmithing = 2;\n\tEnchanting = 3;\n\tEngineering = 4;\n\tHerbalism = 5;\n\tInscription = 6;\n\tJewelcrafting = 7;\n\tLeatherworking = 8;\n\tMining = 9;\n\tSkinning = 10;\n\tTailoring = 11;\n\tArcheology = 12;\n}'
    names = set(re.findall(r"^\s*(\w+)\s*=\s*\d+;", enum_source, re.MULTILINE))
    assert set(PRIMARY_PROFESSIONS.values()) <= names
    assert 'ProfessionUnknown' in names
    assert PRIMARY_PROFESSIONS[197] == 'Tailoring'


DPS011_ITEMS = {
    'arms_warrior': (78373, 78668), 'fury_warrior': (78373, 78668),
    'retribution_paladin': (78373, 78675), 'frost_death_knight': (78373, 78670),
    'unholy_death_knight': (78373, 78670), 'marksmanship_hunter': (78430, 78362),
    'survival_hunter': (78430, 78362), 'assassination_rogue': (78446, 78679),
    'combat_rogue': (78446, 78679),
}


def dps011_corrected_documents(tmp_path):
    """Temporary proposed inputs only; never rewrite promoted reference identity."""
    catalog = json.loads((ROOT/'experiments/configs/all_spec_targets_cata_p4_v1.json').read_text())
    gear = json.loads((ROOT/'experiments/configs/wowsims_cata_p4_gear_profiles.json').read_text())
    for profile in gear['profiles'].values():
        profile['profession_setup'] = resolve_profession_setup(profile['items'])
    for target in catalog['targets']:
        bot = target['provisioning_bot']
        if 'profession_equipment' in bot:
            bot['profession_setup'] = resolve_profession_setup(bot['profession_equipment'])
    paths = (tmp_path/'targets.json', tmp_path/'wowsims_cata_p4_gear_profiles.json')
    for path, value in zip(paths, (catalog, gear)):
        path.write_text(json.dumps(value))
    (tmp_path/'cata_434_action_profiles.json').write_bytes(
        (ROOT/'experiments/configs/cata_434_action_profiles.json').read_bytes())
    return paths, catalog, gear


def test_dps011_exact_nine_spec_eighteen_item_closure_and_rank_authority():
    from tools.bot_ml.wowsims_gear_binding import resolve_prismatic_socket, native_socket_authority
    targets = json.loads((ROOT/'experiments/configs/all_spec_targets_cata_p4_v1.json').read_text())['targets']
    affected = {}
    for target in targets:
        equipment = target['provisioning_bot'].get('profession_equipment', [])
        sockets = [value for item in equipment
                   if (value := resolve_prismatic_socket(item)) and value['slot'] in (8, 9)]
        if not sockets:
            continue
        affected[target['spec_target_id']] = tuple(row['item_id'] for row in sorted(sockets, key=lambda row: row['slot']))
        assert [(row['slot'], row['creator_enchant_id'], row['creator_spell_id']) for row in sockets] == [
            (8, 3717, 55628), (9, 3723, 55641)]
        assert all(row['required_rank'] == 400 and row['native_applicability_rank'] == 1 for row in sockets)
        setup = resolve_profession_setup(equipment)
        row = next(row for row in setup['requirements'] if row['native_skill_id'] == 164)
        assert (row['required_rank'], row['provisioned_value'], row['provisioned_max']) == (400, 525, 525)
        assert row['source_enchant_ids'] == [3717, 3723]
        assert 'Blacksmithing' in setup['wowsims_professions']
    assert affected == DPS011_ITEMS
    sources = native_socket_authority()['sources']
    assert any(path.endswith('089_npc_trainer.sql') for path in sources)
    assert all(len(digest) == 64 for digest in sources.values())


@pytest.mark.parametrize('mutation', [
    lambda item: item.update(slot=5),
    lambda item: item.update(gem_item_ids=[71879, 71879, 71879], gem_enchant_ids=[4329]*3),
    lambda item: item.update(gem_item_ids=[71879, 999999]),
    lambda item: item.update(gem_enchant_ids=[4329, 1]),
    lambda item: item.update(prismatic_enchant_id=3723),
    lambda item: item.update(gem_item_ids=[71879], gem_enchant_ids=[4329], prismatic_enchant_id=3717),
])
def test_dps011_resolver_rejects_topology_mapping_and_creator_drift(mutation):
    from tools.bot_ml.wowsims_gear_binding import resolve_prismatic_socket
    item = {'slot': 8, 'item_id': 78430, 'gem_item_ids': [71879, 71879], 'gem_enchant_ids': [4329, 4329]}
    mutation(item)
    with pytest.raises(ValueError):
        resolve_prismatic_socket(item)


def test_dps011_fresh_provisioning_sql_uses_creator_payloads_and_blacksmithing(tmp_path):
    paths, targets, _ = dps011_corrected_documents(tmp_path)
    target = next(row for row in targets['targets'] if row['spec_target_id'] == 'marksmanship_hunter')
    config = {'scenarios': [{'id': 'socket_fixture',
        'start_position': {'map_id': 0, 'x': 1, 'y': 2, 'z': 3},
        'bots': [target['provisioning_bot']]}]}
    equipped = provisioning.apply_gear_profiles(config, provisioning.load_gear_profiles(paths[1]))
    bot = equipped['scenarios'][0]['bots'][0]
    sql = provisioning.build_character_insert_sql(equipped)
    for item in bot['equipment']:
        if item['slot'] in (8, 9):
            assert item['enchantments'] in sql
            assert int(item['enchantments'].split()[18]) == {8: 3717, 9: 3723}[item['slot']]
    assert {'id': 164, 'value': 525, 'max': 525} in bot['skills']
    assert 'SELECT c.`guid`, 164, 525, 525' in sql
