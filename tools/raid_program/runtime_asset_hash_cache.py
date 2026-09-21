"""Local hash reuse, never an asset authority. Changed stat identity rehashes.

Every hit still requires an open regular file and the caller's race/path checks.
The cache is local trusted-user state, not portable qualification evidence.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import os
from pathlib import Path
import sqlite3

ACTIVE = ContextVar("runtime_asset_hash_cache", default=None)


def signature(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def hash_descriptor(fd, value):
    cache = ACTIVE.get()
    key = repr(signature(value))
    if cache:
        hit = cache["rows"].get(key)
        if hit:
            cache["hits"] += 1
            return hit
    digest = hashlib.sha256()
    while chunk := os.read(fd, 1024 * 1024):
        digest.update(chunk)
        if cache:
            cache["bytes_hashed"] += len(chunk)
    result = digest.hexdigest()
    if cache:
        cache["rows"][key] = result
        cache["misses"] += 1
    return result


@contextmanager
def cached_hashes(path=None):
    """Cache failure falls back to hashing. Boot ID prevents inode reuse after reboot."""
    if ACTIVE.get() is not None:
        yield ACTIVE.get()
        return
    db = None
    rows = {}
    if path is not None:
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            db = sqlite3.connect(path, timeout=1)
            db.execute("CREATE TABLE IF NOT EXISTS hashes (boot TEXT, identity TEXT, sha TEXT, PRIMARY KEY(boot, identity))")
            rows = {k: v for k, v in db.execute("SELECT identity, sha FROM hashes WHERE boot=?", (boot,))
                    if isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)}
        except (OSError, sqlite3.Error):
            if db:
                db.close()
            db = None
    cache = {"rows": rows, "hits": 0, "misses": 0, "bytes_hashed": 0}
    token = ACTIVE.set(cache)
    try:
        yield cache
    finally:
        ACTIVE.reset(token)
        if db:
            try:
                # Bound growth: retain only this boot's recently observed identities.
                db.execute("DELETE FROM hashes")
                db.executemany("INSERT INTO hashes VALUES (?, ?, ?)",
                               ((boot, k, v) for k, v in list(rows.items())[-50000:]))
                db.commit()
            except sqlite3.Error:
                pass
            finally:
                db.close()


def default_cache_path():
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "trinity-cata/asset-hashes.sqlite3"
