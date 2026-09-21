import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tools.raid_program import calibration_reuse as reuse


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return {'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def compatible(tmp_path, monkeypatch):
    from tools.raid_program import review_execution
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    git('commit', '--allow-empty', '-qm', 'base')
    source = {'source_commit': git('rev-parse', 'HEAD'), 'binary_sha256': 'a'*64}
    (tmp_path/'boss.cpp').write_text('// boss-only change\n')
    git('add', 'boss.cpp'); git('commit', '-qm', 'boss')
    target = {'source_commit': git('rev-parse', 'HEAD'), 'binary_sha256': 'b'*64}
    packet = put(tmp_path, 'packet.json', {})
    setup = put(tmp_path, 'readback.json', {'gear': 'same'})
    identity = {'scenario_kind': 'raid', 'encounter': {'boss': 'another_boss'}}
    statement = {'calibration_packet': packet, 'source_build': source, 'target_build': target,
        'validation_identity': identity, 'actor_id': '1', 'spec': 'balance_druid',
        'changed_paths': ['boss.cpp'], 'unchanged': dict.fromkeys(reuse.UNCHANGED, True),
        'current_setup_evidence': [setup], 'rationale': 'Only isolated boss script changed.',
        'author_session_id': 'implementer'}
    review = {'verdict': 'approved'}
    def verify_review(root, doc, implementer_session_id):
        assert implementer_session_id == 'implementer'
        return {'statement.json': hashlib.sha256((root/'statement.json').read_bytes()).hexdigest()}
    # Separate rollout validation is covered by test_review_execution; exercise
    # this consumer's identity, complete-delta and setup checks with real Git.
    monkeypatch.setattr(review_execution, 'verify_review', verify_review)
    def call():
        proof = put(tmp_path, 'proof.json', {'statement': put(tmp_path, 'statement.json', statement),
                                           'review': put(tmp_path, 'review.json', review)})
        return reuse.verify_compatibility(tmp_path, proof, packet_ref=packet,
            source_build=source, target_build=target, validation_identity=identity,
            actor_id='1', spec='balance_druid')
    return tmp_path, statement, review, call


def test_other_boss_uses_same_measurement_after_review(compatible):
    root, statement, review, call = compatible
    assert call()['status'] == 'reviewed_compatible'


@pytest.mark.parametrize('component', sorted(reuse.UNCHANGED))
def test_changed_or_unknown_inputs_require_recalibration(compatible, component):
    root, statement, review, call = compatible
    statement['unchanged'][component] = False
    with pytest.raises(ValueError, match='changed or unknown'):
        call()


def test_omitted_delta_rejected(compatible):
    root, statement, review, call = compatible
    statement['changed_paths'] = []
    with pytest.raises(ValueError, match='omits source'):
        call()


def test_wrong_build_or_unapproved_review_rejected(compatible):
    root, statement, review, call = compatible
    review['verdict'] = 'rejected'
    with pytest.raises(ValueError, match='independent approval'):
        call()
    review['verdict'] = 'approved'
    statement['target_build'] = {'source_commit': 'f'*40, 'binary_sha256': 'c'*64}
    with pytest.raises(ValueError, match='identity mismatch'):
        call()


def test_setup_readback_is_bound(compatible):
    root, statement, review, call = compatible
    (root/'readback.json').write_text('{}')
    with pytest.raises(ValueError):
        call()


def test_register_requires_qualification_and_preserves_prior_entries(tmp_path, monkeypatch):
    from tools.raid_program import dps_gate
    put(tmp_path, 'packet.json', {'actor_id': '1'})
    calls = []
    def verify(root, ref, **kwargs):
        calls.append(kwargs)
        return {'passed': True}
    monkeypatch.setattr(dps_gate, 'verify_packet', verify)
    reuse.register(tmp_path, 'packet.json', 'balance_druid', '1')
    reuse.register(tmp_path, 'packet.json', 'balance_druid', '1')
    assert len(calls) == 2
    assert len(reuse.candidates(tmp_path, 'balance_druid')['candidates']) == 1
    def fail(*args, **kwargs):
        raise ValueError('95% DPS gate failed')
    monkeypatch.setattr(dps_gate, 'verify_packet', fail)
    with pytest.raises(ValueError, match='95%'):
        reuse.register(tmp_path, 'packet.json', 'fire_mage', '1')
    assert reuse.candidates(tmp_path, 'fire_mage')['candidates'] == []
