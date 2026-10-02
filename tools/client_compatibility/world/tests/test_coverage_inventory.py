import copy
import json
import pytest
from tools.client_compatibility import coverage


def test_initial_manifest_does_not_claim_live_passes_or_opcode_coverage():
    manifest=coverage.load_manifest();report=coverage.report(manifest)
    assert report['planned_feature_scenarios']>=60
    assert report['current_qualified_feature_passes']==0
    assert all(row['qualification']=='pending_current_live_qualification' for row in report['features'])
    assert report['protocol_inventory']['modern_names']>report['protocol_inventory']['modern_names_referenced_by_bridge']
    assert 'coverage_percent' not in report['protocol_inventory']


@pytest.mark.parametrize('change',['duplicate','forged_pass','missing_oracle'])
def test_matrix_cannot_hide_duplicates_or_claim_a_pass(tmp_path,change):
    manifest=copy.deepcopy(coverage.load_manifest())
    if change=='duplicate':manifest['features'].append(manifest['features'][0])
    if change=='forged_pass':manifest['features'][0]['passed']=True
    if change=='missing_oracle':manifest['features'][0].pop('oracle')
    target=tmp_path/'manifest.json';target.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):coverage.load_manifest(target)


def test_event_inventory_reports_unmapped_names_without_reading_packet_bodies(tmp_path):
    path=tmp_path/'events.jsonl'
    path.write_text(json.dumps({'event':'unmapped_client_packet','name':'CMSG_QUEST_GIVER_ACCEPT_QUEST',
        'body':'not admitted'})+'\n'+json.dumps({'event':'modern_packet','name':'CMSG_QUEST_GIVER_ACCEPT_QUEST'})+'\n')
    observed=coverage.event_inventory(path)
    assert observed['unmapped_client_names']=={'CMSG_QUEST_GIVER_ACCEPT_QUEST':1}
    assert 'body' not in observed and 'not admitted' not in json.dumps(observed)
