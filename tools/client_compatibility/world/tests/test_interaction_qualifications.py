"""Coverage regeneration retains reviewed successes without expanding their scope."""
import copy
import pytest
from tools.client_compatibility.interaction_qualifications import reconcile
from tools.client_compatibility.interaction_inventory import checklist,render


def test_current_checklist_preserves_markers_group_archaeology_and_quest_evidence():
    data=checklist();by_id={case['id']:case for case in data['cases']}
    for key in ['character.equipment_set_save','character.equipment_set_equip','character.equipment_set_delete',
            'raid.world_marker','raid.clear_marker','raid.roster_health_bars',
            'party.role_poll','party.role_assign','archaeology.survey','archaeology.site_rotation',
            'quests.accept','quests.decline','quests.collapse_zone','quests.abandon_cancel',
            'quests.choose_reward','quests.reward_item','quests.reward_money',
            'talents.glyph_filter_known','talents.glyph_filter_unknown','talents.glyph_filter_prime',
            'talents.glyph_filter_major','talents.glyph_filter_minor','map.minimap_tracking',
            'quests.giver_trivial_marker','reputation.inspect_standing','reputation.watched_faction',
            'reputation.collapse','reputation.expand','reputation.inactive_toggle',
            'reputation.persist','reputation.at_war_toggle',
            'reputation.gain_standing','reputation.lose_standing',
            'currency.open','currency.close','currency.expand','currency.collapse',
            'currency.inspect_currency','currency.backpack_toggle','currency.unused_toggle','currency.persist',
            'archaeology.close','archaeology.race_select','archaeology.project_select','archaeology.solve_project',
            'archaeology.project_completion','archaeology.persist','currency.spend_currency',
            'archaeology.use_keystone','archaeology.project_tooltip','archaeology.cast_bar',
            'quests.persist','map.continent','map.zone','map.zoom_in','map.zoom_out',
            'map.world_map_binding','map.coordinates','map.player_position',
            'map.digsite_overlay','archaeology.continent_map','map.minimap_zoom',
            'character.equipment_tooltips','talents.glyph_tooltip','character.equipment_set_create']:
        assert by_id[key]['qualification'] and '- [x] `'+key+'`' in render(data)
    for key in ['raid.assistant_promote','party.full_group_error',
            'talents.glyph_replace','currency.gain_currency','currency.weekly_cap',
            'map.pan','map.dungeon_floor','map.quest_route','archaeology.fragments_cap']:
        assert 'qualification' not in by_id[key] and '- [ ] `'+key+'`' in render(data)
    assert data['qualified_operations']==sum('qualification' in case for case in data['cases'])
    assert all(record['scope'] and record['limits'] and record['evidence'] for record in data['qualification_records'])


def fixture(tmp_path):
    pointer='artifacts/client_harness/proof.tar.gz.dvc';path=tmp_path/pointer
    path.parent.mkdir(parents=True);path.write_text('outs: []\n')
    record={'id':'survey','operations':['archaeology.survey'],'scope':'One site','limits':'Other variants pending',
        'evidence':[{'pointer':pointer,'member':'evidence/run/episode.json','sha256':'a'*64}]}
    return {'cases':[{'id':'archaeology.survey'}]}, {'qualifications':[record]}


def test_unknown_and_duplicate_operations_cannot_turn_green(tmp_path):
    data,ledger=fixture(tmp_path)
    bad=copy.deepcopy(ledger);bad['qualifications'][0]['operations']=['archaeology.solve_project']
    with pytest.raises(ValueError,match='unknown'):reconcile(copy.deepcopy(data),bad,tmp_path)
    bad=copy.deepcopy(ledger);bad['qualifications'][0]['operations']*=2
    with pytest.raises(ValueError,match='duplicate'):reconcile(copy.deepcopy(data),bad,tmp_path)


def test_unlinked_or_unscoped_evidence_cannot_turn_green(tmp_path):
    data,ledger=fixture(tmp_path)
    for field,value in [('scope',''),('evidence',[]),('limits','')]:
        bad=copy.deepcopy(ledger);bad['qualifications'][0][field]=value
        with pytest.raises(ValueError):reconcile(copy.deepcopy(data),bad,tmp_path)
    for field,value in [('pointer','artifacts/client_harness/missing.dvc'),('member','../secret'),('sha256','invalid')]:
        bad=copy.deepcopy(ledger);bad['qualifications'][0]['evidence'][0][field]=value
        with pytest.raises(ValueError):reconcile(copy.deepcopy(data),bad,tmp_path)
