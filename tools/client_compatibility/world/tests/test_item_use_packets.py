"""Trace only reviewed item-use packets needed for the ordinary glyph trial."""
import json
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


def test_item_use_is_captured_without_authentication_or_launcher_payloads(codec,tmp_path):
    (tmp_path/'evidence').mkdir()
    for name in ['CMSG_USE_ITEM','CMSG_AUTH_SESSION','SMSG_CONNECT_TO','SMSG_ENTER_ENCRYPTED_MODE']:
        result(codec,op='packet_diagnostic',root=str(tmp_path),name=name,body='ff230000')
    rows=[json.loads(line) for line in (tmp_path/'evidence/world_packets.jsonl').read_text().splitlines()]
    assert [(r['name'],r['body']) for r in rows]==[('CMSG_USE_ITEM','ff230000')]
