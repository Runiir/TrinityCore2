"""Read actual Blizzard taxi button centers from observation-only pixels."""
import struct
from .menu_pixels import read_menu

SIZE=1035


def decode_image(image):
    image,data,seq,count=read_menu(image,b'TCT',128,15,60,128,1.875)
    nodes=[]
    for i in range(128 if data[:4]==b'TCT1' else count):
        node,x,y,state,slot=struct.unpack_from('>3H2B',data,9+i*8)
        if i>=count:
            if any([node,x,y,state,slot]):raise ValueError('nonempty unused taxi node')
        else:
            if not node or not slot:raise ValueError('invalid taxi node')
            nodes.append({'id':node,'state':state,'slot':slot,
                'pixel':[round(x/65535*image.width),round((1-y/65535)*image.height)]})
    return {'sequence':seq,'nodes':nodes,'source':'addon_visible_blizzard_taxi_buttons'}
