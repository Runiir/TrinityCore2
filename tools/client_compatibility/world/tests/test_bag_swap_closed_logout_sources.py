"""Typed flat carry must preserve historical roles and bound fresh roles."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import pytest
from tools.client_compatibility import bag_swap_closed_logout_sources as source
from tools.client_compatibility import bag_swap_indexed_archive as archive
from tools.client_compatibility import bag_swap_evidence as evidence
from tools.client_compatibility import interaction_bag_swap_continuation as continuation
from tools.client_compatibility.world.tests.test_bag_swap_indexed_archive import carried, encoded, packed, digest


@pytest.fixture
def flat(carried, monkeypatch):
    c = carried; root = c['root']; monkeypatch.setattr(evidence.lab, 'ROOT', root)
    old = deepcopy(c['carry']); original = root / source.BATCH
    original.mkdir(parents=True)
    files = {}
    for row in [*old['members'], *old['authorities']]:
        previous = row['copy_member']; row['copy_member'] = previous.replace(c['batch'].name, original.name)
        files[row['copy_member']] = (root / previous).read_bytes()
    old_raw = encoded(old); old_member = source.BATCH + archive.CARRY_NAME
    files[old_member] = old_raw
    roles = {}
    for kind, schema in [('authority',source.CACHE_SCHEMA),('runtime_authority',source.RUNTIME_SCHEMA)]:
        member = source.BATCH + 'resume/' + kind + '.json'; raw = encoded({'schema':schema})
        files[member] = raw; roles[kind] = {'path':str(root/member),'sha256':digest(raw)}
    files[source.BATCH+'scout_ready01/episode.json'] = encoded({'schema':'client442_laya_interactions_v1',
        'phase':'bags_swap_scout_ready','authority_source':roles['authority'],
        'runtime_authority_source':roles['runtime_authority'],'completed':True,'failure':None})
    binary = b'{"historical_metadata_only":true}\n'
    historic = encoded({'schema':'client442_laya_interactions_v1','phase':'bags_swap_scout_ready',
        'authority_source':{'path':str(root/'evidence/ui174/resume/authority.json'),'sha256':'a'*64},
        'runtime_authority_source':{'path':str(root/'evidence/ui174/resume/runtime_authority.json'),'sha256':'b'*64}})
    rows=[]
    for name, raw, kind in [('old.bin',binary,'binary'),('ready.json',historic,'json'),
                           ('boundary.json',encoded({'completed':True,'failure':None}),'json')]:
        member=source.BATCH+'crash_sources/'+digest(raw)+Path(name).suffix; files[member]=raw
        rows.append({'original_path':str(root/'evidence/ui174'/name),'sha256':digest(raw),'bytes':len(raw),
            'copy_member':member,'kind':kind})
    crash={'schema':'client442_bag_swap_offline_ancestry_v1','members':rows,'authorities':[],
        'boundary_source':{'path':rows[2]['original_path'],'sha256':rows[2]['sha256']},
        'indexed_carry_source':{'path':str(root/old_member),'sha256':digest(old_raw)}}
    files[source.BATCH+'crash_ancestry.json']=encoded(crash)
    stop_member=source.BATCH+'failed_entry_stop01/episode.json'
    files[stop_member]=encoded({'completed':True,'failure':None})
    files[source.BATCH+'frame.png']=b'\x89PNG\r\n\x1a\nfixture'
    files['tracking/packets.jsonl']=encoded({'time':1})
    files['tracking/events.jsonl']=encoded({'time':1})
    raw,cp,files=packed(files);cp['file']=source.POINTER.removesuffix('.dvc')
    tracking=[r for r in cp['file_manifest'] if r['path'].startswith('tracking/')]
    cp['file_manifest']=[r for r in cp['file_manifest'] if not r['path'].startswith('tracking/')]
    for member,value in files.items():
        path=root/member;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
    paths={m:str(root/m) for m in files};digests={m:digest(v) for m,v in files.items()};sizes={m:len(v) for m,v in files.items()}
    classes=source._classes(paths,digests,sizes,old,root)
    successor=root/'evidence/client_interactions_20261008_ui177';successor.mkdir()
    cp_path=original/'checkpoint_receipt.json';cp_path.write_bytes(encoded(cp))
    remote=root/'evidence/ui176_remote.json';remote.write_bytes(encoded({'actual_remote_verified':True,'tracking_files':tracking}))
    pins={'closure':{'path':str(root/stop_member),'sha256':digests[stop_member]},
        'checkpoint':source.bound(cp_path),'remote':source.bound(remote), 'primary_stop':c['predecessor']['primary_stop']}
    rows=[]
    for m,v in files.items():
        rows.append({'original_path':str(root/m),'original_member':m,'sha256':digests[m],'bytes':sizes[m],
            'copy_member':str((successor/source.RAW_DIRECTORY/(digests[m]+'.blob')).relative_to(root)),
            'kinds':sorted(classes[m])})
    external=[]
    for k in ('checkpoint','remote'):
        ref=pins[k];external.append({'role':k,'original_path':ref['path'],'original_member':str(Path(ref['path']).relative_to(root)),
            'sha256':ref['sha256'],'bytes':Path(ref['path']).stat().st_size,
            'copy_member':str((successor/source.RAW_DIRECTORY/(ref['sha256']+'.blob')).relative_to(root)), 'kinds':['json']})
    carry={'schema':source.CARRY_SCHEMA,'predecessor':pins,'archive':{'file':cp['file'],'bytes':cp['bytes'],
        'sha256':cp['sha256'],'manifest':cp['file_manifest'],'tracking_manifest':tracking},'dvc_pointer':{},'pointer_raw_hex':'',
        'members':rows,'authorities':external}
    for row in [*rows,*external]:
        target=root/row['copy_member'];target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():target.write_bytes(Path(row['original_path']).read_bytes())
    (successor/source.CARRY_NAME).write_bytes(encoded(carry))
    return {'root':root,'batch':successor,'carry':carry,'files':files,'roles':roles,'binary':rows,
        'original':original,'historical':historic,'historical_row':crash['members'][1]}


def load_portable(c):
    paths={str(p.relative_to(c['root'])):str(p) for p in c['batch'].rglob('*') if p.is_file()}
    digests={m:source.bound(p)['sha256'] for m,p in paths.items()};sizes={m:Path(p).stat().st_size for m,p in paths.items()}
    return source.materialize(paths,digests,sizes,c['carry'],c['root'])


def diagnostic_carries(c, count):
    """Retain valid maps whose aliases deliberately name absent sibling copies."""
    refs=[]
    for number in range(count):
        value=deepcopy(c['carry'])
        for row in [*value['members'],*value['authorities']]:
            row['copy_member']=str(Path('evidence')/f'ui177_candidate_diagnostic_{number}'/
                source.RAW_DIRECTORY/(row['sha256']+'.blob'))
            assert not (c['root']/row['copy_member']).exists()
        source.validate_manifest(value,c['root'])
        path=c['batch']/'diagnostics'/f'actual_flat_manifest{number}.json'
        path.parent.mkdir(exist_ok=True);path.write_bytes(encoded(value))
        refs.append((source.bound(path),value))
    return refs


def ready_ref(c):
    member=source.BATCH+'scout_ready01/episode.json'
    return {'path':str(c['root']/member),'sha256':digest(c['files'][member])}


@pytest.mark.parametrize('local',[True,False])
@pytest.mark.parametrize('count',[1,2,3])
def test_diagnostic_maps_are_readable_without_promoting_competing_aliases(flat,local,count):
    c=flat;diagnostics=diagnostic_carries(c,count)
    store=source.local_store(c['batch'],c['root']) if local else load_portable(c)
    actual=ready_ref(c);expected=json.loads(c['files'][source.BATCH+'scout_ready01/episode.json'])
    actual_row=next(r for r in c['carry']['members'] if r['original_path']==actual['path'])
    for ref,value in diagnostics:
        assert store.get(ref,False)==value
    for member in (None,'resume/authority.json',archive.CARRY_NAME,'crash_ancestry.json',None):
        if member is None:
            assert store.get(actual,False)==expected
        else:
            original=source.BATCH+member
            assert store.get({'path':str(c['root']/original),'sha256':digest(c['files'][original])},False)
        store._refresh_maps()
        assert store.maps==[c['carry']]
        assert store._rows(actual)==[actual_row]
        assert store.member(actual)==actual_row['copy_member']
    # Lazy historical-map decoding must not extend the current outer keyspace.
    historical={'path':c['historical_row']['original_path'],'sha256':c['historical_row']['sha256']}
    with pytest.raises(RuntimeError,match='absent or ambiguous'):
        store.get(historical,False)
    binary=next(r for r in c['carry']['members'] if r['original_member'].endswith('.bin'))
    with pytest.raises(RuntimeError,match='not an ordinary JSON'):
        store.get({'path':binary['original_path'],'sha256':binary['sha256']},False)


@pytest.mark.parametrize('local',[True,False])
@pytest.mark.parametrize('damage',['wrong_sha','absent_logical_ref'])
def test_diagnostic_maps_cannot_rescue_bad_logical_sources(flat,local,damage):
    c=flat;diagnostic_carries(c,2)
    store=source.local_store(c['batch'],c['root']) if local else load_portable(c)
    ref=ready_ref(c)
    if damage=='wrong_sha':ref['sha256']='f'*64
    else:ref['path']=str(c['root']/source.BATCH/'scout_ready01/absent.json')
    with pytest.raises(RuntimeError,match='absent or ambiguous'):
        store.get(ref,False)


@pytest.mark.parametrize('local',[True,False])
def test_readable_diagnostic_maps_do_not_replace_damaged_actual_copy(flat,local):
    c=flat;diagnostic_carries(c,2);actual=ready_ref(c)
    row=next(r for r in c['carry']['members'] if r['original_path']==actual['path'])
    path=c['root']/row['copy_member'];raw=path.read_bytes()
    path.write_bytes(raw.replace(b'bags_swap_scout_ready',b'bags_swap_scout_reado'))
    with pytest.raises(RuntimeError,match='complete flat physical copies differ'):
        source.local_store(c['batch'],c['root']) if local else load_portable(c)


@pytest.mark.parametrize('damage',['passed_carry','physical_carry','missing_physical_carry'])
def test_materialize_requires_exact_current_carry_even_with_valid_diagnostics(flat,damage):
    c=flat;diagnostic_carries(c,3);path=c['batch']/source.CARRY_NAME
    if damage=='passed_carry':c['carry']['pointer_raw_hex']='00'
    elif damage=='physical_carry':
        different=deepcopy(c['carry']);different['pointer_raw_hex']='00';path.write_bytes(encoded(different))
    else:path.unlink()
    with pytest.raises(RuntimeError,match='exact current physically retained carry map'):
        load_portable(c)


@pytest.mark.parametrize('local',[True,False])
@pytest.mark.parametrize('location,message',[
    ('member','typed bounded flat original member'),
    ('authority','typed bounded flat original member'),
    ('manifest','unique typed actual checkpoint manifest row'),
    ('tracking','unique typed actual checkpoint manifest row'),
    ('archive','actual compressed checkpoint SHA256 and bytes'),
])
def test_physical_canonical_map_cannot_substitute_equal_float_for_integer(flat,local,location,message):
    c=flat;physical=deepcopy(c['carry'])
    row={'member':physical['members'][0],'authority':physical['authorities'][0],
        'manifest':physical['archive']['manifest'][0],
        'tracking':physical['archive']['tracking_manifest'][0],
        'archive':physical['archive']}[location]
    assert type(row['bytes']) is int
    row['bytes']=float(row['bytes'])
    assert type(row['bytes']) is float
    # Python equality accepts this mutation; exact typed authority must refuse it.
    assert physical==c['carry']
    with pytest.raises(RuntimeError,match=message):
        source.validate_manifest(physical,c['root'])
    (c['batch']/source.CARRY_NAME).write_bytes(encoded(physical))
    with pytest.raises(RuntimeError,match=message if local else 'exact current physically retained carry map'):
        store=source.local_store(c['batch'],c['root']) if local else load_portable(c)
        assert store.get(ready_ref(c),False)['phase']=='bags_swap_scout_ready'


@pytest.mark.parametrize('damage',['boolean_bytes','missing_kinds'])
def test_materialize_cannot_use_physically_untyped_canonical_member(flat,damage):
    c=flat;physical=deepcopy(c['carry']);row=physical['members'][0]
    if damage=='boolean_bytes':row['bytes']=True
    else:row.pop('kinds')
    with pytest.raises(RuntimeError,match='typed bounded flat original member'):
        source.validate_manifest(physical,c['root'])
    (c['batch']/source.CARRY_NAME).write_bytes(encoded(physical))
    with pytest.raises(RuntimeError,match='exact current physically retained carry map'):
        load_portable(c)


@pytest.mark.parametrize('local',[True,False])
def test_alias_map_is_pinned_against_later_readable_data_mutation(flat,local):
    c=flat;diagnostics=diagnostic_carries(c,1)
    store=source.local_store(c['batch'],c['root']) if local else load_portable(c)
    actual=ready_ref(c);expected=json.loads(c['files'][source.BATCH+'scout_ready01/episode.json'])
    active=deepcopy(c['carry'])
    diagnostic=store.get(diagnostics[0][0],False)
    canonical=store.get(source.bound(c['batch']/source.CARRY_NAME),False)
    for value in (c['carry'],diagnostic,canonical):
        row=next(r for r in value['members'] if r['original_path']==actual['path'])
        row['copy_member']='evidence/absent/predecessor_ui176_raw/'+row['sha256']+'.blob'
    store._refresh_maps()
    assert store.maps==[active]
    assert store.get(actual,False)==expected


@pytest.mark.parametrize('local',[True,False])
def test_flat_mixed_view_keeps_original_keys_binary_and_historical_roles(flat,local):
    c=flat;store=source.local_store(c['batch'],c['root']) if local else load_portable(c)
    ready=store.get({'path':str(c['root']/source.BATCH/'scout_ready01/episode.json'),
        'sha256':digest(c['files'][source.BATCH+'scout_ready01/episode.json'])},False)
    assert ready['authority_source']==c['roles']['authority']
    binary=next(row for row in c['carry']['members'] if row['original_member'].endswith('.bin'))
    assert binary['original_member'] not in store.data
    with pytest.raises(RuntimeError,match='not an ordinary JSON'):
        store.get({'path':binary['original_path'],'sha256':binary['sha256']},False)
    assert continuation.authority_sources(source.RUNTIME_SCHEMA) is source
    assert source.LOGIN_SYNC_SCHEMA=='client442_bag_swap_login_sync_v2'


@pytest.mark.parametrize('local',[True,False])
def test_fabricated_historical_current_roles_rejected_before_exemption(flat,local):
    c=flat;row=next(r for r in c['carry']['members'] if r['original_member']==c['historical_row']['copy_member'])
    value=json.loads(c['historical']);value['authority_source']={'path':str(c['batch']/'resume/absent.json'),'sha256':'c'*64}
    value['runtime_authority_source']={'path':str(c['batch']/'resume/absent_runtime.json'),'sha256':'d'*64}
    raw=encoded(value);old=c['root']/row['copy_member'];old.unlink()
    row['sha256']=digest(raw);row['bytes']=len(raw)
    row['copy_member']=str((c['batch']/source.RAW_DIRECTORY/(row['sha256']+'.blob')).relative_to(c['root']))
    (c['root']/row['copy_member']).write_bytes(raw)
    manifest=next(r for r in c['carry']['archive']['manifest'] if r['path']==row['original_member'])
    manifest.update(sha256=row['sha256'],bytes=row['bytes'])
    (c['batch']/source.CARRY_NAME).write_bytes(encoded(c['carry']))
    with pytest.raises(RuntimeError,match='historical crash receipt cannot bind current-batch'):
        source.local_store(c['batch'],c['root']) if local else load_portable(c)


@pytest.mark.parametrize('schema',[source.CACHE_SCHEMA,source.RUNTIME_SCHEMA])
@pytest.mark.parametrize('local',[True,False])
def test_fresh_schema_cap_is_enforced_before_decode(flat,schema,local):
    c=flat;path=c['batch']/'renamed.json'
    path.write_bytes(encoded({'schema':schema,'padding':'x'*(1024*1024)}))
    with pytest.raises(RuntimeError,match='exact raw byte bound before decode'):
        source.local_store(c['batch'],c['root']) if local else load_portable(c)


def test_manifest_cannot_reclassify_old_opaque_cache_as_ordinary_json(flat):
    c=flat;bad=deepcopy(c['carry']);row=bad['members'][0]
    pinned=archive.index._OPAQUE_SOURCES['ui172_authority']
    row.update(sha256=pinned['source']['sha256'],bytes=pinned['bytes'],kinds=['json'])
    row['copy_member']=str((c['batch']/source.RAW_DIRECTORY/(row['sha256']+'.blob')).relative_to(c['root']))
    expected=next(r for r in bad['archive']['manifest'] if r['path']==row['original_member'])
    expected.update(sha256=row['sha256'],bytes=row['bytes'])
    with pytest.raises(RuntimeError,match='ordinary JSON keeps'):
        source.validate_manifest(bad,c['root'])


def test_actual_pins_cannot_reuse_ui173_or_missing_remote(flat):
    c=flat;pins={k:c['carry']['predecessor'][k] for k in ('closure','checkpoint','remote')}
    assert source.admission_pins(pins,root=c['root'])==pins
    pins['closure']['path']=str(c['root']/'evidence/client_interactions_20261008_ui173/stopped_closure01/episode.json')
    with pytest.raises(RuntimeError,match='only the actual published excluded UI176'):
        source.admission_pins(pins,root=c['root'])


def sealed_stream(flat,monkeypatch):
    c=flat;files=deepcopy(c['files'])
    for i in range(13):files[f'tracking/live/fixture{i}.tsv']=b'fixture\n'
    raw,cp,files=packed(files);cp['file']=source.POINTER.removesuffix('.dvc')
    tracking=[r for r in cp['file_manifest'] if r['path'].startswith('tracking/')]
    cp['file_manifest']=[r for r in cp['file_manifest'] if not r['path'].startswith('tracking/')]
    assert len(tracking)==16
    cp_ref=c['carry']['predecessor']['checkpoint'];Path(cp_ref['path']).write_bytes(encoded(cp));cp_ref.update(source.bound(cp_ref['path']))
    oid=hashlib.md5(raw).hexdigest()
    pointer_raw=(f'outs:\n- md5: {oid}\n  size: {len(raw)}\n  hash: md5\n  path: {Path(cp["file"]).name}\n').encode()
    pointer={'source':{'path':str(c['root'].parent/source.POINTER),'sha256':digest(pointer_raw)},
        'pointer':source.POINTER,'oid':oid,'bytes':len(raw)}
    remote={'schema':'client442_ui176_closed_excluded_failed_batch_remote_review_v1',
        'pointer':source.POINTER,'object_md5':oid,'bytes':len(raw),'archive_sha256':digest(raw),
        'pointer_sha256':digest(pointer_raw),'outcome':'approved','result':'pass','qualification_added':False,
        'operations_admitted':0,'complete_raw_source_members':123,'manifest_files':len(cp['file_manifest']),
        'all_files':len(cp['file_manifest'])+16,'lifecycle_verified_checks':dict.fromkeys(source.REMOTE_CHECKS,True),
        'lifecycle_review_source':{'path':'/tmp/fixture_lifecycle.json','sha256':'e'*64},'tracking_files':tracking}
    remote.update(dict.fromkeys(('approval','scope_closed','actual_remote_verified','complete_manifest_verified',
        'source123_envelopes_match_retained_git_commit','source_index_classes_and_raw_bindings_verified',
        'whole_failed_unit_excluded'),True))
    remote_ref=c['carry']['predecessor']['remote'];Path(remote_ref['path']).write_bytes(encoded(remote));remote_ref.update(source.bound(remote_ref['path']))
    from tools.client_compatibility import review_hunter_learn_checkpoint as requests
    import urllib.request
    monkeypatch.setattr(requests,'remote_options',lambda repo:{})
    monkeypatch.setattr(requests,'remote_request',lambda options,oid:object())
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k:io.BytesIO(raw))
    return cp,remote,pointer,pointer_raw


def test_writer_streams_complete_raw_manifest_and_preserves_typed_original_view(flat,monkeypatch):
    c=flat;cp,remote,pointer,raw=sealed_stream(c,monkeypatch)
    batch=c['root']/'evidence/writer_successor';batch.mkdir()
    ref=source.carry_authority(batch,admitted={'predecessor':c['carry']['predecessor'],
        'dvc_pointer':pointer,'pointer_raw_hex':raw.hex()},root=c['root'])
    value=json.loads(Path(ref['path']).read_text())
    assert value['archive']['manifest']==cp['file_manifest'] and value['archive']['tracking_manifest']==remote['tracking_files']
    assert len(value['members'])==len(cp['file_manifest'])+16
    assert len(list((batch/source.RAW_DIRECTORY).iterdir()))==len(source.validate_manifest(value,c['root']))
    assert source.local_store(batch,c['root']).get(c['roles']['authority'],False)['schema']==source.CACHE_SCHEMA
    assert not list(batch.rglob('*.gz'))


def test_portable_archive_preserves_current_tracking_identity_over_predecessor_tracking(flat):
    c=flat;prefix=str(c['batch'].relative_to(c['root']))+'/'
    files={str(p.relative_to(c['root'])):p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
    files[prefix+'current/episode.json']=encoded({'completed':True,'failure':None})
    files[prefix+'current/frame.png']=b'\x89PNG\r\n\x1a\ncurrent'
    files['tracking/packets.jsonl']=encoded({'time':101,'current':True})
    files['tracking/events.jsonl']=encoded({'time':102,'current':True})
    raw,cp,_=packed(files)
    data,digests,tracking,count=archive.inspect_archive(io.BytesIO(raw),cp,prefix)
    try:
        assert count==len(raw)
        for kind in ('packets','events'):
            m='tracking/'+kind+'.jsonl'
            assert tracking['raw_journals'][m][0]['current'] is True
            assert digests[m]==digest(files[m])
            assert source.bound(tracking['paths'][m])['sha256']==digests[m]
    finally:tracking['_spool'].cleanup()


def test_publication_reader_selects_flat_normal_carry_without_v1_autodetection(flat,monkeypatch):
    from tools.client_compatibility import review_bag_swap_checkpoint as review
    c=flat;prefix=str(c['batch'].relative_to(c['root']))+'/'
    marker=object();called=[]
    def selected(*args):called.append(args);raise RuntimeError('selected typed normal reader')
    monkeypatch.setattr(archive,'inspect_archive',selected)
    with pytest.raises(RuntimeError,match='selected typed normal reader'):
        review.inspect_archive(marker,{'file_manifest':[{'path':prefix+source.CARRY_NAME}]},prefix)
    assert called[0][0] is marker


@pytest.mark.parametrize('fault',['approval','excluded','checkpoint','checks','opaque_count'])
def test_sealed_pointer_cannot_admit_missing_actual_remote_guards(flat,monkeypatch,fault):
    cp,remote,pointer,raw=sealed_stream(flat,monkeypatch)
    if fault=='approval':remote['approval']=False
    elif fault=='excluded':remote['whole_failed_unit_excluded']=False
    elif fault=='checkpoint':remote['archive_sha256']='f'*64
    elif fault=='checks':remote['lifecycle_verified_checks'].pop('ordinary_logout_input')
    else:remote['complete_raw_source_members']=122
    with pytest.raises(RuntimeError):source._portable_pointer(pointer,raw.hex(),cp,remote)


def epoch_case(tmp_path):
    """Synthetic 123-member predecessor exercises the derived 129-member union."""
    from tools.client_compatibility.world.tests.test_bag_swap_indexed_sources import Store
    store=Store(tmp_path);repo=tmp_path/'repo'
    members=sorted({'experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json',
        'tools/client_compatibility/untouched.py',*source.CHANGED_OLD} |
        {f'tools/client_compatibility/prior_{i:03d}.py' for i in range(114)})
    assert len(members)==123
    before='b'*40;after='c'*40
    old_rows=[];old_copies=[];current_raw={}
    for i,member in enumerate(members):
        raw=('old '+member).encode();sha=digest(raw);path=str(repo/member)
        old_rows.append({'path':path,'sha256':sha});current_raw[member]=raw
        old_copies.append(store.add(source.BATCH+'resume/code_sources/'+str(i)+'.json',
            {'schema':source.indexed.stopped.CODE_SCHEMA,'code_commit':before,'original_path':path,
             'sha256':sha,'bytes':len(raw),'raw_hex':raw.hex()}))
    old={'schema':source.crash.EPOCH_SCHEMA,'code_commit':before,'committed_sources':old_rows,'carried_sources':old_copies}
    old_epoch=store.add(source.BATCH+'resume/current_code_epoch.json',old)
    old_resume=store.add(source.BATCH+'resume/resume.json',{'code_commit':before,'committed_sources':old_rows,
        'current_code_epoch_source':old_epoch})
    old_ready=store.add(source.BATCH+'scout_ready01/episode.json',{'code_commit':before,'committed_sources':old_rows,
        'current_code_epoch_source':old_epoch,'resume_source':old_resume})
    closure={'schema':source.CLOSURE_SCHEMA,'phase':source.PHASE,'excluded_failed_entry':True,
        'code_commit':before,'sources':{'ready':old_ready}}
    for member in source.NEW_FILES:current_raw[member]=('new '+member).encode()
    for member in source.CHANGED_OLD:current_raw[member]+=b' permitted transition'
    rows=[];copies=[]
    for i,member in enumerate(sorted(current_raw)):
        raw=current_raw[member];path=str(repo/member);sha=digest(raw)
        rows.append({'path':path,'sha256':sha})
        copies.append(store.add('evidence/current/resume/code_sources/'+str(i)+'.json',
            {'schema':source.indexed.stopped.CODE_SCHEMA,'code_commit':after,'original_path':path,
             'sha256':sha,'bytes':len(raw),'raw_hex':raw.hex()}))
    epoch={'schema':source.EPOCH_SCHEMA,'code_commit':after,'committed_sources':rows,'carried_sources':copies,
        'excluded_predecessor_code_commit':before}
    epoch_ref=store.add('evidence/current/resume/current_code_epoch.json',epoch)
    ready={'code_commit':after,'committed_sources':rows,'current_code_epoch_source':epoch_ref}
    return store,repo,closure,ready,deepcopy(ready),epoch,old,current_raw


def test_current_epoch_derives_exact_129_union_and_validates_both_raw_packages(tmp_path):
    store,repo,closure,ready,resume,epoch,previous,raw=epoch_case(tmp_path)
    result=source.validate_current_code_epoch(store,resume,ready,closure)
    assert result=={'code_commit':'c'*40,'complete_raw_source_members':129,'predecessor_publication_code_commit':'b'*40}
    old,actual_repo,wanted=source._epoch_paths(store,closure)
    assert actual_repo==repo and len(wanted)==len(previous['committed_sources'])+len(source.NEW_FILES)
    assert set(source.NEW_FILES)<=set(wanted)


@pytest.mark.parametrize('fault',['reuse','empty','invalid_commit','schema','extra_field','missing','extra',
    'duplicate','reorder','unrelated_changed','new_source_disguised','foreign_repo','old_commit_relabel',
    'old_empty','old_schema','old_raw','new_raw','missing_envelope','duplicate_envelope','resume_epoch',
    'resume_vector','ready_vector','old_ready_commit','old_resume_ref'])
def test_portable_epoch_rejects_stale_incomplete_relabelled_or_unrelated_sources(tmp_path,fault):
    store,repo,closure,ready,resume,epoch,previous,raw=epoch_case(tmp_path)
    if fault=='reuse':epoch['code_commit']=ready['code_commit']=resume['code_commit']=previous['code_commit']
    elif fault=='empty':epoch['committed_sources']=ready['committed_sources']=resume['committed_sources']=[];epoch['carried_sources']=[]
    elif fault=='invalid_commit':epoch['code_commit']=ready['code_commit']=resume['code_commit']='short'
    elif fault=='schema':epoch['schema']=source.crash.EPOCH_SCHEMA
    elif fault=='extra_field':epoch['invented_prior']={}
    elif fault=='missing':epoch['committed_sources'].pop()
    elif fault=='extra':epoch['committed_sources'].append({'path':str(repo/'zz_extra.py'),'sha256':'a'*64})
    elif fault=='duplicate':epoch['committed_sources'][1]=epoch['committed_sources'][0]
    elif fault=='reorder':epoch['committed_sources'].reverse()
    elif fault=='unrelated_changed':next(row for row in epoch['committed_sources'] if row['path'].endswith('/untouched.py'))['sha256']='a'*64
    elif fault=='new_source_disguised':next(row for row in epoch['committed_sources'] if row['path'].endswith(source.NEW_FILES[0]))['path']=str(repo/'renamed_new.py')
    elif fault=='foreign_repo':epoch['committed_sources'][0]['path']=str(tmp_path/'foreign/file.py')
    elif fault=='old_commit_relabel':epoch['excluded_predecessor_code_commit']='d'*40
    elif fault=='old_empty':previous['committed_sources'].clear();previous['carried_sources'].clear()
    elif fault=='old_schema':previous['schema']=source.EPOCH_SCHEMA
    elif fault=='old_raw':store.get(previous['carried_sources'][0],False)['raw_hex']='00'
    elif fault=='new_raw':store.get(epoch['carried_sources'][0],False)['raw_hex']='00'
    elif fault=='missing_envelope':epoch['carried_sources'].pop()
    elif fault=='duplicate_envelope':epoch['carried_sources'][1]=epoch['carried_sources'][0]
    elif fault=='resume_epoch':resume['current_code_epoch_source']=closure['sources']['ready']
    elif fault=='resume_vector':resume['committed_sources']=[]
    elif fault=='ready_vector':ready['committed_sources']=[]
    elif fault=='old_ready_commit':store.get(closure['sources']['ready'],False)['code_commit']='d'*40
    else:store.get(closure['sources']['ready'],False)['current_code_epoch_source']=ready['current_code_epoch_source']
    with pytest.raises((RuntimeError,KeyError)):source.validate_current_code_epoch(store,resume,ready,closure)


@pytest.mark.parametrize('fault',['reuse','empty','missing','extra','unrelated_changed'])
def test_writer_enforces_same_transition_before_creating_current_envelopes(tmp_path,monkeypatch,fault):
    store,repo,closure,ready,resume,epoch,previous,raw=epoch_case(tmp_path)
    monkeypatch.setattr(source.indexed,'ROOT',tmp_path)
    monkeypatch.setattr(source.indexed,'REPO',repo)
    monkeypatch.setattr(source,'local_store',lambda *args,**kwargs:store)
    from tools.client_compatibility import bag_swap_projection as projection
    rows=deepcopy(epoch['committed_sources']);commit=epoch['code_commit']
    if fault=='reuse':commit=previous['code_commit']
    elif fault=='empty':rows=[]
    elif fault=='missing':rows.pop()
    elif fault=='extra':rows.append({'path':str(repo/'zz_extra.py'),'sha256':'a'*64})
    else:next(row for row in rows if row['path'].endswith('/untouched.py'))['sha256']='a'*64
    monkeypatch.setattr(projection,'source_identities',lambda actual:rows)
    monkeypatch.setattr(source.subprocess,'check_output',lambda *a,**k:commit)
    directory=tmp_path/'evidence/current/resume';directory.mkdir(parents=True)
    with pytest.raises(RuntimeError):source.current_code_epoch(directory,{'closure':closure})
    assert not (directory/'code_sources').exists()


def test_writer_copies_fresh_committed_envelopes_for_complete_derived_union(tmp_path,monkeypatch):
    store,repo,closure,ready,resume,epoch,previous,raw=epoch_case(tmp_path)
    monkeypatch.setattr(source.indexed,'ROOT',tmp_path);monkeypatch.setattr(source.indexed,'REPO',repo)
    monkeypatch.setattr(source,'local_store',lambda *args,**kwargs:store)
    from tools.client_compatibility import bag_swap_projection as projection
    monkeypatch.setattr(projection,'source_identities',lambda actual:epoch['committed_sources'])
    def committed(command,**kwargs):
        return epoch['code_commit'] if command[1]=='rev-parse' else raw[command[2].split(':',1)[1]]
    monkeypatch.setattr(source.subprocess,'check_output',committed)
    original_write=source._write
    def written(path,value,root=None):
        ref=original_write(path,value,root);store.values[ref['path']]=value;return ref
    monkeypatch.setattr(source,'_write',written)
    directory=tmp_path/'evidence/current/resume';directory.mkdir(parents=True)
    ref=source.current_code_epoch(directory,{'closure':closure});created=store.get(ref,False)
    assert len(created['committed_sources'])==len(created['carried_sources'])==129
    assert created['excluded_predecessor_code_commit']==previous['code_commit']
    source.indexed.stopped._envelopes(store,created,created['committed_sources'],created['code_commit'])
