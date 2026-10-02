"""Read normal public UI state from the owned game's screenshot pixels."""
import json
import struct
from .telemetry import checksum

CAPACITY=4096


def decode_packet(data):
    if len(data)<12 or data[:4]!=b'TCU2':raise ValueError('UI observation marker is missing')
    length,sequence=struct.unpack_from('>HI',data,4)
    if length>CAPACITY or len(data)!=length+12:raise ValueError('invalid UI observation length')
    if checksum(data[:-2])!=int.from_bytes(data[-2:],'big'):raise ValueError('UI observation checksum mismatch')
    value=json.loads(data[10:-2]);value.update(sequence=sequence,source='normal_addon_visible_ui_pixels')
    if value.get('observer_error'):raise ValueError(value['observer_error'])
    return value


def decode_image(image,x=281.25,y=15,cell=2.8125):
    rgb=image.convert('RGB');data=bytearray()
    def read(count):
        for index in range(len(data)//3,(count+2)//3):
            pixel=rgb.getpixel((int(x+(index%128+.5)*cell),int(y+(index//128+.5)*cell)))
            data.extend(pixel)
        return bytes(data[:count])
    header=read(10)
    if header[:4]!=b'TCU2':raise ValueError('UI observation marker is missing')
    length=int.from_bytes(header[4:6],'big')
    if length>CAPACITY:raise ValueError('UI observation length exceeds its bound')
    return decode_packet(read(length+12))
