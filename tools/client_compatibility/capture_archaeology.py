"""Checkpoint the owned archaeology and mount compatibility experiment."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
from dvclive import Live
from .lab_runtime import REPO, ROOT, owned_process, sha256
from .observation.archaeology import collected
from .world.events import capture_packet


FAILURES = [
    "Conflicting Alchemy specializations broke the profession frame",
    "Incoming 60895 cast uses one visual and three crafting counts",
    "Outgoing 60895 cast uses one visual; extra visual shifted the cast time",
    "Gather requires visible GO targeting and owned client/server cast acknowledgement",
    "Backpack capacity defaulted to zero",
    "Expired native instruments needed destroy/removal translation",
    "First research project exposed a nested serializer mismatch",
    "Interruption fixture initially expected the wrong failure number",
    "Main pixi manifest lacks auth protobuf/Crypto dependencies; auth manifest passes",
    "Mount fixture initially lacked character metadata and assumed incorrect mask blocks",
    "Ongoing CGObject updates need both active and changed fragment bits (3)",
    "Flight Master's License was absent and Master Riding was reduced to 300",
    "Existing movement test assumed every native opcode has an MSG prefix; flight uses CMSG",
    "Airborne dismount needs modern/native extra-flag mapping and the observed falling hint",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if REPO != Path('/home/runiir/Games/trinity-442-compatibility'):
        raise RuntimeError("capture must use the isolated compatibility checkout")
    if subprocess.check_output(['git', 'status', '--porcelain', '--', 'tools/client_compatibility',
            'experiments/configs/client_harness', 'docs/client_harness'], cwd=REPO).strip():
        raise RuntimeError("commit experiment code/configs/docs before capture")
    out.mkdir(parents=True, exist_ok=False)
    evidence = ROOT / 'evidence'
    episode = json.loads((evidence / 'laya_archaeology_episode.json').read_text())
    confirmation = collected(episode['completion']['session'], episode['steps'][-1]['started_at'])
    if not episode['completed'] or confirmation != episode['completion'] or confirmation['quantity'] != 8:
        raise RuntimeError("completed native fragment collection was not reproduced from trace")
    tests = ET.parse(evidence / 'archaeology_protocol_tests.xml').getroot().findall('testsuite')
    if not tests or any(int(t.attrib.get('failures', 0)) + int(t.attrib.get('errors', 0)) for t in tests):
        raise RuntimeError("protocol tests missing or failing")
    monitor = json.loads((evidence / 'client_monitor.json').read_text())
    current = owned_process('client')
    if not current or current['pid'] != monitor['pid'] or not monitor['second_monitor_verified']:
        raise RuntimeError("owned client second-monitor placement is unverified")
    mount = json.loads((evidence / 'mount_live_validation.json').read_text())
    if mount['mounted_addon']['speed'] != 14 or not mount['mounted_addon']['in_world']:
        raise RuntimeError("mounted movement observation is missing")
    flight = json.loads((evidence / 'flight_live_validation.json').read_text())
    if not flight['verified']: raise RuntimeError("owned flight controls/landing are unverified")
    with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5) as r:
        health = json.load(r)
    (out / 'model_health.json').write_text(json.dumps(health, indent=2) + '\n')
    files = ['laya_archaeology_episode.json', 'archaeology_character_setup.json',
        'archaeology_character_setup_before_flight.json', 'archaeology_protocol_tests.xml',
        'client_monitor.json', 'mount_live_validation.json', 'flight_live_validation.json',
        '85_professions_fixed.png', 'fragment_looted.png', 'gather_test.png',
        'survey_castbar_fixed.png', 'backpack_fixed.png', 'telescope_removed_verified.png',
        'mount_final_smoke.png', 'mount_speed_verified.png', 'dismounted_final.png',
        'survey_bar_recheck.png', 'survey_interrupted_verified.png', 'survey_retry_verified.png',
        *flight['screenshots']]
    for step in episode['steps']:
        for frame in step['screenshots']:
            if sha256(evidence / frame['file']) != frame['sha256']:
                raise RuntimeError('episode frame identity changed')
            files.append(frame['file'])
    for name in sorted(set(files)): shutil.copy2(evidence / name, out / name)
    with (out / 'world_packets.jsonl').open('w') as safe:
        for line in (evidence / 'world_packets.jsonl').open():
            if capture_packet(json.loads(line)['name']): safe.write(line)
    shutil.copy2(ROOT / 'logs/modern_world.jsonl', out / 'modern_world.jsonl')
    paths = [p for p in (REPO / 'tools/client_compatibility').rglob('*') if p.is_file()
        and not {'.pixi', '__pycache__', '.pytest_cache'} & set(p.parts)]
    paths += [REPO / 'experiments/configs/client_harness/85_archaeology_character_v1.json',
              REPO / 'docs/client_harness/archaeology_20261001.md']
    receipt = {'schema': 'client442_archaeology_validation_v1', 'client_build': 60895,
        'native_build': 15595, 'worktree': str(REPO),
        'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'code_sha256': {str(p.relative_to(REPO)): sha256(p) for p in paths},
        'native_worldserver_sha256': sha256(ROOT / 'bin/worldserver'),
        'processes': {name: {k: v for k, v in (owned_process(name) or {}).items() if k in ['pid', 'start_ticks']}
            for name in ['worldserver', 'authserver', 'modern_world', 'modern_auth', 'laya', 'client']},
        'fragment_collection': confirmation, 'model_actions': len(episode['steps']),
        'model_navigation_steps': [3, 25], 'teacher_loot_coordinates': True,
        'manual_movement_in_initial_steps': True, 'weights_fine_tuned': False,
        'screenshots_directly_consumed_by_model': False,
        'observation_sources': episode['observation_sources'],
        'protocol_tests_passed': sum(int(t.attrib['tests']) for t in tests),
        'mounted_run_speed': 14, 'flight_verified': True, 'second_monitor_verified': True,
        'full_gameplay_compatibility': False, 'repaired_intermediate_failures': FAILURES,
        'remaining': ['NPC creation', 'broad ongoing inventory/research updates',
            'general targeted combat', 'crafting', 'transports/vehicles', 'quests',
            'character-selection equipment preview', 'automatic screenshot loot localization',
            'reference gear gems/enchants'],
        'screenshots': {name: sha256(out / name) for name in sorted(set(files)) if name.endswith('.png')}}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    with Live(dir=str(out / 'dvclive'), save_dvc_exp=False, dvcyaml=False, report=None) as live:
        for key, value in {'archaeology/fragments': 8, 'archaeology/laya_steps': len(episode['steps']),
                'archaeology/teacher_loot_coordinates': 1, 'mount/run_speed': 14,
                'mount/flight': 1, 'monitor/second': 1,
                'validation/protocol_tests_passed': receipt['protocol_tests_passed']}.items():
            live.log_metric(key, value)
        live.next_step()
    needles = [json.loads((ROOT / f'secrets/{name}').read_text())['password'].encode()
        for name in ['runtime.json', 'game_account.json']]
    needles.append((ROOT / 'secrets/root_password').read_text().strip().encode())
    for path in out.rglob('*'):
        if path.is_file() and any(needle in path.read_bytes() for needle in needles):
            raise RuntimeError('credential matched evidence')
    archive = REPO / 'artifacts/client_harness/442_archaeology_20261001.tar.gz'
    with tarfile.open(archive, 'w:gz') as handle: handle.add(out, arcname='442_archaeology_20261001')
    print(json.dumps({'archive': str(archive), 'protocol_tests_passed': receipt['protocol_tests_passed'],
        'fragments': 8, 'flight_verified': True}, indent=2))


if __name__ == '__main__': main()
