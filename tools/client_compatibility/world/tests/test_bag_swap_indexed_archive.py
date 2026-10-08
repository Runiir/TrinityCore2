"""Small raw archives exercise keyspace, class and complete-stream boundaries."""
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from tools.client_compatibility import bag_swap_indexed_archive as archive
from tools.client_compatibility import bag_swap_indexed_sources as provider
from tools.client_compatibility import bag_swap_source_index as index


def digest(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value): return (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode()


def packed(files, *, extra=(), tail=b'', metadata=True):
    files = dict(files)
    rows = [{'path': name, 'bytes': len(raw), 'sha256': digest(raw)} for name, raw in sorted(files.items())
        if not name.startswith('tracking/')]
    if metadata: files['tracking/checkpoint.json'] = encoded({'schema':'client442_interaction_checkpoint_v1','files':rows})
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in files.items():
            info = tarfile.TarInfo(name); info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
        for info, raw in extra: tar.addfile(info, io.BytesIO(raw) if raw is not None else None)
    raw = gzip.compress(target.getvalue()+tail, mtime=0)
    cp = {'file':provider.POINTER.removesuffix('.dvc'), 'cloud_verified':True,
        'bytes':len(raw), 'sha256':digest(raw),
        'file_manifest':[{'path':name,'bytes':len(value),'sha256':digest(value)} for name,value in sorted(files.items())]}
    return raw, cp, files


@pytest.fixture
def carried(tmp_path, monkeypatch):
    root = tmp_path/'root'; root.mkdir()
    monkeypatch.setattr(provider, 'ROOT', root)
    parent = 'evidence/client_interactions_20261008_ui173/'
    closure_member = parent+'stopped_closure01/episode.json'
    files = {closure_member: encoded({'completed':True,'failure':None,'value':'parent'}),
        parent+'duplicate.json':encoded({'completed':True,'failure':None,'value':'parent'}),
        parent+'frame.png':b'\x89PNG\r\n\x1a\nsmall-fixture', parent+'empty.log':b'',
        parent+'json_copy.log':encoded({'completed':True,'failure':None,'value':'parent'}),
        'tracking/owned_entry_request_packets.jsonl':b'',
        'tracking/owned_pet_abandon_packets.jsonl':b'',
        'tracking/owned_tame_request_packets.jsonl':b'',
        'tracking/packets.jsonl':encoded({'time':1,'packet':'parent'}),
        'tracking/events.jsonl':encoded({'time':1,'event':'parent'})}
    blobs = {}
    aliases = []
    for member, raw in sorted(files.items()):
        if member.startswith('tracking/') or member == parent+'json_copy.log': continue
        sha = digest(raw)
        blobs.setdefault(sha, {'member':member,'source_member':member,'sha256':sha,
            'bytes':len(raw),'kind':index._ordinary_kind(member)})
        aliases.append({'scope':'ui173','original_path':str(root/member),'original_member':member,
            'sha256':sha,'bytes':len(raw),'blob':blobs[sha]['member']})
    value = {'schema':index.SCHEMA,'blobs':list(blobs.values()),
        'scopes':[{'id':'ui171','parent':None},{'id':'ui172','parent':'ui171'},{'id':'ui173','parent':'ui172'}],
        'aliases':aliases}
    index_member = parent+'stopped_closure01/source_index.json'
    files[index_member] = encoded(value)
    raw, cp, files = packed(files)
    cp_path = root/parent/'checkpoint_receipt.json'; cp_path.parent.mkdir(parents=True)
    cp_path.write_bytes(encoded(cp)); cp_ref = provider.bound(cp_path)
    pointer_raw = (f'outs:\n- md5: {hashlib.md5(raw).hexdigest()}\n  size: {len(raw)}\n  hash: md5\n'
        f'  path: {Path(cp["file"]).name}\n').encode()
    pointer = {'source':{'path':str(tmp_path/provider.POINTER),'sha256':digest(pointer_raw)},
        'pointer':provider.POINTER,'oid':hashlib.md5(raw).hexdigest(),'bytes':len(raw)}
    remote = {'schema':'client442_bag_swap_stopped_remote_review_v1', 'checkpoint_source':cp_ref,
        'actual_remote_verified':True,'complete_manifest_verified':True,'pointer':provider.POINTER,
        'pointer_sha256':digest(pointer_raw),'object_md5':pointer['oid'],'bytes':len(raw),'archive_sha256':digest(raw)}
    remote_path = root/'evidence/ui173_stopped_remote.json'; remote_path.write_bytes(encoded(remote))
    predecessor = {'closure':{'path':str(root/closure_member),'sha256':digest(files[closure_member])},
        'checkpoint':cp_ref,'remote':provider.bound(remote_path),
        'primary_stop':{'path':str(root/'evidence/primary_stop.json'),'sha256':'1'*64}}
    source_ref = {'path':str(root/index_member),'sha256':digest(files[index_member])}
    batch = root/'evidence/client_interactions_20261008_ui174'; batch.mkdir()
    ref = archive.carry_archive(io.BytesIO(raw), cp, parent, batch, predecessor, source_ref,
        pointer, pointer_raw.hex(), {k:predecessor[k] for k in ('checkpoint','remote')}, root=root)
    carry = json.loads(Path(ref['path']).read_text())
    return {'root':root,'batch':batch,'parent':parent,'carry':carry,'carry_ref':ref,
        'files':files,'raw':raw,'cp':cp,'predecessor':predecessor,'index_value':value,'index_member':index_member}


def test_carry_exact_full_manifest_dedup_and_unchanged_index(carried):
    c = carried
    rows = c['carry']['members']
    assert {r['original_member'] for r in rows} == set(c['files'])
    physical = list((c['batch']/archive.RAW_DIRECTORY).iterdir())
    assert len(physical) == len({r['sha256'] for r in rows+c['carry']['authorities']})
    copy = next(r for r in rows if r['original_member']==c['index_member'])
    assert (c['root']/copy['copy_member']).read_bytes() == c['files'][c['index_member']]
    assert not list(c['batch'].glob('*.gz'))
    assert set(c['carry']) == archive.FIELDS


def test_actual_empty_binary_three_journal_collision_has_one_copy_and_each_typed_view(carried):
    c = carried
    rows = [r for r in c['carry']['members'] if r['sha256'] == digest(b'')]
    assert len(rows) == 4 and {r['kind'] for r in rows} == {'binary', 'journal'}
    assert len({r['copy_member'] for r in rows}) == 1
    copy = rows[0]['copy_member']
    assert archive.validate_carry_manifest(c['carry'], c['root'])[copy] == (
        digest(b''), 0, frozenset(('binary', 'journal')))
    store = archive.local_sources(c['batch'], root=c['root'])
    assert copy not in store.data and store.raw_journals[copy] == []
    data, _, parent = archive.parent_view(store, c['carry'])
    for row in rows:
        assert row['original_member'] not in data
        if row['kind'] == 'journal': assert parent['raw_journals'][row['original_member']] == []
        else:
            assert row['original_member'] not in parent['raw_journals']
            with pytest.raises(RuntimeError, match='not a journal view'):
                store.journal({'path': row['original_path'], 'sha256': row['sha256']})


def test_identical_valid_json_binary_copy_keeps_original_views_and_rejects_log_json_alias(carried):
    c = carried
    log = next(r for r in c['carry']['members'] if r['original_member'].endswith('/json_copy.log'))
    rows = [r for r in c['carry']['members'] if r['sha256'] == log['sha256']]
    assert {r['kind'] for r in rows} == {'json', 'binary'}
    assert len({r['copy_member'] for r in rows}) == 1
    store = archive.local_sources(c['batch'], root=c['root'])
    assert store.get(c['predecessor']['closure'])['value'] == 'parent'
    with pytest.raises(RuntimeError, match='not an ordinary JSON view'):
        store.get({'path': log['original_path'], 'sha256': log['sha256']}, False)
    data, _, parent = archive.parent_view(store, c['carry'])
    assert log['original_member'] not in data and log['original_member'] not in parent['raw_journals']


@pytest.mark.parametrize('mutation', ['kind', 'size'])
def test_same_sha_views_reject_disguise_and_conflicting_byte_bindings(carried, mutation):
    c = carried; bad = deepcopy(c['carry'])
    row = next(r for r in bad['members'] if r['original_member'].endswith('/empty.log'))
    if mutation == 'kind': row['kind'] = 'journal'
    else:
        row['bytes'] = 1
        next(r for r in bad['archive']['manifest'] if r['path'] == row['original_member'])['bytes'] = 1
    with pytest.raises(RuntimeError): archive.validate_carry_manifest(bad, c['root'])


def test_shared_binary_view_does_not_hide_json_cap_before_decode(carried, monkeypatch):
    c = carried
    row = next(r for r in c['carry']['members'] if r['original_member'].endswith('/json_copy.log'))
    assert any(r['sha256'] == row['sha256'] and r['kind'] == 'json' for r in c['carry']['members'])
    monkeypatch.setattr(archive, 'MAX_JSON', row['bytes'] - 1)
    monkeypatch.setattr(archive, '_read', lambda *args: pytest.fail('oversized logical JSON view reached decoding'))
    with pytest.raises(RuntimeError, match='ordinary carried JSON exceeds'):
        archive._materialize({}, {}, c['carry'], c['root'])


def test_shared_physical_copy_runs_each_type_validation(carried, monkeypatch):
    c = carried; original = archive._read; seen = []
    def recorded(path, kind, size, *limits):
        seen.append((digest(Path(path).read_bytes()), size, kind))
        return original(path, kind, size, *limits)
    monkeypatch.setattr(archive, '_read', recorded)
    archive.local_sources(c['batch'], root=c['root'])
    assert seen.count((digest(b''), 0, 'binary')) == 1
    assert seen.count((digest(b''), 0, 'journal')) == 1
    raw = encoded({'completed':True,'failure':None,'value':'parent'})
    assert seen.count((digest(raw), len(raw), 'binary')) == 1
    assert seen.count((digest(raw), len(raw), 'json')) == 1


def test_outer_store_avoids_v1_autodetection_and_parent_restores_keys(carried):
    c = carried
    store = archive.local_sources(c['batch'], root=c['root'])
    assert store.local is True
    assert store.get(c['predecessor']['checkpoint'], False) == c['cp']
    assert store.member(c['predecessor']['closure']).endswith('.blob')
    with pytest.raises(RuntimeError, match='indexed physical payload'):
        index.Sources(store.data, store.digests, store.raw_journals, paths=store.paths, root=c['root'])
    data, digests, tracking = archive.parent_view(store, c['carry'])
    assert data[c['index_member']] == c['index_value']
    assert tracking['manifest'] == {r['path']:r for r in c['cp']['file_manifest']}
    assert tracking['packets'] == [{'time':1,'packet':'parent'}]
    assert tracking['events'] == [{'time':1,'event':'parent'}]
    assert tracking['members'] == set(archive.failed.TRACKING_MEMBERS)
    assert tracking['journal_counts']['tracking/packets.jsonl']['sha256'] == digest(c['files']['tracking/packets.jsonl'])
    assert c['predecessor']['remote']['path'] == str(c['root']/next(r['original_member']
        for r in c['carry']['authorities'] if r['role']=='remote'))
    restored = index.Sources(data, digests, tracking['raw_journals'], paths=tracking['paths'], root=c['root'])
    assert restored.get(c['predecessor']['closure'])['value'] == 'parent'


def test_outer_archive_keeps_current_and_parent_tracking_separate(carried):
    c = carried; prefix = str(c['batch'].relative_to(c['root']))+'/'
    files = {str(p.relative_to(c['root'])):p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
    files.update({prefix+'current/episode.json':encoded({'value':'current'}), prefix+'current.png':b'\x89PNG\r\n\x1a\ncurrent',
        'tracking/packets.jsonl':encoded({'time':2,'packet':'current'}),
        'tracking/events.jsonl':encoded({'time':2,'event':'current'})})
    raw, cp, _ = packed(files)
    data, digests, current, count = archive.inspect_archive(io.BytesIO(raw), cp, prefix)
    try:
        assert count == len(raw) and current['packets'] == [{'time':2,'packet':'current'}]
        store = archive.Sources(data,digests,current['raw_journals'],current['paths'],c['root'],c['carry'])
        _, _, parent = archive.parent_view(store,c['carry'])
        assert parent['packets'] == [{'time':1,'packet':'parent'}]
        assert current['packets'] == [{'time':2,'packet':'current'}]
        assert parent['batch_prefix'] == c['parent'] and current['batch_prefix'] == prefix
    finally: current['_spool'].cleanup()


@pytest.mark.parametrize('mutation', ['missing','duplicate','kind','opaque','copy','multi_copy','pointer','authority','index_size','closure_pin'])
def test_carry_negative_bindings(carried, mutation):
    c = carried; bad = deepcopy(c['carry'])
    if mutation=='missing': bad['members'].pop()
    elif mutation=='duplicate': bad['members'][-1]=deepcopy(bad['members'][0])
    elif mutation=='kind': next(r for r in bad['members'] if r['kind']=='json')['kind']='binary'
    elif mutation=='opaque': next(r for r in bad['members'] if r['kind']=='json')['kind']='ui172_authority'
    elif mutation=='copy': bad['members'][0]['copy_member']='../escape.blob'
    elif mutation=='multi_copy':
        row = next(r for r in bad['members'] if r['original_member'].endswith('/duplicate.json'))
        row['copy_member']=row['copy_member'].replace(archive.RAW_DIRECTORY,'other_raw')
    elif mutation=='pointer': bad['pointer_raw_hex']='00'
    elif mutation=='authority': bad['authorities'][0]['role']=bad['authorities'][1]['role']
    elif mutation=='closure_pin': bad['predecessor']['closure']['sha256']='2'*64
    elif mutation=='index_size':
        member = c['index_member']; size=index.MAX_INDEX+1
        next(r for r in bad['archive']['manifest'] if r['path']==member)['bytes']=size
        next(r for r in bad['members'] if r['original_member']==member)['bytes']=size
    with pytest.raises(RuntimeError): archive.validate_carry_manifest(bad,c['root'])


def test_local_and_archive_raw_carry_whitespace_bound_predecode(carried, monkeypatch):
    c=carried; path=Path(c['carry_ref']['path']); normal=path.read_bytes()
    monkeypatch.setattr(provider,'MAX_CARRY_BYTES',len(normal)+4)
    path.write_bytes(normal+b' '*5)
    called=[]; original=archive._json
    def checked(raw):
        called.append(len(raw)); return original(raw)
    monkeypatch.setattr(archive,'_json',checked)
    with pytest.raises(RuntimeError,match='raw successor carry'): archive.local_sources(c['batch'],root=c['root'])
    assert called==[]
    prefix=str(c['batch'].relative_to(c['root']))+'/'
    files={str(p.relative_to(c['root'])):p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
    files.update({prefix+'entry/episode.json':b'{}\n',prefix+'frame.png':b'\x89PNG\r\n\x1a\n',
        'tracking/packets.jsonl':b'','tracking/events.jsonl':b''})
    raw,cp,_=packed(files)
    with pytest.raises(RuntimeError,match='raw-bounded successor carry'): archive.inspect_archive(io.BytesIO(raw),cp,prefix)
    assert called==[]


def test_declared_index_bound_rejects_before_local_decode(carried,monkeypatch):
    c=carried; actual=len(c['files'][c['index_member']])
    monkeypatch.setattr(index,'MAX_INDEX',actual-1)
    called=[]
    monkeypatch.setattr(index,'_source_json',lambda raw: called.append(raw) or json.loads(raw))
    # Carry itself is decoded, but no index payload is read or decoded.
    with pytest.raises(RuntimeError,match='unchanged original parent source index'):
        archive.local_sources(c['batch'],root=c['root'])
    assert len(called)==1 and json.loads(called[0])['schema']==archive.SCHEMA


def test_archive_declared_index_bound_precedes_blob_decode(carried,monkeypatch):
    c=carried; prefix=str(c['batch'].relative_to(c['root']))+'/'
    files={str(p.relative_to(c['root'])):p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
    files.update({prefix+'entry/episode.json':b'{}\n',prefix+'frame.png':b'\x89PNG\r\n\x1a\n',
        'tracking/packets.jsonl':b'','tracking/events.jsonl':b''})
    raw,cp,_=packed(files)
    monkeypatch.setattr(index,'MAX_INDEX',len(c['files'][c['index_member']])-1)
    called=[]; original=archive._json
    def checked(raw): called.append(raw);return original(raw)
    monkeypatch.setattr(archive,'_json',checked)
    with pytest.raises(RuntimeError,match='unchanged original parent source index'):
        archive.inspect_archive(io.BytesIO(raw),cp,prefix)
    assert len(called)==1 and json.loads(called[0])['schema']==archive.SCHEMA


def test_known_index_cap_rejects_before_parent_stream_or_destination(carried,monkeypatch):
    c=carried; batch=c['root']/'evidence/next-batch';batch.mkdir()
    monkeypatch.setattr(index,'MAX_INDEX',len(c['files'][c['index_member']])-1)
    class Untouched:
        def read(self,size): pytest.fail('oversized known index must reject before stream consumption')
    with pytest.raises(RuntimeError,match='raw-bounded unchanged parent index'):
        archive.carry_archive(Untouched(),c['cp'],c['parent'],batch,c['predecessor'],
            c['carry']['source_index_source'],c['carry']['dvc_pointer'],c['carry']['pointer_raw_hex'],
            {k:c['predecessor'][k] for k in ('checkpoint','remote')},root=c['root'])
    assert not list(batch.iterdir())


def test_parent_raw_mutation_and_symlink_are_rejected(carried):
    c=carried; store=archive.local_sources(c['batch'],root=c['root'])
    row=next(r for r in c['carry']['members'] if r['kind']=='json')
    path=c['root']/row['copy_member']; raw=path.read_bytes(); path.write_bytes(b' '+raw[1:])
    with pytest.raises(RuntimeError,match='changed after ingestion'): archive.parent_view(store,c['carry'])
    path.unlink(); path.symlink_to(Path(c['carry_ref']['path']))
    with pytest.raises(RuntimeError,match='links forbidden'): archive.local_sources(c['batch'],root=c['root'])


@pytest.mark.parametrize('change',['crc','truncated','trailing','concatenated','nonzero_tail','duplicate','link','unmanifested'])
def test_whole_archive_negative_boundaries(carried,tmp_path,change):
    c=carried; raw,cp=c['raw'],deepcopy(c['cp'])
    if change=='crc': raw=raw[:-8]+bytes([raw[-8]^1])+raw[-7:]
    elif change=='truncated': raw=raw[:-4]
    elif change=='trailing': raw+=b'x'
    elif change=='concatenated': raw+=gzip.compress(b'',mtime=0)
    else:
        extra=[]; tail=b''
        if change=='nonzero_tail': tail=b'x'+b'\0'*511
        else:
            name=next(iter(c['files'])) if change=='duplicate' else 'unmanifested.bin'
            info=tarfile.TarInfo(name)
            if change=='link': info.type=tarfile.SYMTYPE;info.linkname='target';extra=[(info,None)]
            else: info.size=1;extra=[(info,b'x')]
        raw,cp,_=packed(c['files'],extra=extra,tail=tail,metadata=False)
    cp['bytes'],cp['sha256']=len(raw),digest(raw)
    destination=tmp_path/'spool';destination.mkdir()
    with pytest.raises(RuntimeError): archive._stream(io.BytesIO(raw),cp,c['parent'],destination)


def test_unclassified_blob_cannot_evade_json_class(carried):
    c=carried; extra=c['batch']/'unclassified.blob';extra.write_bytes(b'{}\n')
    with pytest.raises(RuntimeError,match='unclassified blob'): archive.local_sources(c['batch'],root=c['root'])


def test_source_changed_during_json_decode_rejects(carried,monkeypatch):
    c=carried; original=archive._read; modified=[]
    def changing(path,kind,size,*limits):
        value=original(path,kind,size,*limits)
        if kind=='json' and not modified and Path(path).suffix=='.blob':
            raw=Path(path).read_bytes();Path(path).write_bytes(b' '+raw[1:]);modified.append(str(path))
        return value
    monkeypatch.setattr(archive,'_read',changing)
    with pytest.raises(RuntimeError,match='changed while decoding'):
        archive.local_sources(c['batch'],root=c['root'])
    assert modified


def test_original_blob_class_requires_unchanged_v1_index(carried):
    c=carried; bad=deepcopy(c['carry'])
    row=next(r for r in bad['members'] if r['kind']=='binary')
    member=row['original_member'];row['original_member']=member+'.blob';row['original_path']=str(c['root']/row['original_member'])
    next(r for r in bad['archive']['manifest'] if r['path']==member)['path']=row['original_member']
    archive.validate_carry_manifest(bad,c['root'])
    with pytest.raises(RuntimeError,match='unchanged parent v1 index'): archive._parent_classes(bad,c['index_value'],c['root'])


def test_only_exact_opaque_categories_skip_json_decode(tmp_path,monkeypatch):
    raw=b'{"core_sha256":"'+b'1'*64+b'","graph":{}}'
    path=tmp_path/'opaque.blob';path.write_bytes(raw)
    monkeypatch.setattr(index,'_OPAQUE_SOURCES',{'ui172_authority':{'source':{'sha256':digest(raw)},'bytes':len(raw),'core_sha256':'1'*64}})
    monkeypatch.setattr(archive,'_json',lambda raw: pytest.fail('opaque raw JSON must not be decoded'))
    assert archive._read(path,'ui172_authority',len(raw)) is None
    assert index._opaque_kind(digest(raw),len(raw))=='ui172_authority'
    assert index._opaque_kind(digest(raw),len(raw)+1) is None


@pytest.mark.parametrize('failure',['crc','metadata','publication'])
def test_failed_carry_cleans_only_new_staging_and_allows_retry(carried,monkeypatch,failure):
    c=carried;batch=c['root']/'evidence/retry-batch';batch.mkdir()
    unrelated=batch/'retained.txt';unrelated.write_text('preserve')
    raw=c['raw']
    undo=monkeypatch.context()
    with undo as patch:
        if failure=='crc': raw=raw[:-8]+bytes([raw[-8]^1])+raw[-7:]
        elif failure=='metadata': patch.setattr(archive,'_metadata',lambda *a: (_ for _ in ()).throw(RuntimeError('metadata negative')))
        else:
            link=archive.os.link
            def fail_manifest(source,target):
                if Path(target).name==archive.CARRY_NAME: raise OSError('manifest publication negative')
                return link(source,target)
            patch.setattr(archive.os,'link',fail_manifest)
        with pytest.raises((RuntimeError,OSError)):
            archive.carry_archive(io.BytesIO(raw),c['cp'],c['parent'],batch,c['predecessor'],
                c['carry']['source_index_source'],c['carry']['dvc_pointer'],c['carry']['pointer_raw_hex'],
                {k:c['predecessor'][k] for k in ('checkpoint','remote')},root=c['root'])
    assert list(batch.iterdir())==[unrelated] and unrelated.read_text()=='preserve'
    result=archive.carry_archive(io.BytesIO(c['raw']),c['cp'],c['parent'],batch,c['predecessor'],
        c['carry']['source_index_source'],c['carry']['dvc_pointer'],c['carry']['pointer_raw_hex'],
        {k:c['predecessor'][k] for k in ('checkpoint','remote')},root=c['root'])
    assert Path(result['path']).is_file() and unrelated.read_text()=='preserve'
    assert not list(batch.glob('.ui173-carry-*'))


@pytest.mark.parametrize('name,schema',[('authority.json',provider.CACHE_SCHEMA),
    ('runtime_authority.json',provider.RUNTIME_SCHEMA)])
def test_known_current_descriptor_runtime_caps_precede_decode_locally_and_in_archive(carried,monkeypatch,name,schema):
    c=carried;prefix=str(c['batch'].relative_to(c['root']))+'/'
    raw_value=encoded({'schema':schema})+b' '*100
    limit=len(raw_value)-1
    monkeypatch.setattr(provider,'MAX_DESCRIPTOR_BYTES',limit)
    monkeypatch.setattr(provider,'MAX_RUNTIME_BYTES',limit)
    target=c['batch']/'scout_resume01'/name;target.parent.mkdir();target.write_bytes(raw_value)
    original=archive._json;decoded=[]
    def tracked(raw):
        assert raw!=raw_value, 'oversized known role reached JSON decoder'
        decoded.append(len(raw));return original(raw)
    monkeypatch.setattr(archive,'_json',tracked)
    role = 'descriptor' if schema == provider.CACHE_SCHEMA else 'runtime'
    refs = {role: provider.bound(target)}
    with pytest.raises(RuntimeError,match='current descriptor/runtime raw source'):
        archive.local_sources(c['batch'],root=c['root'],role_refs=refs)
    files={str(p.relative_to(c['root'])):p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
    files.update({prefix+'entry/episode.json':b'{}\n',prefix+'frame.png':b'\x89PNG\r\n\x1a\n',
        'tracking/packets.jsonl':b'','tracking/events.jsonl':b''})
    raw,cp,_=packed(files)
    with pytest.raises(RuntimeError,match='current descriptor/runtime raw source'):
        archive.inspect_archive(io.BytesIO(raw),cp,prefix,role_refs=refs)


def successor_archive(c):
    prefix = str(c['batch'].relative_to(c['root'])) + '/'
    files = {str(p.relative_to(c['root'])): p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
    files.update({prefix + 'entry/episode.json': b'{}\n',
        prefix + 'frame.png': b'\x89PNG\r\n\x1a\n',
        'tracking/packets.jsonl': b'', 'tracking/events.jsonl': b''})
    raw, cp, _ = packed(files)
    return raw, cp, prefix


def prohibit_document_decode(monkeypatch, forbidden):
    decoded = []
    original = index._source_json
    def tracked(raw):
        assert raw not in forbidden, 'over-cap role entered complete JSON decoder'
        decoded.append(len(raw))
        return original(raw)
    monkeypatch.setattr(index, '_source_json', tracked)
    return decoded


@pytest.mark.parametrize('schema', [provider.CACHE_SCHEMA, provider.RUNTIME_SCHEMA])
def test_original_renamed_cap_observation_now_rejects_before_document_decode(carried, monkeypatch, schema):
    c = carried
    # Exact original reviewer mutation, including its >1MiB whitespace tail.
    raw = json.dumps({'schema': schema}).encode() + b' ' * (provider.MAX_RUNTIME_BYTES + 1)
    (c['batch'] / 'renamed_private_authority.json').write_bytes(raw)
    decoded = prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='exact raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'])
    compressed, cp, prefix = successor_archive(c)
    with pytest.raises(RuntimeError, match='exact raw byte bound before decode'):
        archive.inspect_archive(io.BytesIO(compressed), cp, prefix)
    assert len(raw) not in decoded


@pytest.mark.parametrize('role', ['descriptor', 'runtime'])
@pytest.mark.parametrize('name', ['a_renamed.json', 'resume.json', 'report.json', 'episode.json'])
def test_explicit_role_caps_precede_decoder_even_without_schema(carried, monkeypatch, role, name):
    c = carried
    raw = b'{}\n' + b' ' * 100
    path = c['batch'] / name
    path.write_bytes(raw)
    monkeypatch.setattr(provider, 'MAX_DESCRIPTOR_BYTES', len(raw) - 1)
    monkeypatch.setattr(provider, 'MAX_RUNTIME_BYTES', len(raw) - 1)
    refs = {role: provider.bound(path)}
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'], role_refs=refs)
    compressed, cp, prefix = successor_archive(c)
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        archive.inspect_archive(io.BytesIO(compressed), cp, prefix, role_refs=refs)


@pytest.mark.parametrize('anchor', ['resume', 'ready'])
def test_late_source_owned_roles_precede_all_materialization(carried, monkeypatch, anchor):
    c = carried
    raw = b'{}\n' + b' ' * 1000
    role = c['batch'] / 'a_renamed_role.json'
    role.write_bytes(raw)
    other = c['batch'] / 'runtime_without_writer_basename.json'
    other.write_bytes(b'{}\n')
    value = {'unrelated': {'schema': provider.CACHE_SCHEMA, 'phase': 'bags_swap_scout_ready'},
        'authority_source': provider.bound(role), 'runtime_authority_source': provider.bound(other)}
    value['schema' if anchor == 'resume' else 'phase'] = (
        'client442_bag_swap_scout_resume_v1' if anchor == 'resume' else 'bags_swap_scout_ready')
    if anchor == 'ready': value['schema'] = 'client442_laya_interactions_v1'
    (c['batch'] / 'z_late_anchor.json').write_bytes(encoded(value))
    monkeypatch.setattr(provider, 'MAX_DESCRIPTOR_BYTES', len(raw) - 1)
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'])
    compressed, cp, prefix = successor_archive(c)
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        archive.inspect_archive(io.BytesIO(compressed), cp, prefix)


@pytest.mark.parametrize('spelling', ['escaped', 'late', 'duplicate'])
def test_schema_cap_handles_escaped_late_and_duplicate_declarations(carried, monkeypatch, spelling):
    c = carried
    schema = json.dumps(provider.CACHE_SCHEMA).encode()
    if spelling == 'escaped': raw = b'{"\\u0073chema":' + schema + b'}'
    elif spelling == 'late': raw = b'{"irrelevant":{"schema":"ordinary","text":"}\\\"{"},"schema":' + schema + b'}'
    else: raw = b'{"schema":' + schema + b',"\\u0073chema":"ordinary"}'
    raw += b' ' * 100
    (c['batch'] / 'renamed_private_authority.json').write_bytes(raw)
    monkeypatch.setattr(provider, 'MAX_DESCRIPTOR_BYTES', len(raw) - 1)
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='exact raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'])


@pytest.mark.parametrize('mutation', ['missing_role', 'duplicate_role', 'explicit_conflict', 'wrong_sha', 'same_role_ref'])
def test_role_union_rejects_incomplete_ambiguous_or_changed_refs_before_decode(carried, monkeypatch, mutation):
    c = carried
    descriptor = c['batch'] / 'descriptor_renamed.json'; descriptor.write_bytes(b'{"value":"descriptor"}\n')
    runtime = c['batch'] / 'compact_renamed.json'; runtime.write_bytes(b'{"value":"runtime"}\n')
    refs = {'descriptor': provider.bound(descriptor), 'runtime': provider.bound(runtime)}
    value = {'schema': 'client442_bag_swap_scout_resume_v1', 'authority_source': refs['descriptor'],
        'runtime_authority_source': refs['runtime']}
    explicit = None
    if mutation == 'missing_role': del value['runtime_authority_source']
    elif mutation == 'wrong_sha': value['authority_source'] = {**refs['descriptor'], 'sha256': 'b' * 64}
    elif mutation == 'same_role_ref': value['runtime_authority_source'] = refs['descriptor']
    elif mutation == 'explicit_conflict': explicit = {'descriptor': refs['runtime']}
    raw = encoded(value)
    if mutation == 'duplicate_role':
        raw = raw.rstrip()[:-1] + b',"\\u0061uthority_source":' + encoded(refs['descriptor']).strip() + b'}\n'
    (c['batch'] / 'owner_receipt.json').write_bytes(raw)
    prohibit_document_decode(monkeypatch, [descriptor.read_bytes(), runtime.read_bytes(), raw])
    with pytest.raises(RuntimeError): archive.local_sources(c['batch'], root=c['root'], role_refs=explicit)


def test_nested_decoys_and_large_unrelated_ordinary_json_retain_original_limit(carried, monkeypatch):
    c = carried
    value = {'nested': {'schema': provider.CACHE_SCHEMA, 'phase': 'bags_swap_scout_ready',
        'authority_source': {'path': 'irrelevant'}}, 'text': 'ordinary ' * 100}
    path = c['batch'] / 'ordinary_large.json'; path.write_bytes(encoded(value))
    monkeypatch.setattr(provider, 'MAX_DESCRIPTOR_BYTES', 64)
    monkeypatch.setattr(provider, 'MAX_RUNTIME_BYTES', 64)
    store = archive.local_sources(c['batch'], root=c['root'])
    assert store.get(provider.bound(path), False) == value
    compressed, cp, prefix = successor_archive(c)
    data, _, tracking, _ = archive.inspect_archive(io.BytesIO(compressed), cp, prefix)
    try: assert data[str(path.relative_to(c['root']))] == value
    finally: tracking['_spool'].cleanup()


def test_bound_scanned_bytes_reject_changed_role_discovery(carried, monkeypatch):
    c = carried
    path = c['batch'] / 'source.json'; path.write_bytes(b'{}\n')
    original = archive._role_fields
    changed = []
    def mutate(raw):
        if raw == b'{}\n' and not changed:
            path.write_bytes(b'[]\n'); changed.append(True)
        return original(raw)
    monkeypatch.setattr(archive, '_role_fields', mutate)
    with pytest.raises(RuntimeError, match='changed while decoding'):
        archive.local_sources(c['batch'], root=c['root'])
    assert changed


def test_renamed_bound_roles_and_current_receipt_roundtrip_locally_and_portably(carried):
    c = carried
    descriptor = c['batch'] / 'report.json'; descriptor.write_bytes(encoded({'schema': provider.CACHE_SCHEMA}))
    runtime = c['batch'] / 'episode.json'; runtime.write_bytes(encoded({'schema': provider.RUNTIME_SCHEMA}))
    refs = {'descriptor': provider.bound(descriptor), 'runtime': provider.bound(runtime)}
    receipt = {'schema': 'client442_bag_swap_scout_resume_v1', 'authority_source': refs['descriptor'],
        'runtime_authority_source': refs['runtime']}
    (c['batch'] / 'z_resume.json').write_bytes(encoded(receipt))
    store = archive.local_sources(c['batch'], root=c['root'], role_refs=refs)
    assert store.get(refs['descriptor'], False)['schema'] == provider.CACHE_SCHEMA
    assert store.get(refs['runtime'], False)['schema'] == provider.RUNTIME_SCHEMA
    compressed, cp, prefix = successor_archive(c)
    data, _, tracking, _ = archive.inspect_archive(io.BytesIO(compressed), cp, prefix)
    try:
        assert data[str(descriptor.relative_to(c['root']))]['schema'] == provider.CACHE_SCHEMA
        assert data[str(runtime.relative_to(c['root']))]['schema'] == provider.RUNTIME_SCHEMA
    finally: tracking['_spool'].cleanup()


def test_actual_over_one_mib_unrelated_ordinary_json_remains_legal(carried):
    c = carried
    raw = b'{"ordinary":"' + b'x' * (provider.MAX_RUNTIME_BYTES + 1) + b'"}\n'
    path = c['batch'] / 'ordinary_large.json'; path.write_bytes(raw)
    store = archive.local_sources(c['batch'], root=c['root'])
    assert len(store.get(provider.bound(path), False)['ordinary']) == provider.MAX_RUNTIME_BYTES + 1


def test_duplicate_indexed_schema_within_cap_is_rejected_before_document_decode(carried, monkeypatch):
    c = carried
    raw = b'{"schema":' + json.dumps(provider.RUNTIME_SCHEMA).encode() + b',"\\u0073chema":"ordinary"}\n'
    (c['batch'] / 'renamed.json').write_bytes(raw)
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='unambiguous before decode'):
        archive.local_sources(c['batch'], root=c['root'])


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be',
    'utf-32', 'utf-32-le', 'utf-32-be'])
@pytest.mark.parametrize('schema', [provider.CACHE_SCHEMA, provider.RUNTIME_SCHEMA])
def test_all_accepted_json_encodings_enforce_schema_caps_before_document_decode(carried, monkeypatch, encoding, schema):
    c = carried
    raw = (json.dumps({'schema': schema}) + ' ' * 1000).encode(encoding)
    (c['batch'] / 'renamed_encoded_authority.json').write_bytes(raw)
    monkeypatch.setattr(provider, 'MAX_DESCRIPTOR_BYTES', len(raw) - 1)
    monkeypatch.setattr(provider, 'MAX_RUNTIME_BYTES', len(raw) - 1)
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='exact raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'])
    compressed, cp, prefix = successor_archive(c)
    with pytest.raises(RuntimeError, match='exact raw byte bound before decode'):
        archive.inspect_archive(io.BytesIO(compressed), cp, prefix)


@pytest.mark.parametrize('encoding', ['utf-16-le', 'utf-32-be'])
def test_encoded_owner_receipts_bind_roles_before_document_decode(carried, monkeypatch, encoding):
    c = carried
    raw = b'{}\n' + b' ' * 1000
    descriptor = c['batch'] / 'a_descriptor.json'; descriptor.write_bytes(raw)
    runtime = c['batch'] / 'runtime.json'; runtime.write_bytes(b'{}\n')
    owner = {'schema': 'client442_bag_swap_scout_resume_v1', 'authority_source': provider.bound(descriptor),
        'runtime_authority_source': provider.bound(runtime)}
    (c['batch'] / 'z_owner.json').write_bytes(json.dumps(owner).encode(encoding))
    monkeypatch.setattr(provider, 'MAX_DESCRIPTOR_BYTES', len(raw) - 1)
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'])


def test_bounded_scanner_occurrences_do_not_lose_a_middle_indexed_schema(carried, monkeypatch):
    c = carried
    raw = (b'{' + b'"schema":null,' * 10000 + b'"schema":' + json.dumps(provider.CACHE_SCHEMA).encode()
        + b',' + b'"schema":null,' * 10000 + b'"schema":null}')
    fields, _, recognized, _ = archive._role_fields(raw)
    assert len(fields['schema']) == 2 and provider.CACHE_SCHEMA in recognized
    (c['batch'] / 'many_declarations.json').write_bytes(raw)
    monkeypatch.setattr(provider, 'MAX_DESCRIPTOR_BYTES', len(raw) - 1)
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='exact raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'])


def test_actual_decode_snapshot_rechecks_late_schema_replacement(carried, monkeypatch):
    c = carried
    raw = b'{"ordinary":true}' + b' ' * (provider.MAX_RUNTIME_BYTES + 1)
    replacement = json.dumps({'schema': provider.RUNTIME_SCHEMA}).encode()
    replacement += b' ' * (len(raw) - len(replacement))
    path = c['batch'] / 'late_replacement.json'; path.write_bytes(raw)
    original = archive._role_limits
    def replacing(*args):
        limits = original(*args)
        path.write_bytes(replacement)
        return limits
    monkeypatch.setattr(archive, '_role_limits', replacing)
    prohibit_document_decode(monkeypatch, [replacement])
    with pytest.raises(RuntimeError, match='decoded raw bytes differ from the pinned source SHA'):
        archive.local_sources(c['batch'], root=c['root'])


def test_actual_read_growth_rejects_before_document_decoder(tmp_path, monkeypatch):
    path = tmp_path / 'role.json'; path.write_bytes(b'{}\n')
    original = Path.open
    def growing(target, mode='r', *args, **kwargs):
        if target == path and mode == 'rb':
            with original(target, 'wb') as writer: writer.write(b'{}\n' + b' ' * 100)
        return original(target, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', growing)
    monkeypatch.setattr(archive, '_json', lambda raw: pytest.fail('grown role reached document decoder'))
    with pytest.raises(RuntimeError, match='changed while decoding its actual raw bytes'):
        archive._read(path, 'json', 3, 3)


@pytest.mark.parametrize('encoding', ['utf-16-le', 'utf-16-be', 'utf-32-le', 'utf-32-be'])
def test_literal_lone_surrogates_follow_complete_decoder_encoding_without_cap_bypass(carried, monkeypatch, encoding):
    c = carried
    text = json.dumps({'schema': provider.RUNTIME_SCHEMA, 'unrelated': '\ud800'}, ensure_ascii=False) + ' ' * 1000
    raw = text.encode(encoding, errors='surrogatepass')
    assert json.loads(raw)['unrelated'] == '\ud800'
    (c['batch'] / 'renamed_surrogate_authority.json').write_bytes(raw)
    monkeypatch.setattr(provider, 'MAX_RUNTIME_BYTES', len(raw) - 1)
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='exact raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'])


def test_literal_lone_surrogate_unrelated_json_keeps_existing_acceptance(carried):
    c = carried
    raw = '{"unrelated":"\ud800"}'.encode('utf-16-le', errors='surrogatepass')
    path = c['batch'] / 'ordinary_surrogate.json'; path.write_bytes(raw)
    assert archive.local_sources(c['batch'], root=c['root']).get(provider.bound(path), False)['unrelated'] == '\ud800'


def test_identical_over_one_mib_ordinary_bytes_ignore_authority_writer_names(carried):
    c = carried
    raw = json.dumps({'schema': 'ordinary_snapshot_v1', 'padding': 'x' * (1024 * 1024)}).encode()
    assert len(raw) == 1048625 and len(raw) > provider.MAX_RUNTIME_BYTES
    expected = json.loads(raw)
    refs = []
    for name in ('ordinary.json', 'authority.json', 'runtime_authority.json'):
        path = c['batch'] / name; path.write_bytes(raw)
        ref = provider.bound(path); refs.append(ref)
        member = str(path.relative_to(c['root']))
        assert archive._role_limits({member: str(path)}, {member: ref['sha256']}, {}, c['root'], None) == {}
    assert len({ref['sha256'] for ref in refs}) == 1
    store = archive.local_sources(c['batch'], root=c['root'])
    assert all(store.get(ref, False) == expected for ref in refs)
    compressed, cp, prefix = successor_archive(c)
    data, _, tracking, _ = archive.inspect_archive(io.BytesIO(compressed), cp, prefix)
    try:
        assert all(data[provider._member(ref, c['root'])] == expected for ref in refs)
    finally: tracking['_spool'].cleanup()


@pytest.mark.parametrize('name', ['ordinary.json', 'authority.json', 'runtime_authority.json'])
@pytest.mark.parametrize('role', ['descriptor', 'runtime'])
def test_identical_ordinary_schema_bytes_are_capped_only_when_role_is_bound(carried, monkeypatch, name, role):
    c = carried
    raw = json.dumps({'schema': 'ordinary_snapshot_v1', 'padding': 'x' * (1024 * 1024)}).encode()
    path = c['batch'] / name; path.write_bytes(raw)
    prohibit_document_decode(monkeypatch, [raw])
    refs = {role: provider.bound(path)}
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        archive.local_sources(c['batch'], root=c['root'], role_refs=refs)
    compressed, cp, prefix = successor_archive(c)
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        archive.inspect_archive(io.BytesIO(compressed), cp, prefix, role_refs=refs)


@pytest.mark.parametrize('schema', [provider.RUNTIME_SCHEMA, provider.CACHE_SCHEMA, 'ordinary_snapshot_v1'])
def test_review02_exact_json_replacement_is_rejected_before_decoder(carried, monkeypatch, schema):
    c = carried; path = c['batch'] / 'independent_renamed.json'
    raw_a = provider._encode({'schema': schema, 'marker': 'AAAA'})
    raw_b = provider._encode({'schema': schema, 'marker': 'BBBB'})
    assert len(raw_a) == len(raw_b)
    path.write_bytes(raw_a)
    real_read, decoder, calls = archive._read, index._source_json, []
    def replace_before_read(target, *args, **kwargs):
        if Path(target) == path:
            assert path.read_bytes() == raw_a
            path.write_bytes(raw_b); calls.append('A_to_B_after_role_scan')
        return real_read(target, *args, **kwargs)
    def restore_after_decode(raw):
        value = decoder(raw)
        if raw == raw_b:
            path.write_bytes(raw_a); calls.append('B_to_A_after_decode')
        return value
    monkeypatch.setattr(archive, '_read', replace_before_read)
    monkeypatch.setattr(index, '_source_json', restore_after_decode)
    with pytest.raises(RuntimeError, match='decoded raw bytes differ from the pinned source SHA'):
        archive.local_sources(c['batch'], root=c['root'])
    assert calls == ['A_to_B_after_role_scan']


def test_review02_exact_journal_replacement_never_returns_forged_rows(carried, monkeypatch):
    c = carried
    row = next(r for r in c['carry']['members'] if r['original_member'] == 'tracking/packets.jsonl')
    path = c['root'] / row['copy_member']; raw_a = path.read_bytes(); raw_b = raw_a.replace(b'parent', b'forged')
    assert len(raw_a) == len(raw_b)
    read, journal, calls = archive._read, archive._journal, []
    def before(target, *args, **kwargs):
        if Path(target) == path: path.write_bytes(raw_b); calls.append('A_to_B')
        return read(target, *args, **kwargs)
    def after(handle, size):
        result = journal(handle, size)
        if Path(handle.name) == path: path.write_bytes(raw_a); calls.append('B_to_A')
        return result
    monkeypatch.setattr(archive, '_read', before)
    monkeypatch.setattr(archive, '_journal', after)
    with pytest.raises(RuntimeError, match='decoded raw bytes differ from the pinned source SHA'):
        archive.local_sources(c['batch'], root=c['root'])
    assert calls == ['A_to_B', 'B_to_A'] and path.read_bytes() == raw_a


@pytest.mark.parametrize('kind,raw', [('json', b'{"time":1,"marker":"AAAA"}\n'),
    ('journal', b'{"time":1,"marker":"AAAA"}\n')])
@pytest.mark.parametrize('change', ['replace', 'grow', 'shrink', 'inode', 'symlink'])
def test_typed_opened_identity_races_reject_before_return(tmp_path, monkeypatch, kind, raw, change):
    path = tmp_path / 'typed.blob'; path.write_bytes(raw)
    opened, changed = Path.open, []
    replacement = raw.replace(b'AAAA', b'BBBB')
    def mutate():
        if change == 'replace': path.write_bytes(replacement)
        elif change == 'grow': path.write_bytes(raw + b' ')
        elif change == 'shrink': path.write_bytes(raw[:-1])
        else:
            path.unlink()
            if change == 'inode': path.write_bytes(raw)
            else:
                target = tmp_path / 'other.blob'; target.write_bytes(raw); path.symlink_to(target)
        changed.append(True)
    class Handle:
        def __init__(self, handle): self.handle, self.name = handle, handle.name
        def __enter__(self): return self
        def __exit__(self, *args): return self.handle.__exit__(*args)
        def fileno(self): return self.handle.fileno()
        def read(self, count=-1):
            value = self.handle.read(count)
            if not changed: mutate()
            return value
    def hooked(target, mode='r', *args, **kwargs):
        handle = opened(target, mode, *args, **kwargs)
        return Handle(handle) if target == path and mode == 'rb' else handle
    monkeypatch.setattr(Path, 'open', hooked)
    with pytest.raises(RuntimeError, match='changed while decoding its actual raw bytes'):
        archive._read(path, kind, len(raw), expected_sha=digest(raw))
    assert changed


@pytest.mark.parametrize('kind', ['json', 'journal'])
def test_typed_decoder_mutate_restore_is_rejected_after_parse(tmp_path, monkeypatch, kind):
    raw = b'{"time":1,"marker":"AAAA"}\n'
    path = tmp_path / 'typed.blob'; path.write_bytes(raw)
    original = archive._json if kind == 'json' else archive._journal
    def restore(*args):
        value = original(*args)
        path.write_bytes(raw.replace(b'AAAA', b'BBBB')); path.write_bytes(raw)
        return value
    monkeypatch.setattr(archive, '_json' if kind == 'json' else '_journal', restore)
    with pytest.raises(RuntimeError, match='changed while decoding its actual raw bytes'):
        archive._read(path, kind, len(raw), expected_sha=digest(raw))
    assert path.read_bytes() == raw


@pytest.mark.parametrize('kind', ['json', 'journal'])
def test_typed_reader_rejects_wrong_manifest_size_or_sha(tmp_path, kind):
    raw = b'{"time":1}\n'; path = tmp_path / 'typed.blob'; path.write_bytes(raw)
    with pytest.raises(RuntimeError, match='retained raw source size differs'):
        archive._read(path, kind, len(raw) + 1, expected_sha=digest(raw))
    with pytest.raises(RuntimeError, match='decoded raw bytes differ from the pinned source SHA'):
        archive._read(path, kind, len(raw), expected_sha='b' * 64)


@pytest.mark.parametrize('kind,raw,value', [('json', b'{"time":1}\n', {'time': 1}),
    ('journal', b'{"time":1}\n', [{'time': 1}]), ('journal', b'', []),
    ('binary', b'opaque binary', None), ('png', b'\x89PNG\r\n\x1a\nbody', None)])
def test_exact_typed_snapshots_use_one_open_and_return_valid_views(tmp_path, monkeypatch, kind, raw, value):
    path = tmp_path / 'typed.blob'; path.write_bytes(raw)
    original, count = Path.open, []
    def tracked(target, mode='r', *args, **kwargs):
        if target == path and mode == 'rb': count.append(True)
        return original(target, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', tracked)
    assert archive._read(path, kind, len(raw), expected_sha=digest(raw)) == value
    assert len(count) == 1


@pytest.mark.parametrize('reader', ['local', 'portable'])
def test_review02_unrelated_ordinary_ready_phase_keeps_complete_reader_acceptance(carried, reader):
    c = carried
    raw = json.dumps({'schema': 'ordinary_snapshot_v1', 'phase': 'bags_swap_scout_ready',
        'value': 'unrelated ordinary semantic data'}).encode()
    assert len(raw) == 113
    path = c['batch'] / 'ordinary_semantic_phase.json'; path.write_bytes(raw)
    if reader == 'local': data = archive.local_sources(c['batch'], root=c['root']).data
    else:
        compressed, cp, prefix = successor_archive(c)
        data, _, tracking, _ = archive.inspect_archive(io.BytesIO(compressed), cp, prefix)
        tracking['_spool'].cleanup()
    assert data[str(path.relative_to(c['root']))] == json.loads(raw)


@pytest.mark.parametrize('reader', ['local', 'portable'])
@pytest.mark.parametrize('owner_kind', ['ordinary_keys', 'ordinary_ready_keys', 'generic_wrong_phase'])
def test_unrelated_ordinary_role_keys_do_not_lower_target_cap(carried, reader, owner_kind):
    c = carried
    raw = json.dumps({'schema': 'ordinary_snapshot_v1', 'padding': 'x' * (1024 * 1024)}).encode()
    target = c['batch'] / 'large_ordinary.json'; target.write_bytes(raw)
    target_ref = provider.bound(target)
    owner = {'schema': 'ordinary_snapshot_v1', 'authority_source': target_ref,
        'runtime_authority_source': target_ref}
    if owner_kind == 'ordinary_ready_keys': owner['phase'] = 'bags_swap_scout_ready'
    elif owner_kind == 'generic_wrong_phase':
        owner.update(schema='client442_laya_interactions_v1', phase='unrelated_ordinary_phase')
    owner_path = c['batch'] / 'owner_keys.json'; owner_path.write_bytes(encoded(owner))
    if reader == 'local': data = archive.local_sources(c['batch'], root=c['root']).data
    else:
        compressed, cp, prefix = successor_archive(c)
        data, _, tracking, _ = archive.inspect_archive(io.BytesIO(compressed), cp, prefix)
        tracking['_spool'].cleanup()
    assert data[str(target.relative_to(c['root']))] == json.loads(raw)
    assert data[str(owner_path.relative_to(c['root']))] == owner


@pytest.mark.parametrize('reader', ['local', 'portable'])
def test_genuine_generic_ready_binds_complete_renamed_role_refs(carried, reader):
    c = carried
    descriptor = c['batch'] / 'private_report.json'; descriptor.write_bytes(encoded({'schema': provider.CACHE_SCHEMA}))
    runtime = c['batch'] / 'private_episode.json'; runtime.write_bytes(encoded({'schema': provider.RUNTIME_SCHEMA}))
    owner = {'schema': 'client442_laya_interactions_v1', 'phase': 'bags_swap_scout_ready',
        'authority_source': provider.bound(descriptor), 'runtime_authority_source': provider.bound(runtime)}
    (c['batch'] / 'genuine_ready.json').write_bytes(encoded(owner))
    if reader == 'local': data = archive.local_sources(c['batch'], root=c['root']).data
    else:
        compressed, cp, prefix = successor_archive(c)
        data, _, tracking, _ = archive.inspect_archive(io.BytesIO(compressed), cp, prefix)
        tracking['_spool'].cleanup()
    assert data[str(descriptor.relative_to(c['root']))]['schema'] == provider.CACHE_SCHEMA
    assert data[str(runtime.relative_to(c['root']))]['schema'] == provider.RUNTIME_SCHEMA


@pytest.mark.parametrize('reader', ['local', 'portable'])
@pytest.mark.parametrize('role', ['descriptor', 'runtime'])
def test_genuine_generic_ready_caps_bound_ordinary_schema_target_before_decode(carried, monkeypatch, reader, role):
    c = carried
    raw = json.dumps({'schema': 'ordinary_snapshot_v1', 'padding': 'x' * (1024 * 1024)}).encode()
    target = c['batch'] / 'overcap_private.json'; target.write_bytes(raw)
    other = c['batch'] / 'other_private.json'; other.write_bytes(b'{}\n')
    refs = {role: provider.bound(target), 'runtime' if role == 'descriptor' else 'descriptor': provider.bound(other)}
    owner = {'schema': 'client442_laya_interactions_v1', 'phase': 'bags_swap_scout_ready',
        'authority_source': refs['descriptor'], 'runtime_authority_source': refs['runtime']}
    (c['batch'] / 'genuine_ready.json').write_bytes(encoded(owner))
    prohibit_document_decode(monkeypatch, [raw])
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        if reader == 'local': archive.local_sources(c['batch'], root=c['root'])
        else:
            compressed, cp, prefix = successor_archive(c)
            archive.inspect_archive(io.BytesIO(compressed), cp, prefix)


@pytest.mark.parametrize('failure',[False,True])
def test_private_raw_spool_uses_the_owned_evidence_filesystem_and_cleans_on_exit(tmp_path,failure):
    root=tmp_path/'root';root.mkdir();(root/'evidence').mkdir()
    directory=None
    try:
        with archive._private_spool(root,'.owned-test-spool-') as name:
            directory=Path(name)
            assert directory.parent==root/'evidence'
            assert directory.resolve()==directory and not directory.is_symlink()
            assert directory.stat().st_mode & 0o777==0o700
            (directory/'raw.blob').write_bytes(b'original bounded source')
            if failure:raise RuntimeError('ordinary source verification failure')
    except RuntimeError as error:
        assert failure and str(error)=='ordinary source verification failure'
    assert directory is not None and not directory.exists()


@pytest.mark.parametrize('damage',['absent_evidence','symlink_evidence','symlink_parent'])
def test_raw_spool_requires_existing_canonical_evidence_before_creating_any_directory(tmp_path,monkeypatch,damage):
    root=tmp_path/'root';root.mkdir()
    if damage=='symlink_evidence':
        actual=tmp_path/'actual';actual.mkdir();(root/'evidence').symlink_to(actual,target_is_directory=True)
    elif damage=='symlink_parent':
        (root/'evidence').mkdir();alias=tmp_path/'root_alias';alias.symlink_to(root,target_is_directory=True);root=alias
    def forbidden(*args,**kwargs):raise AssertionError('invalid source staging must not allocate')
    monkeypatch.setattr(archive.tempfile,'TemporaryDirectory',forbidden)
    with pytest.raises(RuntimeError):archive._private_spool(root,'.owned-test-spool-')


def test_portable_full_archive_spool_ignores_global_tmpdir_and_keeps_output_identical(carried,monkeypatch,tmp_path):
    c=carried;compressed,cp,prefix=successor_archive(c)
    trap=tmp_path/'global_tmpdir';trap.mkdir();monkeypatch.setenv('TMPDIR',str(trap))
    original=archive.tempfile.TemporaryDirectory;calls=[]
    def allocated(*args,**kwargs):
        calls.append(dict(kwargs));return original(*args,**kwargs)
    monkeypatch.setattr(archive.tempfile,'TemporaryDirectory',allocated)
    data,digests,tracking,count=archive.inspect_archive(io.BytesIO(compressed),cp,prefix)
    name=Path(tracking['_spool'].name)
    try:
        assert count==len(compressed) and data[prefix+'entry/episode.json']=={}
        assert calls==[{'prefix':'.client442-indexed-carry-','dir':c['root']/'evidence'}]
        assert name.parent==c['root']/'evidence'
        assert not list(trap.iterdir())
    finally:tracking['_spool'].cleanup()
    assert not name.exists()


@pytest.mark.parametrize('filesystem',['tmpfs','ramfs','','overlay','unknown','ext4\nxfs'])
def test_memory_or_unidentified_spool_filesystems_reject_before_allocation(tmp_path,monkeypatch,filesystem):
    root=tmp_path/'root';root.mkdir();(root/'evidence').mkdir()
    def observed(*args,**kwargs):
        return archive.subprocess.CompletedProcess(args[0],0,stdout=filesystem,stderr='')
    def forbidden(*args,**kwargs):raise AssertionError('non-disk staging must not allocate')
    monkeypatch.setattr(archive.subprocess,'run',observed)
    monkeypatch.setattr(archive.tempfile,'TemporaryDirectory',forbidden)
    with pytest.raises(RuntimeError,match='supported disk-backed evidence filesystem required'):
        archive._private_spool(root,'.owned-test-spool-')
    assert list((root/'evidence').iterdir())==[]


@pytest.mark.parametrize('failure',['missing','nonzero','timeout','encoding'])
def test_spool_filesystem_discovery_errors_fail_closed_before_allocation(tmp_path,monkeypatch,failure):
    root=tmp_path/'root';root.mkdir();(root/'evidence').mkdir()
    errors={'missing':FileNotFoundError('findmnt unavailable'),
        'nonzero':archive.subprocess.CalledProcessError(1,['findmnt']),
        'timeout':archive.subprocess.TimeoutExpired(['findmnt'],5),
        'encoding':UnicodeDecodeError('ascii',b'\xff',0,1,'not ascii')}
    def observed(*args,**kwargs):raise errors[failure]
    def forbidden(*args,**kwargs):raise AssertionError('failed discovery must not allocate')
    monkeypatch.setattr(archive.subprocess,'run',observed)
    monkeypatch.setattr(archive.tempfile,'TemporaryDirectory',forbidden)
    with pytest.raises(RuntimeError,match='disk-backed evidence filesystem discovery failed'):
        archive._private_spool(root,'.owned-test-spool-')
    assert list((root/'evidence').iterdir())==[]


def test_actual_memory_filesystem_is_denied_before_temporary_spool_creation(monkeypatch):
    import tempfile
    filesystem=archive.subprocess.run(['findmnt','--noheadings','--raw','--output','FSTYPE',
        '--target','/tmp'],check=True,capture_output=True,encoding='ascii',timeout=5).stdout.strip()
    if filesystem not in ('tmpfs','ramfs'):pytest.skip('host /tmp is not a memory filesystem')
    with tempfile.TemporaryDirectory(prefix='client442-tiny-tmpfs-negative-',dir='/tmp') as name:
        root=Path(name);(root/'evidence').mkdir()
        def forbidden(*args,**kwargs):raise AssertionError('real memory staging must not allocate')
        monkeypatch.setattr(archive.tempfile,'TemporaryDirectory',forbidden)
        with pytest.raises(RuntimeError,match='supported disk-backed evidence filesystem required'):
            archive._private_spool(root,'.owned-test-spool-')
        assert list((root/'evidence').iterdir())==[]


def test_actual_lab_disk_filesystem_accepts_tiny_spool_and_cleans():
    root=Path('/home/runiir/.local/share/trinity-client442-lab')
    filesystem=archive.subprocess.run(['findmnt','--noheadings','--raw','--output','FSTYPE',
        '--target',str(root/'evidence')],check=True,capture_output=True,encoding='ascii',timeout=5).stdout.strip()
    assert filesystem=='ext4'
    with archive._private_spool(root,'.client442-tiny-disk-positive-') as name:
        path=Path(name);(path/'raw.blob').write_bytes(b'one bounded source')
        assert path.parent==root/'evidence' and path.stat().st_mode & 0o777==0o700
    assert not path.exists()
