"""Read actual Blizzard taxi button centers from observation-only pixels."""
import struct
from .telemetry import checksum

SIZE=1035


def decode_image(image):
    image=image.convert('RGB');bits=[]
    for index in range(SIZE*8):
        x=int(15+(index%128+.5)*1.875);y=int(60+(index//128+.5)*1.875)
        r,g,b=image.getpixel((x,y))
        if max(r,g,b)-min(r,g,b)>30 or 40<r<215:raise ValueError('invalid taxi observation pixel')
        bits.append(int(r>=215))
    data=bytes(sum(bits[start+b]<<(7-b) for b in range(8)) for start in range(0,len(bits),8))
    magic,seq,count=struct.unpack_from('>4sIB',data)
    if magic!=b'TCT1' or count>128 or checksum(data[:-2])!=struct.unpack_from('>H',data,SIZE-2)[0]:
        raise ValueError('invalid taxi observation packet')
    nodes=[]
    for i in range(128):
        node,x,y,state,slot=struct.unpack_from('>3H2B',data,9+i*8)
        if i>=count:
            if any([node,x,y,state,slot]):raise ValueError('nonempty unused taxi node')
        else:
            if not node or not slot:raise ValueError('invalid taxi node')
            nodes.append({'id':node,'state':state,'slot':slot,
                'pixel':[round(x/65535*image.width),round((1-y/65535)*image.height)]})
    return {'sequence':seq,'nodes':nodes,'source':'addon_visible_blizzard_taxi_buttons'}
