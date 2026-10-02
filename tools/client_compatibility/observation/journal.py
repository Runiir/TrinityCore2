"""Incremental observation across owned trace rotations, without lost facts."""
import json
import os


def paths(path):
    return sorted(path.parent.glob(path.name + '.part-*')) + ([path] if path.exists() else [])


class Cursor:
    def __init__(self, path):
        self.path, self.offsets = path, {}

    def poll(self):
        for path in paths(self.path):
            try: handle = path.open()
            except FileNotFoundError: continue
            with handle:
                import os
                stat = os.fstat(handle.fileno()); identity = (stat.st_dev, stat.st_ino)
                offset = self.offsets.get(identity, 0)
                if stat.st_size < offset: raise RuntimeError('owned journal was truncated before checkpoint')
                handle.seek(offset)
                while line := handle.readline():
                    if not line.endswith('\n'): break
                    self.offsets[identity] = handle.tell()
                    yield json.loads(line)


def entries(path):
    return Cursor(path).poll()


def character_guid(value=None):
    """Explicit actor identity; legacy single-client commands keep GUID 1."""
    raw=value if value is not None else os.environ.get('CLIENT442_CHARACTER_GUID','1')
    if isinstance(raw,bool):raise ValueError('invalid client442 character GUID')
    try:guid=int(raw)
    except (TypeError,ValueError):raise ValueError('invalid client442 character GUID') from None
    if str(guid)!=str(raw) or not 0<guid<=0xffffffff:
        raise ValueError('client442 character GUID must be a positive native player counter')
    return guid


def player_entry(root,guid=None,session=None):
    guid=character_guid(guid)
    session=session if session is not None else os.environ.get('CLIENT442_SESSION')
    latest = None
    for record in entries(root / 'logs/modern_world.jsonl'):
        if (record['event'] == 'native_player_created' and record['guid'] == guid and
            (session is None or record['session']==session)):latest = record
    if not latest: raise RuntimeError('owned character has not entered the native world')
    return latest
