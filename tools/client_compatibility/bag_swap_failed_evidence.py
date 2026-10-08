"""Pure portable proof of an excluded failed entry, owned stop and full journals."""
import ast
import json
from pathlib import Path

from . import bag_swap_failed_sources as sources
from .item_actionbar_contract import require, finite, strict_equal

ROOT = sources.ROOT
ANCESTRY_SCHEMA = 'client442_bag_swap_ancestry_v1'
JOURNAL_SCHEMA = 'client442_bag_swap_failed_journals_v1'
PROOF_SCHEMA = 'client442_bag_swap_failed_checkpoint_proof_v1'
TRACKING_MEMBERS = ('tracking/packets.jsonl', 'tracking/events.jsonl')
PLAN = 'experiments/configs/client_harness/442_interactions_v1.json'
MAX_ROWS, MAX_BYTES = 250000, 256 * 1024 * 1024
PUBLICATION_FILES = tuple(sorted((
    'tools/client_compatibility/checkpoint_bag_swap_failed.py',
    'tools/client_compatibility/bag_swap_failed_evidence.py',
    'tools/client_compatibility/bag_swap_failed_journals.py',
    'tools/client_compatibility/review_bag_swap_failed_checkpoint.py',
    'tools/client_compatibility/world/tests/test_bag_swap_failed_checkpoint.py',
    'tools/client_compatibility/world/tests/test_bag_swap_failed_publication.py',
    'tools/client_compatibility/world/tests/test_bag_swap_failed_journals.py')))
PUBLICATION_DEPENDENCIES = tuple(sorted((
    'tools/client_compatibility/checkpoint_interactions.py',
    'tools/client_compatibility/checkpoint_item_actionbar.py',
    'tools/client_compatibility/review_hunter_learn_checkpoint.py',
    'tools/client_compatibility/archive_integrity.py',
    'tools/client_compatibility/item_actionbar_evidence.py',
    'tools/client_compatibility/item_actionbar_sources.py',
    'tools/client_compatibility/hunter_learn_sources.py',
    'tools/client_compatibility/hunter_learn_contract.py',
    'tools/client_compatibility/interaction_metrics.py',
    'tools/client_compatibility/native_input/control.py', PLAN)))
_CLOSURE_SOURCE = {'path': str(ROOT / 'evidence/client_interactions_20261008_ui172/failed_pause01/episode.json'),
    'sha256': '723c3df1a161e70126bc1c062289f5628223490c12666ee5df3d69ed5ec30012'}
RECEIPT_FIELDS = frozenset(('schema', 'closure_source', 'preparation_source', 'started_at', 'finished_at',
    'completed', 'failure', 'controller', 'model', 'revision', 'actor', 'runtime', 'code_commit',
    'code_source_epoch', 'input_sent', 'mutation_sent', 'qualification_added', 'operations_admitted',
    'excluded_failed_entry', 'journal_interval', 'journal_sources', 'journal_proof'))


class Sources:
    """Resolve immutable original references from supplied verified archive bytes."""
    def __init__(self, data, digests, raw_journals=None, root=None):
        require(type(data) is dict and type(digests) is dict, 'supplied source JSON and byte digests required')
        self.data, self.digests = data, digests
        self.raw_journals, self.root, self.local = raw_journals or {}, Path(root or ROOT), False
        self.maps = [v for v in data.values() if type(v) is dict and v.get('schema') == ANCESTRY_SCHEMA]

    def member(self, ref):
        sources.reference(ref)
        path = Path(ref['path'])
        require(path.is_relative_to(self.root / 'evidence'), 'original source must remain private evidence')
        member = str(path.relative_to(self.root))
        if self.digests.get(member) == ref['sha256']:
            return member
        require(len(self.maps) == 1, 'one exact carried UI171 ancestry map required')
        rows = [r for r in self.maps[0].get('members', []) if type(r) is dict and
            r.get('original_path') == ref['path'] and r.get('sha256') == ref['sha256']]
        require(len(rows) == 1 and type(rows[0].get('copy_member')) is str,
            'exact original source absent or ambiguous in carried graph')
        member = rows[0]['copy_member']
        require(not Path(member).is_absolute() and '..' not in Path(member).parts and
            self.digests.get(member) == ref['sha256'], 'carried original source byte digest differs')
        return member

    def get(self, ref, successful=True):
        member = self.member(ref)
        require(member in self.data and type(self.data[member]) is dict, 'actual source JSON bytes absent')
        value = self.data[member]
        if successful:
            require(value.get('completed') is True and value.get('failure') is None, 'successful immutable source required')
        return value

    def journal(self, ref):
        member = self.member(ref)
        require(type(self.raw_journals.get(member)) is list, 'full byte-bound original journal absent')
        return self.raw_journals[member]


def source_ref(store, value):
    members = [m for m, v in store.data.items() if v is value]
    require(len(members) == 1, 'one exact source-owned archived receipt required')
    ref = {'path': str(store.root / members[0]), 'sha256': store.digests.get(members[0])}
    sources.reference(ref)
    return ref


def publication_epoch(store, value, closure):
    epoch = value.get('code_source_epoch')
    require(type(epoch) is dict and set(epoch) == {'code_commit', 'committed_sources', 'carried_sources'} and
        epoch['code_commit'] == value.get('code_commit') and epoch['code_commit'] != closure.get('code_commit'),
        'distinct actual publication code epoch required')
    sources._commit(epoch['code_commit'])
    repo = sources._repo(store.get(closure['original_preparation_source'], False))
    original = closure.get('committed_sources')
    original_paths = sources._vector(original, repo)
    require(original_paths == sorted(original_paths) and not set(PUBLICATION_FILES) & set(original_paths),
        'immutable pause must retain its original source package unchanged')
    wanted = sorted(set(original_paths) | set(PUBLICATION_FILES) | set(PUBLICATION_DEPENDENCIES))
    actual = epoch['committed_sources']
    require(sources._vector(actual, repo, wanted) == wanted and
        {r['path']: r['sha256'] for r in actual if str(Path(r['path']).relative_to(repo)) in original_paths} ==
            {r['path']: r['sha256'] for r in original}, 'publication requires exact old pause bytes and the complete new source dependency package')
    copies = epoch['carried_sources']
    require(type(copies) is list and len(copies) == len(actual) and
        len({r.get('path') for r in copies if type(r) is dict}) == len(copies), 'one distinct complete raw code envelope per publication source required')
    total = 0
    for ref, copy in zip(actual, copies):
        envelope = store.get(copy, False)
        require(set(envelope) == sources.CODE_FIELDS and envelope.get('schema') == sources.CODE_SCHEMA and
            envelope.get('code_commit') == epoch['code_commit'] and envelope.get('original_path') == ref['path'] and
            envelope.get('sha256') == ref['sha256'], 'publication raw code member differs from its actual epoch')
        raw = sources._raw(envelope['raw_hex'], envelope['sha256'], envelope['bytes'])
        total += len(raw)
        require(total <= sources.MAX_TOTAL_BYTES, 'bounded complete publication source epoch exceeded')
    return {'code_commit': epoch['code_commit'], 'member_count': len(actual), 'complete_raw_bytes_verified': True}


def validate_journal_receipt(store, value, closure, ready):
    require(type(value) is dict and set(value) == RECEIPT_FIELDS and value.get('schema') == JOURNAL_SCHEMA and
        value.get('completed') is True and value.get('failure') is None and finite(value.get('started_at')) and
        finite(value.get('finished_at')) and closure['finished_at'] < value['started_at'] < value['finished_at'] and
        value.get('closure_source') == source_ref(store, closure) == _CLOSURE_SOURCE and
        value.get('preparation_source') == closure['original_preparation_source'] and
        strict_equal(value.get('actor'), ready['actor']) and strict_equal(value.get('runtime'), ready['runtime']) and
        value.get('controller') == 'code' and value.get('model') is None and value.get('revision') is None and
        all(value.get(k) is False for k in ('input_sent', 'mutation_sent', 'qualification_added')) and
        value.get('excluded_failed_entry') is True and type(value.get('operations_admitted')) is int and
        value['operations_admitted'] == 0 and value.get('journal_interval') ==
            {'from': ready['started_at'], 'until': closure['finished_at']}, 'one successful excluded source-bound complete journal receipt required')
    refs = value.get('journal_sources')
    require(type(refs) is dict and set(refs) == {'packets', 'events'}, 'both current source-owned complete journal copies required')
    raw = {key: store.journal(ref) for key, ref in refs.items()}
    original = {key: store.journal(ref) for key, ref in closure['journal_sources'].items()}
    failed = store.get(closure['original_entry_source'], False)
    from .bag_swap_failed_journals import validate_journals
    result = validate_journals(raw['packets'], raw['events'], ready, failed, closure,
        original['packets'], original['events'])
    require(strict_equal(result, value.get('journal_proof')), 'new complete journal proof differs from actual byte-bound rows')
    return {'journal_proof': result, 'publication_code': publication_epoch(store, value, closure)}


def tracking_state():
    return {'members': set(), 'packets': [], 'events': [], 'raw_journals': {}, 'journal_counts':
        {member: {'rows': 0, 'bytes': 0, 'sha256': None} for member in TRACKING_MEMBERS}}


def collect(member, lines, data, tracking):
    require(member in TRACKING_MEMBERS and member not in tracking['members'], 'two distinct whole tracking journals required')
    rows = tracking['packets' if member == TRACKING_MEMBERS[0] else 'events']
    total = 0
    for row in lines:
        require(type(row) is dict and finite(row.get('time')), 'every whole tracking row must be an object with finite typed time')
        total += len(json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()) + 1
        require(len(rows) < MAX_ROWS and total <= MAX_BYTES, 'bounded whole tracking journal exceeded')
        rows.append(row)
    tracking['members'].add(member)


def _code_bytes(store, value, relative):
    epoch = value['code_source_epoch']
    pairs = [(ref, copy) for ref, copy in zip(epoch['committed_sources'], epoch['carried_sources'])
        if ref['path'].endswith('/' + relative)]
    require(len(pairs) == 1, 'one actual byte-bound publication dependency required: ' + relative)
    envelope = store.get(pairs[0][1], False)
    return sources._raw(envelope['raw_hex'], envelope['sha256'], envelope['bytes'])


def _metadata(store, value, tracking):
    metadata, prefix = tracking.get('archived_metadata'), tracking.get('batch_prefix')
    require(type(metadata) is dict and metadata.get('code_commit') == value['code_commit'] and
        type(prefix) is str and prefix.endswith('/'), 'actual archive publisher code and batch prefix required')
    try:
        def invalid(constant): raise ValueError(constant)
        plan = json.loads(_code_bytes(store, value, PLAN), parse_constant=invalid)
    except (ValueError, UnicodeDecodeError) as error:
        raise RuntimeError('actual byte-bound interaction plan must be complete finite JSON') from error
    require(type(plan) is dict and plan.get('schema') == 'client442_interactions_v1' and
        type(plan.get('qualified_operations')) is int and plan['qualified_operations'] == 453 and
        type(plan.get('cases')) is list and len(plan['cases']) == 916 and
        all(type(case) is dict and type(case.get('id')) is str for case in plan['cases']) and
        len({case['id'] for case in plan['cases']}) == 916 and type(plan.get('qualification_records')) is list and
        all(type(record) is dict and type(record.get('operations')) is list and
            all(type(operation) is str for operation in record['operations']) for record in plan['qualification_records']),
        'unchanged typed 453-qualified/916-operation interaction plan required')
    qualified = {operation for record in plan['qualification_records'] for operation in record['operations']}
    require(len(qualified) == 453 and qualified <= {case['id'] for case in plan['cases']} and
        'bags.swap_item' not in qualified and
        len([case for case in plan['cases'] if case['id'] == 'bags.swap_item' and
            case.get('family') == 'bags' and case.get('operation') == 'swap_item' and
            case.get('automation') == 'pending_adapter']) == 1,
        'bags.swap_item must remain unqualified in the actual carried interaction plan')
    runs = []
    members = sorted(member for member in tracking['manifest'] if member.startswith(prefix) and member.endswith('/episode.json'))
    require(members, 'all current batch ordinary Trial episode bytes required')
    for member in members:
        run = store.data.get(member)
        require(type(run) is dict and {'cases', 'cleanup', 'qualification_added', 'completed', 'failure',
            'controller', 'model', 'revision'} <= set(run) and finite(run.get('started_at')) and
            finite(run.get('finished_at')) and 0 < run['started_at'] < run['finished_at'] and
            strict_equal(run.get('cases'), []) and strict_equal(run.get('cleanup'), []) and
            run.get('qualification_added') is False and ('operations_admitted' not in run or
                type(run['operations_admitted']) is int and run['operations_admitted'] == 0) and
            type(run.get('completed')) is bool and (run.get('failure') is None if run['completed'] else
                type(run.get('failure')) is str and bool(run['failure'])) and
            run.get('controller') == 'code' and run.get('model') is None and run.get('revision') is None,
            'every manifested current batch Trial must retain empty cases, exclusion and truthful completion')
        runs.append({'path': member, **{key: run[key] for key in ('completed', 'failure', 'controller', 'model', 'revision')}})
    require(strict_equal(metadata.get('runs'), runs) and strict_equal(metadata.get('counts'), {}) and
        type(metadata.get('qualified_fixture_operations')) is int and metadata['qualified_fixture_operations'] == 453 and
        type(metadata.get('interaction_plan_operations')) is int and metadata['interaction_plan_operations'] == 916,
        'actual archived batch runs/counts/qualification totals differ from byte-bound sources')
    return {'qualified_fixture_operations': 453, 'interaction_plan_operations': 916,
        'bags_swap_item_unqualified': True, 'current_batch_episode_count': len(runs), 'current_batch_cases': 0}


def _generic_journals(store, value, closure, ready, tracking):
    require(tracking.get('members') == set(TRACKING_MEMBERS), 'both byte-verified current tracking journals required')
    require(type(tracking.get('archived_metadata')) is dict and
        tracking['archived_metadata'].get('code_commit') == value['code_commit'],
        'actual archive publisher code must match its carried publication source epoch')
    current = {key: store.journal(ref) for key, ref in value['journal_sources'].items()}
    require(all(type(row) is dict and finite(row.get('time')) for key in ('packets', 'events')
        for row in tracking[key]), 'every complete generic tracking row requires finite typed time before scoping')
    scoped = {key: [row for row in tracking[key] if
        ready['started_at'] <= row['time'] <= closure['finished_at']] for key in ('packets', 'events')}
    require(strict_equal(scoped['events'], current['events']), 'whole current event copy differs from actual generic archive events')
    publisher = 'tools/client_compatibility/checkpoint_interactions.py'
    raw = _code_bytes(store, value, publisher)
    assignments = [node.value for node in ast.parse(raw).body if isinstance(node, ast.Assign) and
        any(isinstance(target, ast.Name) and target.id == 'SAFE_BODY_NAMES' for target in node.targets)]
    require(len(assignments) == 1, 'actual publisher must declare one literal safe-body allowlist')
    allowed = ast.literal_eval(assignments[0])
    require(type(allowed) is set and all(type(name) is str for name in allowed), 'typed actual publisher safe-body names required')
    expected = [row for row in current['packets'] if 'body' not in row or row.get('name') in allowed]
    require(strict_equal(scoped['packets'], expected), 'generic packets differ from exact actual publisher-filtered complete current rows')
    for member in TRACKING_MEMBERS:
        row = tracking.get('manifest', {}).get(member)
        require(type(row) is dict and store.digests.get(member) == row.get('sha256') and
            tracking['journal_counts'][member] == {'rows': len(tracking['packets' if member == TRACKING_MEMBERS[0] else 'events']),
                'bytes': row['bytes'], 'sha256': row['sha256']}, 'actual complete tracking SHA256/bytes/count binding required')
    return {'both_tracking_journals_verified': True, 'tracking_journals': tracking['journal_counts']}


def proof(data, digests, tracking):
    store = Sources(data, digests, tracking.get('raw_journals', {}))
    closed = [v for v in data.values() if type(v) is dict and v.get('schema') == sources.SCHEMA and v.get('phase') == sources.PHASE]
    receipts = [v for v in data.values() if type(v) is dict and v.get('schema') == JOURNAL_SCHEMA]
    require(len(closed) == len(receipts) == 1, 'one excluded closed pause and one distinct complete journal receipt required')
    closure, receipt = closed[0], receipts[0]
    require(source_ref(store, closure) == _CLOSURE_SOURCE, 'actual immutable excluded closed pause bytes changed')
    excluded = sources.validate_failed_pause(store, closure)
    ready = store.get(closure['original_preparation_source'], False)
    from .checkpoint_bag_swap import validate_carry
    require(validate_carry(store, ready) is True, 'full actual UI171 predecessor byte carry required')
    journals = validate_journal_receipt(store, receipt, closure, ready)
    metadata = _metadata(store, receipt, tracking)
    generic = _generic_journals(store, receipt, closure, ready, tracking)
    return {'schema': PROOF_SCHEMA, **excluded, **journals, **metadata, **generic, 'qualification_added': False,
        'closed_pause_source': source_ref(store, closure), 'journal_receipt_source': source_ref(store, receipt),
        'original_ui171_raw_journals_verified': True}
