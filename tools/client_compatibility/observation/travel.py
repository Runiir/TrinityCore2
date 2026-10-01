"""Decode public addon map/travel observations from the game screenshot."""
import struct
from .telemetry import checksum

PACKET = struct.Struct('>4sIIIiiiBB16HHBH3BH')
FLAGS = {'mounted':1, 'flying':2, 'falling':4, 'swimming':8, 'casting':16,
         'indoors':32, 'flyable_area':64, 'world_position_available':128}


def decode_packet(data):
    magic, sequence, uptime, world, x, y, z, flags, count, *rest = PACKET.unpack(data)
    if magic != b'TCA2' or checksum(data[:-2]) != rest[-1] or count > 16:
        raise ValueError('invalid travel telemetry frame')
    sites = rest[:16]
    if any(sites[count:]) or any(not n for n in sites[:count]):
        raise ValueError('invalid digsite list')
    status = {name: bool(flags & bit) for name,bit in FLAGS.items()}
    cursor=rest[19]<<16|rest[20]<<8|rest[21]
    return {'schema':'client442_addon_travel_v1','sequence':sequence,'client_uptime_ms':uptime,
        'world_map':world if status['world_position_available'] else None,
        'world_position':[x/100,y/100,z/100] if status['world_position_available'] else None,
        'digsite_ids':sites[:count], 'tooltip_name_checksum':rest[16], 'loot_slots':rest[17],
        'camera_zoom':rest[18]/100, 'cursor_position':[cursor>>12,cursor&4095],
        **status, 'source':'addon_rendered_pixels'}


def decode_image(image, x=1025, y=15, cell_size=3.75):
    rgb=image.convert('RGB')
    bits=[]
    for index in range(PACKET.size*8):
        px=int(x+(index%64+.5)*cell_size);py=int(y+(index//64+.5)*cell_size)
        if px>=image.width or py>=image.height: raise ValueError('travel panel outside screenshot')
        r,g,b=rgb.getpixel((px,py))
        if max(r,g,b)-min(r,g,b)>30 or 40<r<215: raise ValueError('invalid travel panel pixel')
        bits.append(int(r>=215))
    data=bytes(sum(bits[start+bit]<<(7-bit) for bit in range(8)) for start in range(0,len(bits),8))
    return decode_packet(data)
