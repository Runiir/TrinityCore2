"""Incremental observation across owned trace rotations, without lost facts."""
import json
import os


def paths(path):
    return sorted(path.parent.glob(path.name + '.part-*')) + ([path] if path.exists() else [])


class Cursor:
    def __init__(self, path):
        self.path, self.offsets = path, {}

    def _sources(self):
        """Pin a stable ordered inode set before streaming historical rows.

        Opening the active path after reading old parts can instead open its
        replacement and omit the renamed inode. Retry discovery before yielding
        any rows; a later rotation remains readable through the pinned handle.
        """
        minimum = None
        historical, required = {}, set()

        def remember(source, stat):
            identity = (stat.st_dev, stat.st_ino)
            if source != self.path:
                if historical.setdefault(source, identity) != identity:
                    raise RuntimeError('historical journal source was replaced before checkpoint')
            return identity

        for _ in range(4):
            handles, accepted = [], False
            try:
                listed = paths(self.path)
                if minimum is None: minimum = len(listed)
                for source in listed:
                    try:
                        if source != self.path: remember(source, source.stat())
                        handle = source.open()
                        handles.append(handle)
                        required.add(remember(source, os.fstat(handle.fileno())))
                    except FileNotFoundError:
                        if source != self.path:
                            raise RuntimeError('historical journal source disappeared before checkpoint') from None
                        break
                else:
                    current = paths(self.path)
                    identities = []
                    for source in current:
                        try: stat = source.stat()
                        except FileNotFoundError:
                            if source != self.path:
                                raise RuntimeError('historical journal source disappeared before checkpoint') from None
                            break
                        identities.append(remember(source, stat))
                    else:
                        # A retry must retain every historical path/inode fact,
                        # even when another rotation keeps the file count equal.
                        for source in historical:
                            try: stat = source.stat()
                            except FileNotFoundError:
                                raise RuntimeError('historical journal source disappeared before checkpoint') from None
                            remember(source, stat)
                        pinned = [(stat.st_dev, stat.st_ino) for stat in
                            (os.fstat(handle.fileno()) for handle in handles)]
                        if len(current) >= minimum and pinned == identities and required <= set(identities):
                            accepted = True
                            return handles
            finally:
                if not accepted:
                    for handle in handles: handle.close()
        raise RuntimeError('owned journal inode inventory did not stabilize before checkpoint')

    def poll(self):
        handles = self._sources()
        try:
            for handle in handles:
                stat = os.fstat(handle.fileno()); identity = (stat.st_dev, stat.st_ino)
                offset = self.offsets.get(identity, 0)
                if stat.st_size < offset: raise RuntimeError('owned journal was truncated before checkpoint')
                handle.seek(offset)
                while line := handle.readline():
                    if not line.endswith('\n'): break
                    self.offsets[identity] = handle.tell()
                    yield json.loads(line)
        finally:
            for handle in handles: handle.close()


def entries(path):
    return Cursor(path).poll()


def latest(path,predicate):
    """Find a current fact without decoding every historical rotation."""
    for source in reversed(paths(path)):
        try:
            with source.open('rb') as handle:lines=handle.readlines()
        except FileNotFoundError:continue
        for line in reversed(lines):
            if not line.endswith(b'\n'):continue
            record=json.loads(line)
            if predicate(record):return record
    return None


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
    found=latest(root/'logs/modern_world.jsonl',lambda r:r.get('event')=='native_player_created' and
        r.get('guid')==guid and (session is None or r.get('session')==session))
    if not found:raise RuntimeError('owned character has not entered the native world')
    return found
