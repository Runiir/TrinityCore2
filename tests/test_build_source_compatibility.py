"""Admission after a progress commit must reuse the binary but reject changed inputs."""
from pathlib import Path
import subprocess

import pytest

from tools.raid_program.build_control_compatibility import GRAPH, _git as git, require_coordination_build


def build_receipt(root, baseline):
    import hashlib
    identity = {'commit': baseline, 'tree': git(root, 'rev-parse', baseline + '^{tree}'),
                'clean': True, 'dirty': False, 'porcelain_sha256': hashlib.sha256(b'').hexdigest()}
    return {'commit': baseline, 'source_identity': {k: dict(identity) for k in ('request', 'admission', 'completion')}}


def verify_build_source(root, baseline):
    return require_coordination_build(root, build_receipt(root, baseline))


def commit(root, name, content="{}"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "-C", str(root), "add", name], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", name], check=True)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def built(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.invalid")):
        subprocess.run(["git", "-C", str(tmp_path), "config", key, value], check=True)
    baseline = commit(tmp_path, "src/spell.cpp", "reviewed source")
    return tmp_path, baseline


def test_progress_and_receipt_commits_preserve_build_identity(built):
    root, baseline = built
    assert verify_build_source(root, baseline)["coordination_changes"] == []
    commit(root, GRAPH)
    head = commit(root, "artifacts/cata_raid_program/build-receipt.json")
    proof = verify_build_source(root, baseline)
    assert proof["build_source_commit"] == baseline
    assert proof["control_commit"] == head != baseline
    assert set(proof["coordination_changes"]) == {GRAPH, "artifacts/cata_raid_program/build-receipt.json"}


@pytest.mark.parametrize("path", ["src/spell.cpp", "experiments/configs/roster.json",
    "tools/runner.py", "CMakeLists.txt", "docs/hidden.cpp", "artifacts/cata_raid_program/loader.py",
    "dataset/gear.json", "references/request.json.dvc"])
def test_changed_inputs_still_require_a_build(built, path):
    root, baseline = built
    commit(root, path, "changed")
    with pytest.raises(ValueError, match="control_path_not_allowed"):
        verify_build_source(root, baseline)


@pytest.mark.parametrize("path", [GRAPH, "src/new.cpp"])
def test_dirty_state_cannot_be_hidden_by_metadata_exemption(built, path):
    root, baseline = built
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("uncommitted")
    with pytest.raises(ValueError, match="control_source_dirty"):
        verify_build_source(root, baseline)


def test_nonancestor_is_not_a_compatible_revision(built):
    root, baseline = built
    later = commit(root, GRAPH)
    subprocess.run(["git", "-C", str(root), "checkout", "--detach", baseline], check=True, capture_output=True)
    with pytest.raises(ValueError, match="not_ancestor"):
        verify_build_source(root, later)


def test_metadata_symlink_is_not_exempt(built):
    root, baseline = built
    target = root / GRAPH
    target.parent.mkdir(parents=True)
    target.symlink_to(root / "src/spell.cpp")
    subprocess.run(["git", "-C", str(root), "add", GRAPH], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "symlink"], check=True)
    with pytest.raises(ValueError, match="not_regular"):
        verify_build_source(root, baseline)


@pytest.mark.parametrize('change', [GRAPH, 'src/spell.cpp'])
def test_dummy_cli_reuses_build_only_after_coordination_commit(built, monkeypatch, tmp_path, change):
    import json
    import sys
    from tools.raid_program import run_dummy_calibrations as runner
    root, baseline = built
    head = commit(root, change, 'progress or code')
    # Native receipt verification has its own production coordinator tests;
    # here exercise the real CLI admission and its config-derivation boundary.
    receipt = tmp_path.parent / (tmp_path.name + '-build.json')
    receipt.write_text(json.dumps({**build_receipt(root, baseline), 'worktree': str(root),
        'classification': 'success', 'output_artifacts': [{'kind': 'worldserver_elf', 'path': str(root/'build/worldserver')}]}))
    policy = tmp_path.parent / (tmp_path.name + '-policy.json')
    policy.write_text('{}')
    monkeypatch.setattr(runner, 'ROOT', root)
    monkeypatch.setattr(runner, 'preflight_calibration_reference_binding', lambda **kw: {'valid': True})
    verified = []
    monkeypatch.setattr(runner, 'verify_receipt', lambda *a: verified.append(a) or {'gate_bearing': True})
    class ReachedConfiguration(Exception): pass
    def derive(**kwargs):
        assert kwargs['expected_source_commit'] == head
        assert kwargs['expected_source_tree'] == git(root, 'rev-parse', 'HEAD^{tree}')
        raise ReachedConfiguration
    monkeypatch.setattr(runner, 'derive_runtime_config', derive)
    monkeypatch.setattr(sys, 'argv', ['run_dummy_calibrations', '--spec', 'balance_druid',
        '--build-receipt', str(receipt), '--policy', str(policy),
        '--output', str(tmp_path.parent / (tmp_path.name + '-capture'))])
    if change == GRAPH:
        with pytest.raises(ReachedConfiguration): runner.main()
    else:
        with pytest.raises(ValueError, match='control_path_not_allowed'): runner.main()
    assert len(verified) == 1


@pytest.mark.parametrize('change', [GRAPH, 'experiments/configs/roster.json'])
def test_shared_launch_retains_both_source_identities(built, monkeypatch, change):
    import json
    from types import SimpleNamespace
    from tools.raid_program import shared_instance_preparation as launch
    root, _ = built
    commit(root, '.gitignore', 'build/\n')
    commit(root, launch.BASE_CONFIG, json.dumps({'typed_inputs': {'data_dir': '/fixture/data'}}))
    baseline = commit(root, 'policy.json', '{}')
    binary = root/'build/worldserver'
    binary.parent.mkdir()
    binary.write_bytes(b'fixture binary, not native evidence')
    commit(root, change, '{}')
    output = root.parent/(root.name + '-shared-output')
    output.mkdir()
    config = output/'runtime.conf'
    config.write_text('fixture')
    config_receipt = output/'config-receipt.json'
    config_receipt.write_text(json.dumps({'destination': {'path': str(config)}}))
    receipt = output/'build.json'
    receipt.write_text(json.dumps({**build_receipt(root, baseline), 'worktree': str(root),
        'classification': 'success', 'resource_class': 'worldserver_build',
        'output_artifacts': [{'kind': 'worldserver_elf', 'path': str(binary)}]}))
    monkeypatch.setattr(launch, 'load_fixture', lambda *a: {'fixture_sha256': 'fixture',
        'fixture': {'inputs': {}},
        'subject': {'expected': SimpleNamespace(map_id=669)},
        'witness': {'expected': SimpleNamespace(map_id=669)}})
    monkeypatch.setattr(launch, 'verify_runtime_config_derivation', lambda **kw: {})
    monkeypatch.setattr(launch, 'validate_shared_config', lambda *a: None)
    monkeypatch.setattr(launch, 'verify_receipt', lambda *a: {'gate_bearing': True})
    monkeypatch.setattr(launch, 'require_runtime_asset_closure', lambda **kw: {'complete': True})
    def verify():
        return launch.verify_launch(source=root, fixture_path=root/'policy.json',
            config=config, config_receipt=config_receipt, config_receipt_sha256=launch.sha256(config_receipt),
            build_receipt=receipt, build_policy=root/'policy.json', coordinator_repository=root,
            output_dir=output)
    if change == GRAPH:
        result = verify()
        assert result['build_source_commit'] == baseline
        assert result['source_commit'] == git(root, 'rev-parse', 'HEAD') != baseline
        assert result['source_compatibility']['valid']
        assert result['binary_sha256'] == launch.sha256(binary)
    else:
        with pytest.raises(ValueError, match='control_path_not_allowed'): verify()


def test_selected_runtime_json_cannot_use_evidence_directory_exemption(built):
    root, baseline = built
    name = 'artifacts/cata_raid_program/runtime-fixture.json'
    commit(root, name)
    with pytest.raises(ValueError, match='runtime input changed'):
        require_coordination_build(root, build_receipt(root, baseline), runtime_inputs=(root/name,))


def test_strict_mode_cannot_be_overridden_by_layered_authority(built):
    from tools.raid_program.build_control_compatibility import verify_build_control_compatibility
    root, baseline = built
    report = verify_build_control_compatibility(worktree=root, receipt=build_receipt(root, baseline),
        coordination_only=True, authority_path=root/'absent.json', authority_sha256='0'*64)
    assert not report['valid']
    assert 'coordination_only_disallows_layered_authority' in report['rejections']
