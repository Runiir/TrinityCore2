"""Keep a verified gzip archive identity stable through DVC processing."""
import gzip
from . import lab_runtime as lab


def archive_digest(path):
    # Reading through gzip EOF validates the compressed stream's CRC and size.
    with gzip.open(path,'rb') as stream:
        while stream.read(1024*1024):pass
    return lab.sha256(path)


def unchanged_archive(path,expected):
    if lab.sha256(path)!=expected:
        raise RuntimeError('workspace checkpoint archive changed after source integrity verification')
