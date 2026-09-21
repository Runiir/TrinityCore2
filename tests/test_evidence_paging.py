import json
import shlex
import io
import tarfile

from tools.raid_program.evidence_paging import bounded_select, command_with, encoded
from tools.raid_program.evidence_view import main
from test_evidence_view import calibration, sim, timeline


def test_adaptive_pages_reconstruct_every_item():
    doc = {'rows': [{'id': i, 'text': 'x'*700} for i in range(31)]}
    offset, collected = 0, []
    while offset is not None:
        page = bounded_select(doc, '/rows', offset, 20, ['select', 'input.json'], 2000)
        assert len(encoded(page)) <= 2000
        collected.extend(page['value'])
        offset = page['next_offset']
        if offset is not None:
            assert '--offset ' + str(offset) in page['next_command']
    assert collected == doc['rows']


def test_nested_item_outline_uses_escaped_pointer():
    doc = {'rows': [{'a/b~c': list(range(10000))}]}
    result = bounded_select(doc, '/rows', 0, 10, ['select', 'input.json'], 2000)
    assert result['value'][0]['a/b~c']['path'] == '/rows/0/a~1b~0c'
    assert result['value'][0]['a/b~c']['items'] == 10000
    assert 'JSON_POINTER_FROM_VIEW' in result['detail_command_template']


def test_structure_only_fallback_respects_budget_for_large_objects():
    doc = {'rows': [{f'field_{i}': 'x' * 700 for i in range(16)}]}
    result = bounded_select(doc, '/rows', 0, 10, ['select', 'input.json'], 2000)
    assert len(encoded(result)) <= 2000
    assert result['view'] == 'structure_only_for_oversized_item'
    assert result['value']


def test_structure_only_fallback_fails_closed_for_locator_over_budget():
    key = 'segment_' + ('x' * 700)
    doc = {key: ['x' * 700]}
    result = bounded_select(doc, '/' + key, 0, 1, ['select', 'input.json'], 500)
    assert len(encoded(result)) <= 500
    assert result == {'view': 'budget_exceeded'}


def test_continuation_does_not_overwrite_export_and_quotes_input():
    command = command_with(['select', 'file with spaces.json', '--output', '/tmp/save.json', '--offset', '4'], offset=8)
    args = shlex.split(command)
    assert 'file with spaces.json' in args and '--output' not in args
    assert args[args.index('--offset')+1] == '8'


def test_equals_form_and_repeated_options_cannot_overwrite_full_export():
    command = command_with(['select', 'input.json', '--output=/tmp/full.json', '--offset=3',
                            '--output', '/tmp/other.json', '--offset', '5'], offset=8)
    args = shlex.split(command)
    assert not any(arg.startswith('--output') for arg in args)
    assert not any(arg.startswith('--offset=') for arg in args)
    assert args.count('--offset') == 1 and args[-2:] == ['--offset', '8']


def test_every_existing_evidence_command_exports(tmp_path, capsys):
    source = tmp_path/'source.json'; source.write_text(json.dumps(timeline()))
    for command in (['inspect', str(source)], ['events', str(source)], ['select', str(source), '--path', '/events']):
        dest = tmp_path/'out.json'
        main(command + ['--output', str(dest)])
        assert json.loads(dest.read_text())
        assert len(capsys.readouterr().out) < 12000


def test_compare_large_top_adapts_and_detail_is_complete(tmp_path, capsys):
    current, reference = tmp_path/'native.json', tmp_path/'sim.json'
    current.write_text(json.dumps(calibration()))
    reference.write_text(json.dumps(sim()))
    base = ['compare', '--current', str(current), '--wowsims', str(reference), '--top', '30']
    main(base + ['--max-chars', '4000'])
    result = json.loads(capsys.readouterr().out)
    assert result['reconciliation'] if 'reconciliation' in result else result['pairs'][0]['reconciliation']
    detail = shlex.split(result['detail_command'])[5:]
    main(detail)
    page = json.loads(capsys.readouterr().out)
    assert page['total_items'] == 1  # spell bucket retains separate proc/owner metrics within it
    assert page['path'] == '/pairs/0/components'
    assert page['sources']['current']['payload_sha256']


def test_archive_inventory_continuations_reach_members_after_first_fifty(tmp_path, capsys):
    archive_path = tmp_path/'many.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as archive:
        for i in range(57):
            info = tarfile.TarInfo(f'run/{i}/report.json'); info.size = 2
            archive.addfile(info, io.BytesIO(b'{}'))
    args = ['inspect', str(archive_path), '--limit', '20']
    names = []
    while True:
        main(args)
        result = json.loads(capsys.readouterr().out)
        names.extend(row['member'] for row in result['value'])
        if result['next_offset'] is None:
            break
        args = shlex.split(result['next_command'])[5:]
    assert names == [f'run/{i}/report.json' for i in range(57)]


def test_nested_inspect_lists_all_fields_without_values(tmp_path, capsys):
    path = tmp_path/'raw.json'
    doc = {'bot': {f'field_{i}': {'payload': 'large-private-value'*10000} for i in range(65)}}
    doc['bot']['a/b~c'] = [1, 2]
    path.write_text(json.dumps(doc))
    main(['inspect', str(path), '--path', '/bot', '--limit', '100'])
    output = capsys.readouterr().out
    page = json.loads(output)
    assert len(output) < 12000 and 'large-private-value' not in output
    assert page['total_items'] == 66 and page['next_offset'] is None
    assert page['value'][-1]['path'] == '/bot/a~1b~0c'
    assert page['value'][-1]['items'] == 2
    assert page['source']['payload_sha256']
