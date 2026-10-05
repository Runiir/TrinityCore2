"""Decode the public archaeology snapshot, rejecting partial screenshot updates."""
import math
import struct
from tools.client_compatibility.observation.telemetry import checksum

HEADER = struct.Struct('>4sHIIHHIIIIIIHHBB')
RACE = struct.Struct('>BHHBHI')
MARKER = struct.Struct('>QHHHHH')
ARROW = struct.Struct('>IIHHI')


def decode(data):
    if len(data) < HEADER.size + 2 or len(data) > 512:
        raise ValueError('archaeology snapshot has invalid length')
    values = HEADER.unpack_from(data)
    magic, length, sequence, uptime, flags, instance, north, west, surveys, at, finds, site, jars, recipe, races, markers = values
    if (magic != b'TCA1' or length != len(data) or races > 16 or markers > 8 or flags & ~4095
            or length != HEADER.size + races * RACE.size + markers * MARKER.size + (ARROW.size if flags & 128 else 0)
            + (4 if flags & 256 else 0) + (2 if flags & 1024 else 0) + 2
            or checksum(data[:-2]) != int.from_bytes(data[-2:], 'big')):
        raise ValueError('archaeology snapshot failed layout or checksum validation')
    offset = HEADER.size
    race_rows, marker_rows = [], []
    for _ in range(races):
        index, fragments, cost, sockets, bags, spell = RACE.unpack_from(data, offset)
        offset += RACE.size
        race_rows.append({'index': index, 'fragments': fragments, 'cost': cost,
                          'sockets': sockets, 'keystones_in_bags': bags, 'project_spell': spell})
    for _ in range(markers):
        coord, x, y, distance, angle, node = MARKER.unpack_from(data, offset)
        offset += MARKER.size
        marker_rows.append({'marker_id': str(coord), 'position': {'x': x/65535, 'y': y/65535},
                            'distance_yards': distance/100, 'heading_radians': angle/65535*math.tau,
                            'node_id': node, 'source': 'visible_GatherMate_minimap_frame'})
    arrow = None
    if flags & 128:
        n,w,angle,length,arrow_at=ARROW.unpack_from(data,offset)
        offset += ARROW.size
        heading=angle/65535*math.tau
        arrow={'observed_at':arrow_at,'heading_radians':heading,'length_yards':length/100,
               'boundary_verified':bool(flags & 2048),
               'origin':{'instance':instance,'north':n/100-100000,'west':w/100-100000},
               'endpoint':{'instance':instance,'north':n/100-100000+math.cos(heading)*length/100,
                           'west':w/100-100000+math.sin(heading)*length/100},
               'source':'public_Canopic_Helper_observed_line_endpoint'}
    altitude = None
    if flags & 256:
        altitude = int.from_bytes(data[offset:offset+4], 'big') / 100 - 100000
        offset += 4
    tooltip = int.from_bytes(data[offset:offset+2], 'big') if flags & 1024 else None
    return {'sequence': sequence, 'client_uptime_ms': uptime, 'can_survey': bool(flags & 1),
            'mounted': bool(flags & 2), 'flying': bool(flags & 4), 'casting': bool(flags & 8),
            'loot_open': bool(flags & 16), 'falling': bool(flags & 64), 'arrow':arrow,
            'swimming': bool(flags & 512), 'altitude_yards':altitude,
            'height_above_ground_yards':None,
            'grounded': not bool(flags & (4 | 64 | 512)), 'tooltip_checksum':tooltip,
            'world': {'instance': instance, 'north': north/100-100000,
                'west': west/100-100000} if flags & 32 else None,
            'successful_surveys': surveys, 'last_survey_uptime_ms': at,
            'looted_finds': finds, 'site_id': site or None, 'canopic_jars_in_bags': jars,
            'recipe_items_in_bags': recipe, 'races': race_rows, 'visible_markers': marker_rows}


def decode_image(image, *, x, y, cell_size):
    rgb = image.convert('RGB')
    def read(size):
        bits = []
        for index in range(size * 8):
            px, py = int(x+(index % 96+.5)*cell_size), int(y+(index//96+.5)*cell_size)
            if not 0 <= px < image.width or not 0 <= py < image.height:
                raise ValueError('archaeology snapshot is outside the screenshot')
            color = rgb.getpixel((px, py))
            if max(color)-min(color) > 30 or 40 < color[0] < 215:
                raise ValueError('archaeology pixel is not black or white')
            bits.append(int(color[0] >= 215))
        return bytes(sum(bits[start+b] << (7-b) for b in range(8)) for start in range(0,len(bits),8))
    prefix = read(6)
    length = int.from_bytes(prefix[4:6], 'big')
    if prefix[:4] != b'TCA1' or not HEADER.size+2 <= length <= 512:
        raise ValueError('archaeology snapshot marker or length is invalid')
    return decode(read(length))
