"""Bridge launch provenance includes its public hotfix configuration."""
from tools.client_compatibility.world import control


def test_each_hotfix_config_invalidates_receipt_but_unrelated_work_does_not(tmp_path,monkeypatch):
    monkeypatch.setattr(control.lab,'REPO',tmp_path)
    folder=tmp_path/'experiments/configs/client_harness';folder.mkdir(parents=True)
    current=control.source_digest()
    for name in ['public_portal_hotfix_v1.json','control_skill_metadata_v1.json']:
        p=folder/name;p.write_text('{"revision":1}\n')
        added=control.source_digest();assert added!=current
        p.write_text('{"revision":2}\n')
        changed=control.source_digest();assert changed!=added;current=changed
    (folder/'unrelated_fixture.json').write_text('{"revision":3}\n')
    assert control.source_digest()==current
