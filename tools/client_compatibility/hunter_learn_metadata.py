"""Pair retained Hunter native authority with the logger's ordered metadata.

Native::receive (native_bridge/native.cpp) emits ``native_packet`` immediately
before Events::packet for each packet in its serialized receive loop. Neither
record contains a shared sequence or body digest. Preserve the two archive
streams' order instead of treating every nearby equal-size event as a match.
Returned ordinals are derived positions, never claimed logger sequence IDs.
"""
from copy import deepcopy
import math


NATIVE_AUTHORITY_NAMES = frozenset(('SMSG_UPDATE_OBJECT', 'SMSG_DESTROY_OBJECT', 'SMSG_TRAINER_LIST',
    'SMSG_ON_MONSTER_MOVE', 'SMSG_ON_MONSTER_MOVE_TRANSPORT', 'SMSG_MOVE_UPDATE_TELEPORT'))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def packet_key(packet):
    return tuple(packet.get(k) for k in ('session', 'time', 'direction', 'name', 'body'))


def scoped(rows, session):
    selected = []
    for row in rows:
        require(isinstance(row, dict), 'native authority journal row is not an object')
        if row.get('session') == session and row.get('direction') == 'from_native' and row.get('name') in NATIVE_AUTHORITY_NAMES:
            selected.append(row)
            require(len(selected) <= 20000, 'native authority metadata exceeds its bounded journal')
    return selected


def native_authority_metadata(wire, events, required, *, session):
    """Validate complete collected streams and return their required native pairs.

    ``wire`` and ``events`` must already cover collect()'s same closed window.
    No time slicing or sorting is performed here. Unrelated directions, names
    and sessions do not belong to this native authority stream. Direct purchase
    and learn metadata retain their separate strict uniqueness checks.
    """
    require(type(session) is str and bool(session), 'native authority session is invalid')
    packets, metadata = scoped(wire, session), scoped(events, session)
    claimed = list(required)
    require(claimed and all(isinstance(p, dict) and p.get('session') == session and
        p.get('direction') == 'from_native' and p.get('name') in NATIVE_AUTHORITY_NAMES and
        finite(p.get('time')) and type(p.get('body')) is str for p in claimed),
        'required native authority belongs to another runtime session or protocol scope')
    require(len(packets) == len(metadata) and packets, 'native authority body and metadata stream counts differ')
    require(all(finite(p.get('time')) and type(p.get('body')) is str for p in packets) and
        all(finite(e.get('time')) and e.get('event') == 'native_packet' and
            type(e.get('bytes')) is int and 0 <= e['bytes'] <= 1024 * 1024 for e in metadata),
        'native authority body or metadata schema differs')
    keys = [packet_key(p) for p in packets]
    required_keys = [packet_key(p) for p in claimed]
    event_keys = [tuple(e[k] for k in ('session', 'time', 'direction', 'name', 'bytes', 'event')) for e in metadata]
    require(len(set(keys)) == len(keys) and len(set(event_keys)) == len(event_keys) and
        len(set(required_keys)) == len(required_keys) and set(required_keys) <= set(keys),
        'native authority required/body/metadata rows are duplicate or missing')
    required_keys = set(required_keys)
    pairs = []
    for ordinal, (packet, event) in enumerate(zip(packets, metadata)):
        try:
            body = bytes.fromhex(packet['body'])
        except ValueError as error:
            raise RuntimeError('native authority packet body is not hexadecimal') from error
        require(body.hex() == packet['body'] and packet['name'] == event['name'] and len(body) == event['bytes'] and
            0 <= packet['time'] - event['time'] < .1,
            'ordered native authority opcode, body size or event-before-body time differs')
        if ordinal:
            require(packets[ordinal - 1]['time'] <= packet['time'] and metadata[ordinal - 1]['time'] <= event['time'],
                'native authority journal stream order differs')
        if ordinal + 1 < len(metadata):
            # Equality permits floating-point timestamp rounding; source row
            # order still identifies each event/body pair exactly once.
            require(packet['time'] <= metadata[ordinal + 1]['time'],
                'native authority body follows the next receive metadata event')
        if packet_key(packet) in required_keys:
            pairs.append({'ordinal': ordinal, 'packet': deepcopy(packet), 'metadata': deepcopy(event)})
    require(len(pairs) == len(claimed), 'required native authority is absent from the complete ordered stream')
    return pairs
