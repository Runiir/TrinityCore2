from __future__ import annotations

import hashlib
import json
from typing import Any


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _uint64_int(value: Any) -> bool:
    return _nonnegative_int(value) and value <= (1 << 64) - 1


def _canonical_object_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
