"""Decode bounded public route and visible UI facts from RGB addon pixels."""
import json
import struct
import math
from tools.client_compatibility.observation.telemetry import checksum

CAPACITY=16384
COLUMNS=128


def decode(data):
    if len(data)<12 or data[:4]!=b'TCU3':raise ValueError('farm UI marker is absent')
    length,sequence=struct.unpack_from('>HI',data,4)
    if length>CAPACITY or len(data)!=length+12:raise ValueError('farm UI length exceeds its bound')
    if checksum(data[:-2])!=int.from_bytes(data[-2:],'big'):raise ValueError('farm UI checksum mismatch')
    row=json.loads(data[10:-2])
    if not isinstance(row,dict):raise ValueError('invalid farm UI')
    if row.get('observer_error'):raise ValueError(str(row['observer_error']))
    row.update(sequence=sequence,source='public_addon_route_and_visible_ui_pixels')
    return row


def decode_image(image,*,x,y,cell):
    rgb=image.convert('RGB');data=bytearray()
    def read(count):
        for index in range(len(data)//3,(count+2)//3):
            px,py=int(x+(index%COLUMNS+.5)*cell),int(y+(index//COLUMNS+.5)*cell)
            if not 0<=px<rgb.width or not 0<=py<rgb.height:raise ValueError('farm UI outside owned viewport')
            data.extend(rgb.getpixel((px,py)))
        return bytes(data[:count])
    header=read(10)
    if header[:4]!=b'TCU3':raise ValueError('farm UI marker is absent')
    length=int.from_bytes(header[4:6],'big')
    if length>CAPACITY:raise ValueError('farm UI exceeds packet capacity')
    return decode(read(length+12))


def locate(image,cell):
    rgb=image.convert('RGB')
    for y in range(8,50):
        for x in range(290,440):
            if rgb.getpixel((x,y))!=(84,67,85):continue
            try:
                row=decode_image(rgb,x=x-cell/2,y=y-cell/2,cell=cell)
                return row,{'x':x-cell/2,'y':y-cell/2,'cell':cell}
            except (ValueError,UnicodeError):pass
    return None,None


def recalibrate(image,position):
    """Require a complete valid checksum for any nearby pixel geometry change."""
    size=position['cell']
    sizes=list(dict.fromkeys([size,round(size*64)/64,math.ceil(size*64)/64,math.floor(size*64)/64]))
    for cell in sizes:
        for dx in [0,-.25,.25,-.5,.5,-.75,.75]:
            for dy in [0,-.25,.25,-.5,.5,-.75,.75]:
                candidate={'x':position['x']+dx,'y':position['y']+dy,'cell':cell}
                try:return decode_image(image,**candidate),candidate
                except ValueError:pass
    raise ValueError('farm UI has no checksum-valid pixel geometry')
