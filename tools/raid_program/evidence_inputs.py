"""Read retained JSON without extracting archives or printing payloads."""
from __future__ import annotations

import hashlib
from itertools import islice
import json
import tarfile
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_input(spec):
    """An exact archive::member selects one regular file, never a fuzzy match."""
    path, sep, member = str(spec).partition("::")
    if sep:
        with tarfile.open(path) as archive:
            matches = [m for m in archive if m.name == member]
            if len(matches) != 1 or not matches[0].isfile():
                raise ValueError("archive member must identify exactly one regular file")
            payload = archive.extractfile(matches[0]).read()
    else:
        payload = Path(path).read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value, {"input": str(spec), "payload_sha256": hashlib.sha256(payload).hexdigest(),
                   "payload_bytes": len(payload)}


def inventory(value, receipt):
    """Describe structure without rendering arrays or embedded reports."""
    from tools.raid_program.evidence_metrics import native_actors
    try:
        actors = [{k: a[k] for k in ("actor", "name", "spec", "role", "dps", "hps")}
                  for a in native_actors(value).values()]
    except ValueError:
        actors = []
    return {"schema": "evidence_inventory_v1", "source": receipt,
            "input_schema": value.get("schema"), "actors": actors,
            "fields": {k: {"type": type(v).__name__, "items": len(v) if isinstance(v, (dict, list)) else None}
                       for k, v in value.items()},
            "note": "Use compare for metrics; events for filtered records. No raw payload printed."}


def resolve_pointer(document, pointer):
    if not pointer.startswith("/") or pointer == "/":
        raise ValueError("--path must be an explicit JSON Pointer, e.g. /events/12")
    value = document
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not key.isdigit():
                raise ValueError("array path requires a nonnegative index")
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise ValueError("path continues past a scalar")
    return value


def select_path(document, pointer, offset=0, limit=10):
    """Explicit JSON Pointer selection for details omitted from event projections."""
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset must be nonnegative and limit 1..100")
    value = resolve_pointer(document, pointer)
    count = len(value) if isinstance(value, (list, dict)) else 1
    if isinstance(value, list):
        page = value[offset:offset+limit]
    elif isinstance(value, dict):
        page = dict(list(value.items())[offset:offset+limit])
    else:
        page = value if offset == 0 else None
    return {"path": pointer, "total_items": count, "offset": offset,
            "next_offset": offset+limit if offset+limit < count else None, "value": page}


def node_inventory(document, pointer, offset=0, limit=20):
    """List nested field names/types/locators without rendering their payloads."""
    from tools.raid_program.evidence_paging import pointer_child
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError('offset must be nonnegative and limit 1..100')
    value = resolve_pointer(document, pointer)
    fields = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else []
    count = len(value) if isinstance(value, (dict, list)) else 0
    rows = [{'name': key, 'path': pointer_child(pointer, key), 'type': type(item).__name__,
             'items': len(item) if isinstance(item, (dict, list)) else None,
             'characters': len(item) if isinstance(item, str) else None}
            for key, item in islice(fields, offset, offset+limit)]
    return {'schema': 'evidence_node_inventory_v1', 'path': pointer, 'node_type': type(value).__name__,
            'total_items': count, 'offset': offset, 'value': rows,
            'next_offset': offset+limit if offset+limit < count else None}
