import struct
import pytest
from tools.client_compatibility.content_census import dbc_ids,SQL_TABLES


def test_census_preserves_record_stride_for_byte_columns(tmp_path):
    path=tmp_path/'Achievement_Criteria.dbc'
    path.write_bytes(struct.pack('<4s4I',b'WDBC',2,4,7,1)+
        struct.pack('<I3sI3s',101,b'abc',102,b'def')+b'\0')
    assert dbc_ids(path)==[101,102]
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ValueError,match='layout'):dbc_ids(path)


def test_native_item_inventory_uses_cataclysm_hotfix_table():
    assert SQL_TABLES['items_hotfix']==('hotfixes','item','ID')
    assert all(role in ['world','hotfixes'] for role,_,_ in SQL_TABLES.values())
