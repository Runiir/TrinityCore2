"""Read public terrain heights, including faces omitted from navigation tiles.

The triangle interpolation follows GridMap.cpp's native MAPS v10 layout.
Shared map files are read only; no player or archaeology database is used.
"""
from functools import lru_cache
import struct
from . import lab_runtime as lab

GRID=533.33333333


@lru_cache(maxsize=32)
def tile(map_id,gx,gy):
    path=lab.BASE/'data/maps'/f'{map_id:03d}{gx:02d}{gy:02d}.map'
    data=path.read_bytes();header=struct.unpack_from('<4s10I',data)
    if header[:2]!=(b'MAPS',10):raise RuntimeError('unsupported public terrain tile')
    offset=header[5];magic,flags,base,maximum=struct.unpack_from('<4sIff',data,offset)
    if magic!=b'MHGT':raise RuntimeError('invalid public terrain height section')
    if flags&1:return data,header,flags,base,1,None,None
    code,scale=('H',(maximum-base)/65535) if flags&2 else ('B',(maximum-base)/255) if flags&4 else ('f',1)
    offset+=16;v9=struct.unpack_from('<'+code*(129*129),data,offset)
    v8=struct.unpack_from('<'+code*(128*128),data,offset+struct.calcsize(code)*129*129)
    return data,header,flags,base,scale,v9,v8


def height(map_id,position):
    x=128*(32-position[0]/GRID);y=128*(32-position[1]/GRID)
    ix,iy=int(x),int(y);gx,gy=ix//128,iy//128
    if not 0<=gx<64 or not 0<=gy<64:raise ValueError('position outside public map grid')
    data,header,flags,base,scale,v9,v8=tile(map_id,gx,gy)
    if flags&1:return base
    x-=ix;y-=iy;ix&=127;iy&=127
    if header[10]:
        holes=struct.unpack_from('<H',data,header[9]+2*((ix//8)*16+iy//8))[0]
        if holes&[0x1111,0x2222,0x4444,0x8888][iy%8//2]&[0x000f,0x00f0,0x0f00,0xf000][ix%8//2]:return None
    h1=v9[ix*129+iy];h2=v9[(ix+1)*129+iy]
    h3=v9[ix*129+iy+1];h4=v9[(ix+1)*129+iy+1];h5=2*v8[ix*128+iy]
    if x+y<1:
        a,b,c=(h2-h1,h5-h1-h2,h1) if x>y else (h5-h1-h3,h3-h1,h1)
    else:a,b,c=(h2+h4-h5,h4-h2,h5-h4) if x>y else (h4-h3,h3+h4-h5,h5-h4)
    value=a*x+b*y+c
    return value*scale+base if flags&6 else value
