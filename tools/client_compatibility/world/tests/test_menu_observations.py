"""Compact menu pixels must preserve old captures and reject damaged packets."""
import struct
from PIL import Image
import pytest
from tools.client_compatibility.observation import taxi,gossip
from tools.client_compatibility.observation.telemetry import checksum


def picture(kind,version,count,damage=False):
    maximum,columns,y=(128,128,60) if kind=='taxi' else (16,64,187.5)
    marker=b'TCT' if kind=='taxi' else b'TCG'
    rows=b''.join(struct.pack('>3H2B',i+1,20000,30000,2,i+1) if kind=='taxi'
        else struct.pack('>4H',i+1,1234,20000,30000) for i in range(count))
    data=marker+str(version).encode()+struct.pack('>IB',7,count)+rows
    if version==1:data+=bytes((maximum-count)*8)
    data+=struct.pack('>H',checksum(data))
    if damage:data=data[:-1]+bytes([data[-1]^1])
    image=Image.new('RGB',(1280,720),(50,100,150))
    for index in range(len(data)*8):
        value=255 if data[index//8]&(1<<(7-index%8)) else 0
        image.putpixel((int(15+(index%columns+.5)*1.875),int(y+(index//columns+.5)*1.875)),(value,)*3)
    return image


@pytest.mark.parametrize('kind',['taxi','gossip'])
@pytest.mark.parametrize('version',[1,2])
@pytest.mark.parametrize('count',[0,2])
def test_old_and_compact_menu_pixels(kind,version,count):
    decoder=taxi.decode_image if kind=='taxi' else gossip.decode_image
    decoded=decoder(picture(kind,version,count));rows=decoded['nodes' if kind=='taxi' else 'options']
    assert decoded['sequence']==7;assert [r['id'] for r in rows]==list(range(1,count+1))
    if rows:assert rows[0]['pixel']==[391,390]


@pytest.mark.parametrize('kind',['taxi','gossip'])
def test_compact_menu_pixels_reject_checksum_damage(kind):
    decoder=taxi.decode_image if kind=='taxi' else gossip.decode_image
    with pytest.raises(ValueError,match='checksum'):decoder(picture(kind,2,2,damage=True))
