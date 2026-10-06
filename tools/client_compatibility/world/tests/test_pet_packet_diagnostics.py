"""Capture exact public pet reads while authentication remains excluded."""
import json
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec, result


def test_safe_pet_read_catalog_names_have_body_evidence(codec,tmp_path):
    names=['CMSG_REQUEST_PET_INFO','CMSG_QUERY_PET_NAME','CMSG_PET_NAME_QUERY',
        'SMSG_PET_NAME_QUERY_RESPONSE','SMSG_QUERY_PET_NAME_RESPONSE','SMSG_PET_SPELLS','SMSG_PET_SPELLS_MESSAGE']
    for name in names:result(codec,op='packet_diagnostic',root=str(tmp_path),name=name,body='0102')
    rows=[json.loads(line) for line in (tmp_path/'evidence/world_packets.jsonl').read_text().splitlines()]
    assert [r['name'] for r in rows]==names and all(r['body']=='0102' for r in rows)


def test_pet_allowlist_does_not_admit_authentication_or_unrelated_pet_services(codec,tmp_path):
    for name in ['CMSG_AUTH_SESSION','CMSG_PET_AUTH_QUERY','SMSG_ENTER_ENCRYPTED_MODE',
        'SMSG_CONNECT_TO','CMSG_BATTLE_PET_REQUEST_JOURNAL','CMSG_PET_RENAME']:
        result(codec,op='packet_diagnostic',root=str(tmp_path),name=name,body='0102')
    assert not (tmp_path/'evidence/world_packets.jsonl').exists()
