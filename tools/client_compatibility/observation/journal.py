"""Incremental observation across owned trace rotations, without lost facts."""
import json


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


def player_entry(root):
    latest = None
    for record in entries(root / 'logs/modern_world.jsonl'):
        if record['event'] == 'native_player_created' and record['guid'] == 1: latest = record
    if not latest: raise RuntimeError('owned character has not entered the native world')
    return latest
