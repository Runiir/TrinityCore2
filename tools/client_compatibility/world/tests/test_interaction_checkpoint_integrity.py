"""Archive receipts must identify verified bytes even after DVC processing."""
import gzip
import hashlib
import pytest
from tools.client_compatibility.checkpoint_interactions import archive_digest,unchanged_archive


def test_complete_gzip_integrity_and_stable_workspace(tmp_path):
    path=tmp_path/'archive.gz';path.write_bytes(gzip.compress(b'captured source evidence'*1000))
    expected=hashlib.sha256(path.read_bytes()).hexdigest()
    assert archive_digest(path)==expected
    unchanged_archive(path,expected)


@pytest.mark.parametrize('fault',['crc','truncated'])
def test_full_stream_rejects_crc_damage_or_truncation(tmp_path,fault):
    path=tmp_path/'archive.gz';data=bytearray(gzip.compress(b'captured source evidence'*1000))
    if fault=='crc':data[-8]^=1
    else:del data[-4:]
    path.write_bytes(data)
    with pytest.raises((gzip.BadGzipFile,EOFError)):archive_digest(path)


def test_changed_workspace_cannot_replace_the_verified_archive_identity(tmp_path):
    path=tmp_path/'archive.gz';path.write_bytes(gzip.compress(b'captured source evidence'*1000))
    expected=archive_digest(path);data=bytearray(path.read_bytes());data[20]^=1;path.write_bytes(data)
    with pytest.raises(RuntimeError,match='changed after source integrity'):unchanged_archive(path,expected)
