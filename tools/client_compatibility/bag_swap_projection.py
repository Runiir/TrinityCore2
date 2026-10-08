"""Decode delivered occupied-backpack GUID deltas without claiming PNG GUIDs."""
import hashlib
from pathlib import Path
import struct
import subprocess

from .item_actionbar_contract import require, packet_rows, body
from .world.buffer import Reader, player_high

ITEM_HIGH = (3 << 58) | (1 << 42)
SLOTS = (35, 36)
SOURCE_FILES = (
    'tools/client_compatibility/item_actionbar_contract.py',
    'tools/client_compatibility/item_actionbar_preservation.py',
    'tools/client_compatibility/world/buffer.py',
    'tools/client_compatibility/world/native_objects.py',
    'tools/client_compatibility/world/native_transport.py',
    'tools/client_compatibility/world/movement.py',
    'tools/client_compatibility/world/native_movement.json',
    'tools/client_compatibility/native_bridge/movement.cpp',
    'tools/client_compatibility/native_bridge/client_requests.cpp',
    'tools/client_compatibility/native_bridge/chat.cpp',
    'tools/client_compatibility/native_bridge/protocol.cpp',
    'tools/client_compatibility/native_bridge/buffer.cpp',
    'tools/client_compatibility/native_bridge/buffer.hpp',
    'tools/client_compatibility/native_bridge/inventory_requests.cpp',
    'tools/client_compatibility/native_bridge/inventory_updates.cpp',
    'tools/client_compatibility/native_bridge/native_objects.cpp',
    'tools/client_compatibility/world/native_fields.json',
    'tools/client_compatibility/world/fields.json',
    'tools/client_compatibility/interaction_item_actionbar_parked_selection_capture.py',
    'tools/client_compatibility/interaction_trial.py',
    'tools/client_compatibility/interaction_bridge_deploy.py',
    'tools/client_compatibility/interaction_parked_client_resource_pause.py',
    'tools/client_compatibility/interaction_single_scout_bridge_deploy.py',
    'tools/client_compatibility/interaction_item_actionbar_continuation.py',
    'tools/client_compatibility/interaction_item_actionbar.py',
    'tools/client_compatibility/interaction_owned_class_fixture.py',
    'tools/client_compatibility/interaction_primary_combat_reentry.py',
    'tools/client_compatibility/interaction_social.py',
    'tools/client_compatibility/owned_input.py',
    'tools/client_compatibility/actors.py',
    'tools/client_compatibility/lab_runtime.py',
    'tools/client_compatibility/observation/journal.py',
    'tools/client_compatibility/observation/interactions.py',
    'src/server/game/Handlers/MiscHandler.cpp',
    'src/server/game/Entities/Unit/Unit.cpp',
    'src/server/game/Entities/Unit/UnitDefines.h',
    'src/server/game/Server/WorldSession.h',
    'src/server/game/Entities/Player/Player.cpp',
    'src/server/game/Handlers/ItemHandler.cpp',
)

# Keep the legacy vectors above intact. The next stopped-entry epoch also binds
# the asynchronous native queue and the actual socket-loss expiry source.
STOPPED_SOURCE_FILES = (
    'tools/client_compatibility/native_bridge/native.cpp',
    'tools/client_compatibility/native_bridge/channel.cpp',
    'tools/client_compatibility/native_bridge/main.cpp',
    'src/server/game/Server/WorldSession.cpp',
)


def source_identities(repo):
    """Freeze the narrow controller, tests, contract, and wire-layout sources."""
    repo = Path(repo)
    from .bag_swap_failed_evidence import PUBLICATION_DEPENDENCIES
    from .bag_swap_indexed_sources import INDEXED_DEPENDENCIES
    paths = sorted([str(p.relative_to(repo)) for p in (repo / 'tools/client_compatibility').glob('*bag_swap*.py')] +
        [str(p.relative_to(repo)) for p in (repo / 'tools/client_compatibility/world/tests').glob('test_bag_swap*.py')] +
        ['experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json'] + list(SOURCE_FILES) +
        list(PUBLICATION_DEPENDENCIES) + list(STOPPED_SOURCE_FILES) + list(INDEXED_DEPENDENCIES))
    require(len(paths) == len(set(paths)) and len(paths) >= 16, 'complete swap source identities are required')
    result = []
    for relative in paths:
        path = repo / relative
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'ordinary swap source required')
        raw = path.read_bytes()
        require(subprocess.check_output(['git', 'show', 'HEAD:' + relative], cwd=repo) == raw,
            'swap controller/config/test source must match its actual committed HEAD bytes')
        result.append({'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()})
    return result


def mask(reader, width, first32=False):
    present = reader.unpack('I')[0] | reader.bits(width - 32) << 32 if first32 else reader.bits(width)
    require(present < 1 << width, 'delivered inventory mask exceeds its fixed width')
    parts = {i: reader.bits(32) for i in range(width) if present & (1 << i)}
    return {i * 32 + bit for i, value in parts.items() for bit in range(32) if value & (1 << bit)}


def delta(raw):
    """Fully consume the bridge's bounded, inventory-only ActivePlayerData block.

    Other sized object blocks are skipped without interpreting their contents.
    An actor2 inventory block must have exactly the two public slot children.
    """
    try:
        reader = Reader(raw)
        map_id, count = reader.unpack('HI')
        require(map_id == 0 and count <= 256 and reader.bits(1) == 1, 'delivered object header differs')
        removed = reader.bits(1)
        if removed:
            destroyed, total = reader.unpack('HI')
            require(destroyed <= total <= 4096, 'delivered removal count differs')
            for _ in range(total):
                identity = reader.guid()
                require(identity != (2, player_high()), 'delivered owner removed during swap')
                require(identity not in ((33, ITEM_HIGH), (41, ITEM_HIGH)),
                    'delivered occupied swap item removed during swap')
        size = reader.unpack('I')[0]
        data = Reader(reader.raw(size))
        reader.end()
        found = []
        for _ in range(count):
            kind = data.unpack('B')[0]
            require(kind == 0, 'swap delivery requires sized value-update blocks')
            identity = data.guid()
            block = Reader(data.raw(data.unpack('I')[0]))
            if identity != (2, player_high()):
                continue
            visibility, fragment, layout, roots = block.unpack('BBBI')
            require(not roots & (1 << 7) or roots == 1 << 7,
                'unsupported owned inventory roots must not hide alongside an exact delivery')
            if roots != 1 << 7:
                continue
            require((visibility, fragment, layout) == (1, 0, 3), 'owned inventory root header differs')
            fields = mask(block, 46, True)
            block.align()
            inventory = {131, 132 + 35, 132 + 36}
            if not fields & {131, *range(132, 278)}:
                continue
            require(fields == inventory, 'occupied swap delivery changed other active-player fields')
            guids = [block.guid(), block.guid()]
            block.end()
            require(all(high == ITEM_HIGH and low in (33, 41) for low, high in guids) and
                {low for low, _ in guids} == {33, 41}, 'delivered occupied item GUID identities differ')
            found.append({'35': list(guids[0]), '36': list(guids[1])})
        data.end()
        require(len(found) <= 1, 'duplicate owned inventory projection in one delivery')
        return found[0] if found else None
    except (ValueError, IndexError, struct.error) as error:
        raise RuntimeError('delivered occupied inventory body cannot be consumed exactly') from error


def delivered_slots(rows, session, since, until, *, swapped):
    require(type(swapped) is bool, 'typed occupied swap state required')
    expected = {'35': [33 if swapped else 41, ITEM_HIGH], '36': [41 if swapped else 33, ITEM_HIGH]}
    found = []
    for row in packet_rows(rows, session, since, until):
        if row.get('name') == 'SMSG_UPDATE_OBJECT' and row.get('direction') == 'to_client':
            value = delta(body(row))
            if value is not None:
                require(value == expected, 'delivered public inventory GUIDs differ from owned swap state')
                found.append({'packet': row, 'slots': value})
    require(len(found) == 1, 'one exact delivered two-slot inventory GUID projection is required')
    return {'public_slots': expected, 'delivery': found[0]['packet'], 'native_sql_slots': [23, 24],
        'rendered_guid_claim': False}
