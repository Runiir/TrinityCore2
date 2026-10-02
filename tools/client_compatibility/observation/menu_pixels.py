"""Versioned one-bit menu packets; v2 omits unused node/option padding."""
import struct
from .telemetry import checksum


def read_menu(image,magic,maximum,x,y,columns,cell):
    image=image.convert('RGB')
    def read(size):
        bits=[]
        for index in range(size*8):
            r,g,b=image.getpixel((int(x+(index%columns+.5)*cell),int(y+(index//columns+.5)*cell)))
            if max(r,g,b)-min(r,g,b)>30 or 40<r<215:raise ValueError('invalid menu observation pixel')
            bits.append(int(r>=215))
        return bytes(sum(bits[i+b]<<(7-b) for b in range(8)) for i in range(0,len(bits),8))
    header=read(9);version,sequence,count=struct.unpack('>4sIB',header)
    if version not in [magic+b'1',magic+b'2'] or count>maximum:raise ValueError('invalid menu observation header')
    data=read(11+8*(maximum if version.endswith(b'1') else count))
    if checksum(data[:-2])!=int.from_bytes(data[-2:],'big'):raise ValueError('menu observation checksum mismatch')
    return image,data,sequence,count
