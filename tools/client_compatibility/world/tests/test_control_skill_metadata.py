"""Native class-skill evidence and pinned441+ hotfix wire widths; no learning."""
import copy
import hashlib
import json
import struct
from types import SimpleNamespace
import pytest
from tools.client_compatibility import lab_runtime as lab
from tools.client_compatibility.world import hotfixes
from tools.client_compatibility.world.control_skill_metadata import convert, TABLE
from tools.client_compatibility.world.buffer import Reader, Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec, result


def config():
    return json.loads((lab.REPO/'experiments/configs/client_harness/control_skill_metadata_v1.json').read_text())


def small(rows=None):
    spec=config()
    rows=rows if rows is not None else [r['native_values'] for r in spec['records']]
    native=struct.pack('<4s4I',b'WDBC',len(rows),14,56,1)
    native+=b''.join(struct.pack('<14I',*r) for r in rows)+b'\0'
    spec['native_source_sha256']=hashlib.sha256(native).hexdigest()
    return native,spec


def test_real_pinned_native_dbc_and_cpp_preserve_positive_class_skill_records(codec):
    native=(lab.ROOT/'data/dbc/enUS/SkillLineAbility.dbc').read_bytes();spec=config()
    assert hashlib.sha256(native).hexdigest()==spec['native_source_sha256']
    expected=convert(native,spec)
    assert result(codec,op='control_skill_hotfixes',native=native.hex(),config=spec)==expected
    assert len(expected)==4
    for row,spell,skill,class_mask in zip(expected,[80388,93375,79682,93321],[354,354,50,50],[256,256,4,4]):
        body=bytes.fromhex(row['data']);assert len(body)==55
        # Independent pinned WPP441 sequence, rather than native packed fields.
        r=Reader(body)
        assert r.unpack('qIhi')==(0,row['record_id'],skill,spell)
        assert r.unpack('hiii')==(1,class_mask,0,0)
        assert r.unpack('hhibhhhii')==(0,0,0,0,0,0,0,0,0);r.end()


@pytest.mark.parametrize('change',[
    'schema','client','native','table','layout','digest','count','record_id',
    'push','unique','source_values','order','race','class','skill','spell','rank',
    'acquire','next_rank','exclusion','duplicate','missing','signature','width','truncated','trailing'])
def test_cpp_and_python_refuse_unpinned_or_semantically_changed_skill_metadata(codec,change):
    native,spec=small()
    if change in ['schema','client','native','table','layout','digest']:
        key={'schema':'schema','client':'client_build','native':'native_build','table':'table_hash',
            'layout':'layout_hash','digest':'native_source_sha256'}[change]
        spec[key]='wrong' if isinstance(spec[key],str) else spec[key]+1
    elif change=='count':spec['records'].append(copy.deepcopy(spec['records'][0]))
    elif change in ['record_id','push','unique']:
        key={'record_id':'record_id','push':'push_id','unique':'unique_id'}[change];spec['records'][0][key]+=1
    elif change=='source_values':spec['records'][0]['native_values'][4]=1
    elif change=='order':spec['records'].reverse()
    else:
        rows=[r['native_values'][:] for r in spec['records']]
        if change in ['race','class','skill','spell','rank','acquire','next_rank','exclusion']:
            column={'race':3,'class':4,'skill':1,'spell':2,'rank':7,'acquire':9,'next_rank':8,'exclusion':5}[change]
            rows[0][column]+=1
            spec['records'][0]['native_values']=rows[0][:]
        elif change=='duplicate':rows.append(rows[0][:])
        elif change=='missing':rows.pop()
        native,_=small(rows)
        if change=='signature':native=b'WRNG'+native[4:]
        elif change=='width':native=native[:12]+struct.pack('<I',55)+native[16:]
        elif change=='truncated':native=native[:-1]
        elif change=='trailing':native+=b'x'
        spec['native_source_sha256']=hashlib.sha256(native).hexdigest()
    with pytest.raises(ValueError):convert(native,spec)
    assert 'error' in codec(op='control_skill_hotfixes',native=native.hex(),config=spec)


def test_four_skill_records_use_standard_hotfix_connect_and_bulk_lookup():
    rows=[r for r in hotfixes.records() if r['table_hash']==TABLE]
    assert [r['record_id'] for r in rows]==[21975,23872,21959,23785]
    sent=[];session=SimpleNamespace(send=lambda n,b:sent.append((n,b)))
    hotfixes.request(session,Writer().pack('III4i',60895,0,4,*[r['push_id'] for r in rows]).finish())
    assert sent[0][0]=='SMSG_HOTFIX_CONNECT'
    r=Reader(sent[0][1]);assert r.unpack('I')==(4,)
    for row in rows:
        assert r.unpack('IIIiI')==(row['push_id'],row['unique_id'],TABLE,row['record_id'],55)
        assert r.bits(3)==1;r.align()
    assert r.unpack('I')==(220,)
    for row in rows:
        body=r.raw(55);assert body==hotfixes.lookup(TABLE,row['record_id'])==bytes.fromhex(row['data'])
    r.end()


@pytest.mark.parametrize('index',[2,3])
@pytest.mark.parametrize('column',[1,2,3,4,7,8])
def test_hunter_rows_cannot_borrow_warlock_skill_class_or_other_rank_semantics(codec,index,column):
    native,spec=small();rows=[r['native_values'][:] for r in spec['records']]
    rows[index][column]+=1;spec['records'][index]['native_values']=rows[index][:]
    native,_=small(rows);spec['native_source_sha256']=hashlib.sha256(native).hexdigest()
    with pytest.raises(ValueError):convert(native,spec)
    assert 'error' in codec(op='control_skill_hotfixes',native=native.hex(),config=spec)
