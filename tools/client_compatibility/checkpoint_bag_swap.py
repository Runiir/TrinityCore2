"""Carry only proof-owned UI171 members, retain current journals, then publish."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

from . import lab_runtime as lab
from .bag_swap_sources import bound, closed, cached_bundle, reference
from .item_actionbar_contract import require, strict_equal
from .bag_swap_evidence import ANCESTRY_SCHEMA
from .checkpoint_item_actionbar import write_exclusive
from .review_hunter_learn_checkpoint import DigestReader, remote_options, remote_request


def required_members(graph):
    """Record the exact JSON/frame accesses of the unchanged strict UI171 proof."""
    from . import item_actionbar_evidence as evidence
    data, digests = graph['data'], graph['digests']
    used = set()
    original_sources, original_frame = evidence.Sources, evidence.frame

    class ObservedSources(original_sources):
        def get(self, ref, successful=True):
            value = super().get(ref, successful)
            member = str(Path(ref['path']).relative_to(lab.ROOT))
            if digests.get(member) == ref['sha256']:
                used.add(member)
            else:
                rows = [row for ancestor in self.ancestry for row in ancestor.get('sources', [])
                    if row.get('original_path') == ref['path'] and row.get('sha256') == ref['sha256']]
                require(len(rows) == 1, 'required original UI171 source is not uniquely carried')
                used.add(str(Path(rows[0]['copy_path']).relative_to(lab.ROOT)))
            return value

    def observed_frame(store, episode, image, source):
        used.add(str((Path(source['path']).parent / image['file']).relative_to(lab.ROOT)))
        return original_frame(store, episode, image, source)

    try:
        evidence.Sources, evidence.frame = ObservedSources, observed_frame
        tracking = deepcopy(graph['tracking'])
        tracking['members'] = set(tracking['members'])
        evidence.proof(deepcopy(data), dict(digests), tracking)
    finally:
        evidence.Sources, evidence.frame = original_sources, original_frame
    ancestors = [(member, value) for member, value in data.items()
        if value.get('schema') == evidence.ANCESTRY_SCHEMA]
    closures = [member for member, value in data.items() if value.get('phase') == evidence.PHASE]
    require(len(closures) == 1, 'actual UI171 proof has one closed source')
    used.add(closures[0])
    require(len(ancestors) == 1, 'actual UI171 proof has one ancestry map')
    used.add(ancestors[0][0])
    for row in ancestors[0][1]['sources']:
        used.add(str(Path(row['copy_path']).relative_to(lab.ROOT)))
    used.add(str(Path(ancestors[0][1]['pointer_observation']['path']).relative_to(lab.ROOT)))
    require(used <= set(digests), 'a required UI171 proof member is outside its verified archive manifest')
    return sorted(used)


def carry(directory, preparation):
    ready = closed(preparation)
    reference(ready.get('authority_source'))
    require(ready.get('phase') == 'bags_swap_scout_ready' and bound(ready['authority_source']['path']) == ready['authority_source'],
        'carry requires the actual source-bound original scout ready authority')
    return carry_authority(directory, ready['authority_source'])


def carry_authority(directory, authority_source, *, admitted=None):
    """Carry a real admitted cache before any client is launched."""
    directory = Path(directory)
    require(directory.is_absolute() and directory.parent == lab.ROOT / 'evidence' and directory.is_dir() and
        not any(p.is_symlink() for p in (directory, *directory.parents)), 'named private occupied-swap batch required')
    reference(authority_source)
    require(bound(authority_source['path']) == authority_source, 'original admitted cache changed before carry')
    old = cached_bundle(authority_source['path']) if admitted is None else admitted
    wanted = set(required_members(old['graph']))
    manifest = {row['path']: row for row in old['archive']['manifest']}
    destination, target = directory / 'predecessor', directory / 'ancestry_manifest.json'
    require(not destination.exists() and not target.exists(), 'carry never overwrites immutable predecessor bytes')
    destination.mkdir(mode=0o700)
    rows, journals, authorities, seen = [], [], [], set()
    for role in ('remote', 'checkpoint'):
        ref = old['predecessor'][role]
        path = Path(ref['path'])
        require(bound(path) == ref, 'actual predecessor review/checkpoint source changed before carry')
        raw = path.read_bytes()
        require(strict_equal(json.loads(raw), old['values'][role]), 'actual predecessor review/checkpoint bytes differ')
        copy = destination / (ref['sha256'] + '.json')
        write_exclusive(copy, raw)
        authorities.append({'role': role, 'original_path': ref['path'], 'sha256': ref['sha256'],
            'bytes': len(raw), 'copy_member': str(copy.relative_to(lab.ROOT))})
    request = remote_request(remote_options(lab.REPO), old['dvc_pointer']['oid'])
    md5 = hashlib.md5()

    class ObjectReader:
        def __init__(self, stream):
            self.stream = stream

        def read(self, size=-1):
            raw = self.stream.read(size)
            md5.update(raw)
            return raw

    with urlopen(request, timeout=60) as remote:
        reader = DigestReader(ObjectReader(remote))
        with tarfile.open(fileobj=reader, mode='r|gz') as archive:
            for member in archive:
                if member.name not in wanted and member.name not in ('tracking/packets.jsonl', 'tracking/events.jsonl'):
                    continue
                require(member.isfile() and member.name not in seen, 'required actual predecessor member is duplicate or not a file')
                seen.add(member.name)
                raw = archive.extractfile(member).read()
                digest = hashlib.sha256(raw).hexdigest()
                if member.name in wanted:
                    expected = manifest[member.name]
                    require(len(raw) == member.size == expected['bytes'] and digest == expected['sha256'],
                        'required actual predecessor JSON/PNG bytes differ')
                    copy = destination / (digest + Path(member.name).suffix)
                    if not copy.exists():
                        write_exclusive(copy, raw)
                    else:
                        require(copy.read_bytes() == raw, 'same-hash predecessor bytes conflict')
                    rows.append({'original_path': str(lab.ROOT / member.name), 'original_member': member.name,
                        'sha256': digest, 'bytes': len(raw), 'copy_member': str(copy.relative_to(lab.ROOT))})
                else:
                    expected = old['journal_manifest'][member.name]
                    require(len(raw) == member.size == expected['bytes'] and digest == expected['sha256'],
                        'complete original predecessor journal differs from first-stream authority')
                    copy = destination / Path(member.name).name
                    write_exclusive(copy, raw)
                    journals.append({'original_member': member.name, 'sha256': digest, 'bytes': len(raw),
                        'copy_member': str(copy.relative_to(lab.ROOT))})
        while reader.read(1024 * 1024):
            pass
    require(seen == wanted | {'tracking/packets.jsonl', 'tracking/events.jsonl'} and
        reader.bytes == old['archive']['bytes'] and reader.digest.hexdigest() == old['archive']['sha256'] and
        md5.hexdigest() == old['dvc_pointer']['oid'], 'actual full predecessor archive SHA/size/DVC object differs')
    value = {'schema': ANCESTRY_SCHEMA, 'authority_source': authority_source,
        'archive': old['archive'], 'dvc_pointer': old['dvc_pointer'], 'pointer_raw_hex': old['pointer_raw_hex'],
        'members': sorted(rows, key=lambda r: r['original_member']),
        'journals': sorted(journals, key=lambda r: r['original_member']), 'authorities': authorities, 'actual_remote_verified': True,
        'compressed_md5': md5.hexdigest(), 'local_archive_created': False}
    write_exclusive(target, (json.dumps(value, indent=2) + '\n').encode())
    return value


def validate_carry(store, ready):
    require(len(store.maps) == 1, 'one strict carried UI171 proof map required')
    value = store.maps[0]
    cache = store.get(ready['authority_source'], False)
    from .bag_swap_sources import validate_bundle
    old = validate_bundle(cache['values'], cache['refs'], cache['graph'])
    require(value.get('authority_source') == ready['authority_source'] and value.get('archive') == old['archive'] and
        value.get('dvc_pointer') == old['dvc_pointer'] and value.get('pointer_raw_hex') == old['pointer_raw_hex'] and
        value.get('actual_remote_verified') is True and value.get('local_archive_created') is False and
        value.get('compressed_md5') == old['dvc_pointer']['oid'], 'exact remotely verified predecessor carry identity differs')
    members = value.get('members')
    require(type(members) is list and [r.get('original_member') for r in members] == required_members(old['graph']) and
        len({r.get('copy_member') for r in members}) <= len(members), 'exact required predecessor source set differs')
    manifest = {r['path']: r for r in old['archive']['manifest']}
    for row in members:
        original, copy = row.get('original_member'), row.get('copy_member')
        require(set(row) == {'original_path', 'original_member', 'sha256', 'bytes', 'copy_member'} and
            row['original_path'] == str(lab.ROOT / original) and original in manifest and
            row['sha256'] == manifest[original]['sha256'] and type(row['bytes']) is int and
            row['bytes'] == manifest[original]['bytes'] and type(copy) is str and not Path(copy).is_absolute() and
            '..' not in Path(copy).parts and store.digests.get(copy) == row['sha256'], 'actual carried predecessor bytes differ')
        if original.endswith('.json'):
            require(strict_equal(store.data.get(copy), old['graph']['data'][original]), 'carried predecessor JSON semantics differ')
    authorities = value.get('authorities')
    require(type(authorities) is list and {r.get('role') for r in authorities} == {'remote', 'checkpoint'} and
        len(authorities) == 2, 'exact actual predecessor review and checkpoint bytes required')
    for row in authorities:
        require(set(row) == {'role', 'original_path', 'sha256', 'bytes', 'copy_member'} and
            {'path': row['original_path'], 'sha256': row['sha256']} == old['predecessor'][row['role']] and
            type(row['bytes']) is int and row['bytes'] > 0 and store.digests.get(row['copy_member']) == row['sha256'] and
            strict_equal(store.data.get(row['copy_member']), old['values'][row['role']]),
            'actual carried predecessor checkpoint/review bytes differ')
    journals = value.get('journals')
    require(type(journals) is list and len(journals) == 2 and {r.get('original_member') for r in journals} ==
        {'tracking/packets.jsonl', 'tracking/events.jsonl'}, 'both carried actual predecessor journals required')
    # Actual remote review reads the carried raw journals and replays UI171 again.
    raw_journals = getattr(store, 'raw_journals', {})
    graph = deepcopy(old['graph'])
    from . import item_actionbar_evidence as evidence
    tracking = evidence.tracking_state()
    tracking.update(digests=graph['digests'], manifest=graph['tracking']['manifest'])
    for row in journals:
        expected = old['journal_manifest'][row['original_member']]
        require(set(row) == {'original_member', 'sha256', 'bytes', 'copy_member'} and
            row['sha256'] == expected['sha256'] and type(row['bytes']) is int and
            row['bytes'] == expected['bytes'] and store.digests.get(row['copy_member']) == row['sha256'],
            'complete original predecessor journal differs from first-stream authority')
        lines = raw_journals.get(row['copy_member'])
        if lines is None and store.local:
            path = lab.ROOT / row['copy_member']
            require(bound(path)['sha256'] == row['sha256'] and path.stat().st_size == row['bytes'], 'local carried journal changed')
            lines = [json.loads(line) for line in path.read_text().splitlines()]
        require(type(lines) is list, 'actual carried raw predecessor journal absent')
        evidence.collect(row['original_member'], lines, graph['data'], tracking)
    require(evidence.proof(graph['data'], graph['digests'], tracking) == old['remote_proof'],
        'actual carried source-owned predecessor journals no longer prove UI171')
    return True


def journal_snapshot(directory, closure):
    """Retain complete source-owned gameplay journals before shared publication."""
    from .observation.journal import entries
    from .bag_swap_evidence import local_store
    directory, closure = Path(directory), Path(closure)
    value = closed(closure)
    ready = local_store().get(value['sources']['preparation'])
    target = directory / 'journals'
    require(value.get('phase') == 'bags_swap_closed_paused' and not target.exists(), 'one new closed current journal capture required')
    target.mkdir(mode=0o700)
    refs = {}
    for kind, path in (('packets', lab.ROOT / 'evidence/world_packets.jsonl'), ('events', lab.ROOT / 'logs/modern_world.jsonl')):
        selected = [r for r in entries(path) if type(r.get('time')) in (int, float) and
            ready['started_at'] <= r['time'] <= value['finished_at']]
        require(selected and len(selected) <= 250000 and not any('AUTH_SESSION' in str(r.get('name', '')) and
            'body' in r for r in selected), 'current journal capture must be bounded gameplay without authentication bodies')
        copy = target / (kind + '.jsonl')
        write_exclusive(copy, ''.join(json.dumps(r, separators=(',', ':')) + '\n' for r in selected).encode())
        refs[kind] = bound(copy)
    # This is a distinct closed read-only journal receipt. The closed gameplay
    # source remains immutable; evidence resolves the receipt by its exact ref.
    receipt = directory / 'journal_receipt.json'
    write_exclusive(receipt, (json.dumps({'schema': 'client442_bag_swap_journals_v1',
        'closure_source': bound(closure), 'journal_sources': refs}, indent=2) + '\n').encode())
    return refs


def checkpoint(directory, name):
    from .checkpoint_interactions import checkpoint as publish
    return publish(Path(directory), name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['carry', 'journals', 'checkpoint'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--preparation', type=Path)
    parser.add_argument('--closure', type=Path)
    parser.add_argument('--name')
    a = parser.parse_args()
    if a.action == 'carry':
        require(a.preparation, 'carry requires its exact ready source')
        result = carry(a.directory, a.preparation)
        print(json.dumps({'carried_members': len(result['members']), 'qualification_added': False}), flush=True)
    elif a.action == 'journals':
        require(a.closure, 'journals requires the immutable closed pause')
        print(json.dumps(journal_snapshot(a.directory, a.closure)), flush=True)
    else:
        require(type(a.name) is str and a.name, 'checkpoint requires its explicit archive name')
        checkpoint(a.directory, a.name)


if __name__ == '__main__':
    main()
