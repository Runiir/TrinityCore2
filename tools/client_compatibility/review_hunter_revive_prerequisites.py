"""Verify the owned Hunter's Revive prerequisite without input or mutation."""
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from . import actors, lab_runtime as lab
from .interaction_archaeology_projects import dbc
from .interaction_bridge_deploy import identity
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot
from .interaction_retained_class_fixture import closed
from .interaction_social import actor
from .observation.journal import latest
from .world.buffer import Reader


def absent_clients():
    for name in ('primary', 'scout'):
        with actor(name):
            if lab.owned_process('client'):
                raise RuntimeError('read-only prerequisite review requires both clients stopped')


def public_revive(entry, recon, entry_ref):
    """Read one actual stock caption from either source-bound Hunter recon form."""
    detail = {'await_owned_tame_cast_review': 'fixture_tame_line2',
        'await_owned_revive_cast_review': 'revive_page2_0'}.get(recon.get('phase'))
    if (detail is None or recon.get('completed') is not True or recon.get('failure') is not None or
        not recon.get('finished_at') or recon.get('entry_source') != entry_ref or
        recon.get('native_session') != entry.get('native_session') or not entry.get('native_session') or
        recon.get('runtime') != entry.get('runtime') or recon.get('actor') != entry.get('actor') or
        recon.get('fixture_source') != entry.get('fixture_source') or
        not entry['finished_at'] <= recon['started_at'] < recon['finished_at']):
        raise RuntimeError('Revive stock caption is not bound to the actual closed Hunter entry')
    observation = recon.get('spellbook_details', {}).get(detail, {})
    state = observation.get('state', {})
    probe = state.get('spellbook_probe', {})
    rows = [r for r in probe.get('rows', []) if r.get('id') == 982]
    if (observation.get('input_sent') is not False or state.get('source') != 'normal_addon_visible_ui_pixels' or
        state.get('player') != 'Harnesshunt' or state.get('level') != 10 or
        probe.get('skill_line') != 2 or len(rows) != 1 or rows[0].get('known') is not True or
        rows[0].get('name') != 'Revive Pet' or rows[0].get('kind') != 'SPELL' or
        (recon['phase'] == 'await_owned_revive_cast_review' and recon.get('revive_spell') != rows[0])):
        raise RuntimeError('actual stock known Revive982 row or observed recon caption differs')
    return rows[0]


def review(output, entry_path, recon_path, pause_path, remote_path):
    started_at = time.time()
    output = output.resolve()
    if output.exists() or not output.is_relative_to(lab.ROOT / 'evidence'):
        raise ValueError('requires a new private evidence episode directory')
    absent_clients()
    entry, recon, pause = [closed(p) for p in (entry_path, recon_path, pause_path)]
    remote = json.loads(remote_path.read_text())
    native, bridge = identity('worldserver'), identity('modern_world')
    before = snapshot()
    if (entry.get('actor', {}).get('guid') != 6 or entry.get('phase') != 'owned_class_entered' or
        entry.get('runtime', {}).get('worldserver') != native or
        recon.get('runtime') != entry.get('runtime') or recon.get('actor') != entry.get('actor') or
        pause.get('runtime') != entry.get('runtime') or pause.get('phase') != 'parked_scout_resource_paused' or
        len(pause.get('checks', {})) != 8 or not all(pause['checks'].values()) or
        pause.get('before') != pause.get('after') or before != pause.get('after') or
        any(v['native']['online'] for v in before.values()) or
        remote.get('actual_remote_verified') is not True or remote.get('complete_json_png_verified') is not True):
        raise RuntimeError('closed Hunter entry, public observation or offline preservation differs')
    config = (lab.ROOT / 'config/worldserver.conf').read_text()
    data = re.findall(r'(?m)^DataDir\s*=\s*"([^"]+)"\s*$', config)
    if data != [str(lab.ROOT / 'data')]:
        raise RuntimeError('native DBC source differs from configured DataDir')
    source = entry_path.resolve().parent.parent
    checkpoint = json.loads((source / 'checkpoint_receipt.json').read_text())
    if (remote.get('archive_sha256') != checkpoint.get('sha256') or
        remote.get('bytes') != checkpoint.get('bytes') or
        remote.get('pointer') != checkpoint.get('file', '') + '.dvc'):
        raise RuntimeError('actual remote proof does not match the Hunter source checkpoint')
    for path in (entry_path, recon_path, pause_path):
        rows = [r for r in checkpoint['file_manifest'] if r['path'] == str(path.resolve().relative_to(lab.ROOT))]
        if len(rows) != 1 or rows[0]['sha256'] != lab.sha256(path):
            raise RuntimeError('source episode differs from verified remote manifest')
    binaries = [r for r in checkpoint['file_manifest'] if r['path'] == 'bin/worldserver']
    if len(binaries) != 1 or lab.sha256(lab.ROOT / 'bin/worldserver') != binaries[0]['sha256']:
        raise RuntimeError('native binary differs from the verified source runtime')
    row = latest(lab.ROOT / 'evidence/world_packets.jsonl', lambda r:
        r.get('session') == entry['native_session'] and r.get('direction') == 'from_native' and
        r.get('name') == 'SMSG_SEND_KNOWN_SPELLS' and entry['started_at'] <= r.get('time', 0) <= entry['finished_at'])
    if not row:
        raise RuntimeError('actual same-entry native known-spell body is unavailable')
    body = bytes.fromhex(row['body'])
    reader = Reader(body)
    initial, count = reader.unpack('BH')
    if initial != 1 or not 0 < count <= 16000:
        raise RuntimeError('native known-spell packet header differs')
    spells = [reader.unpack('Ih')[0] for _ in range(count)]
    cooldowns, = reader.unpack('H')
    history = [reader.unpack('IIHii') for _ in range(cooldowns)]
    reader.end()
    public = public_revive(entry, recon, bound(entry_path))
    if 982 not in spells:
        raise RuntimeError('native and stock public Revive prerequisite disagree')
    abilities, _ = dbc('SkillLineAbility', 14)
    spell_rows, _ = dbc('Spell', 48)
    levels, _ = dbc('SpellLevels', 4)
    race_class, _ = dbc('SkillRaceClassInfo', 9)
    ability = [r for r in abilities if r[2] == 982]
    spell = [r for r in spell_rows if r[0] == 982]
    if len(ability) != 1 or len(spell) != 1:
        raise RuntimeError('Revive DBC identity is ambiguous')
    level = [r for r in levels if r[0] == spell[0][41]]
    owner = before['6']['native']
    skill = [r for r in before['6']['saved']['skills'] if r[0] == ability[0][1]]
    eligible = (len(level) == 1 and len(skill) == 1 and ability[0][9] == 2 and
        (not ability[0][3] or ability[0][3] & (1 << (owner['race'] - 1))) and
        (not ability[0][4] or ability[0][4] & (1 << (owner['class'] - 1))) and
        max(level[0][1], level[0][3]) <= owner['level'])
    if not eligible:
        raise RuntimeError('loaded native skill/level prerequisite differs')
    absent_clients()
    if snapshot() != before or identity('worldserver') != native or identity('modern_world') != bridge:
        raise RuntimeError('read-only review changed actors or runtimes')
    output.mkdir(parents=True, mode=0o700)
    receipt = {'schema': 'client442_revive_prerequisite_review_v1', 'started_at': started_at,
        'finished_at': time.time(), 'actor': entry['actor'], 'runtime': {'worldserver': native, 'modern_world': bridge},
        'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip(),
        'controller': 'code', 'model': None, 'revision': None, 'cases': [], 'completed': True, 'failure': None,
        'sources': [bound(p) for p in (entry_path, recon_path, pause_path)], 'remote_source': bound(remote_path),
        'source_checkpoint': {'pointer': remote['pointer'], 'sha256': remote['archive_sha256'], 'bytes': remote['bytes']},
        'native_known_spell_packet': {**row, 'body_sha256': hashlib.sha256(body).hexdigest(),
            'initial_login': initial, 'ids': spells, 'cooldowns': history}, 'public_revive': public,
        'dbc': {'hashes': {n: lab.sha256(lab.ROOT / 'data/dbc/enUS' / (n + '.dbc')) for n in
            ('SkillLineAbility', 'Spell', 'SpellLevels', 'SkillRaceClassInfo')},
            'ability': ability[0], 'levels': level[0], 'saved_skill': skill[0],
            'race_class_rows': [r for r in race_class if r[1] == ability[0][1]]},
        'native_source': {'path': 'src/server/game/Entities/Player/Player.cpp',
            'sha256': lab.sha256(lab.REPO / 'src/server/game/Entities/Player/Player.cpp'),
            'functions': ['_LoadSkills', 'LearnSkillRewardedSpells', '_SaveSpells']},
        'saved_spell_row_present': any(r[0] == 982 for r in before['6']['saved']['spells']),
        'known_native_and_public': True, 'automatic_skill_level_eligible': True,
        'all_six_snapshot_sha256': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        'all_six_snapshots_preserved': True, 'both_clients_stopped': True, 'input_sent': False,
        'spell_grant_sent': False, 'pet_mutation_sent': False, 'qualification_added': False,
        'qualified_scope': 'Prerequisite review only. Revive982 is already known; a dead-pet cast remains unqualified.'}
    lab.private_write(output / 'episode.json', json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'known_native_and_public': True, 'saved_spell_row_present': receipt['saved_spell_row_present'],
        'all_six_snapshots_preserved': True, 'qualification_added': False}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('output', 'entry', 'recon', 'pause', 'remote'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'):
        review(args.output, args.entry, args.recon, args.pause, args.remote)
