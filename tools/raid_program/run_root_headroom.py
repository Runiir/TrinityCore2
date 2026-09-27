"""Writable headroom of a run root: free space and the user's filesystem quota.

The worldserver's stdout is a regular file in the run root (``stdout=log``).
glibc drops a buffered ``printf`` whose write(2) fails, so an exhausted
filesystem or user quota does not stop the server: a console reply is cut at
a 4 KiB stdio boundary, its ``TC>`` prompt never arrives and the coordinator
waits out the command timeout.  ``/tmp`` here is a tmpfs mounted with
``usrquota``: ``df`` (statvfs) can report gigabytes free while the user's
quota is exhausted, so both limits are read.
"""
from __future__ import annotations

import ctypes
import os
import platform
import time
from pathlib import Path
from typing import Any, Callable

GIB = 1024 ** 3
# A three-hour full-raid shard with bounded heartbeat traces writes about
# 2 MB of console output per 30 s heartbeat (~0.7 GiB) plus its reports.
DEFAULT_MIN_HEADROOM_BYTES = 2 * GIB

_SYS_QUOTACTL_FD = 443  # same number in the unified syscall table (x86_64, aarch64)
_Q_GETQUOTA = 0x800007
_USRQUOTA = 0
_QIF_BLIMITS = 1
_QIF_SPACE = 4
_QUOTA_BLOCK_BYTES = 1024


class _DiskQuota(ctypes.Structure):
    _fields_ = [("dqb_bhardlimit", ctypes.c_uint64), ("dqb_bsoftlimit", ctypes.c_uint64),
                ("dqb_curspace", ctypes.c_uint64), ("dqb_ihardlimit", ctypes.c_uint64),
                ("dqb_isoftlimit", ctypes.c_uint64), ("dqb_curinodes", ctypes.c_uint64),
                ("dqb_btime", ctypes.c_uint64), ("dqb_itime", ctypes.c_uint64),
                ("dqb_valid", ctypes.c_uint32)]


def enforceable_quota(*, hard_bytes: int, soft_bytes: int, used_bytes: int, grace_expires_unix: int,
                      now: float) -> dict[str, Any]:
    """The block ceiling the kernel enforces right now (fs/quota/dquot.c check_bdq).

    The hard limit always refuses writes past it.  The soft limit refuses
    writes only once its grace timer has expired (btime set and reached); a
    usage over the soft limit with btime unset starts the timer on the next
    write, which succeeds.  ``limit_bytes`` is None when nothing caps writes.
    """
    over_soft = bool(soft_bytes) and used_bytes > soft_bytes
    grace_expired = over_soft and bool(grace_expires_unix) and now >= grace_expires_unix
    grace_active = over_soft and bool(grace_expires_unix) and not grace_expired
    ceilings = [value for value in (hard_bytes, soft_bytes if grace_expired else 0) if value]
    return {"hard_limit_bytes": hard_bytes or None, "soft_limit_bytes": soft_bytes or None,
            "used_bytes": used_bytes, "grace_expires_unix": grace_expires_unix or None,
            "over_soft_limit": over_soft, "grace_active": grace_active, "grace_expired": grace_expired,
            "limit_bytes": min(ceilings) if ceilings else None}


def user_quota(path: Path, *, now: Callable[[], float] = time.time) -> dict[str, Any] | None:
    """The caller's block quota on path's filesystem (see enforceable_quota).

    None when the platform, filesystem or kernel reports no quota limits.
    """
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "aarch64"}:
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return None
    try:
        quota = _DiskQuota()
        command = ctypes.c_uint((_Q_GETQUOTA << 8) | _USRQUOTA)
        if libc.syscall(_SYS_QUOTACTL_FD, descriptor, command, os.getuid(), ctypes.byref(quota)) != 0:
            return None
    finally:
        os.close(descriptor)
    if not quota.dqb_valid & _QIF_BLIMITS or not quota.dqb_valid & _QIF_SPACE:
        return None
    if not quota.dqb_bhardlimit and not quota.dqb_bsoftlimit:
        return None
    return enforceable_quota(hard_bytes=int(quota.dqb_bhardlimit) * _QUOTA_BLOCK_BYTES,
                             soft_bytes=int(quota.dqb_bsoftlimit) * _QUOTA_BLOCK_BYTES,
                             used_bytes=int(quota.dqb_curspace), grace_expires_unix=int(quota.dqb_btime),
                             now=now())


def writable_headroom(path: Path, *,
                      quota_reader: Callable[[Path], dict[str, Any] | None] = user_quota) -> dict[str, Any]:
    """Bytes the caller can still write under path: min(free space, enforceable quota remaining)."""
    folder = Path(path)
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    stats = os.statvfs(folder)
    available = int(stats.f_bavail) * int(stats.f_frsize)
    quota = quota_reader(folder)
    row: dict[str, Any] = {"path": str(folder), "filesystem_available_bytes": available,
                           "quota": quota, "quota_limit_bytes": None, "quota_used_bytes": None,
                           "quota_available_bytes": None}
    headroom = available
    if quota is not None and quota.get("limit_bytes") is not None:
        remaining = max(0, int(quota["limit_bytes"]) - int(quota["used_bytes"]))
        row.update(quota_limit_bytes=int(quota["limit_bytes"]), quota_used_bytes=int(quota["used_bytes"]),
                   quota_available_bytes=remaining)
        headroom = min(headroom, remaining)
    row["headroom_bytes"] = headroom
    return row


def safe_headroom(path: Path) -> dict[str, Any]:
    """writable_headroom for diagnostics: never raises."""
    try:
        return writable_headroom(path)
    except OSError as error:
        return {"path": str(path), "error": f"{type(error).__name__}: {error}"}
