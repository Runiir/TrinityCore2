"""Read visible gossip captions and their actual UI centers."""
import struct
from .telemetry import checksum


def decode_image(image):
    image=image.convert('RGB');bits=[]
    for index in range(139*8):
        x=int(15+(index%64+.5)*1.875);y=int(187.5+(index//64+.5)*1.875)
        r,g,b=image.getpixel((x,y))
        if max(r,g,b)-min(r,g,b)>30 or 40<r<215:raise ValueError('invalid gossip pixel')
        bits.append(int(r>=215))
    data=bytes(sum(bits[start+b]<<(7-b) for b in range(8)) for start in range(0,len(bits),8))
    magic,seq,count=struct.unpack_from('>4sIB',data)
    if magic!=b'TCG1' or count>16 or checksum(data[:-2])!=struct.unpack_from('>H',data,137)[0]:raise ValueError('invalid gossip packet')
    rows=[]
    for i in range(count):
        id,name,x,y=struct.unpack_from('>4H',data,9+i*8)
        rows.append({'id':id,'caption_checksum':name,'pixel':[round(x/65535*image.width),round((1-y/65535)*image.height)]})
    return {'sequence':seq,'options':rows,'source':'addon_visible_gossip_font_regions'}
