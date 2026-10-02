"""Read visible gossip captions and their actual UI centers."""
import struct
from .menu_pixels import read_menu


def decode_image(image):
    image,data,seq,count=read_menu(image,b'TCG',16,15,187.5,64,1.875)
    rows=[]
    for i in range(count):
        id,name,x,y=struct.unpack_from('>4H',data,9+i*8)
        rows.append({'id':id,'caption_checksum':name,'pixel':[round(x/65535*image.width),round((1-y/65535)*image.height)]})
    return {'sequence':seq,'options':rows,'source':'addon_visible_gossip_font_regions'}
