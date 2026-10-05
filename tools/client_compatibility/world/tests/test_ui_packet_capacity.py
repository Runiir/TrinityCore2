import json,math,struct
from PIL import Image
import pytest
from tools.client_compatibility.observation.interactions import decode_packet,decode_image,CAPACITY
from tools.client_compatibility.observation.telemetry import checksum
from tools.client_compatibility.interaction_operations import retain_control_pixels


def packet(size):
    body=json.dumps({'mode':'controls','guid':'owned','text':'x'*size},separators=(',',':')).encode()
    raw=struct.pack('>4sHI',b'TCU2',len(body),7)+body
    return raw+checksum(raw).to_bytes(2,'big')


def test_expanded_packet_and_actual_rows_survive_lossless_control_retention(tmp_path):
    raw=packet(7000);state=decode_packet(raw);assert len(raw)>6144
    im=Image.new('RGB',(1280,720))
    for index in range(math.ceil(len(raw)/3)):
        color=tuple(raw[index*3:index*3+3].ljust(3,b'\0'))
        im.putpixel((int(281.25+(index%128+.5)*2.8125),int(15+(index//128+.5)*2.8125)),color)
    source=tmp_path/'full.png';target=tmp_path/'control.png';im.save(source)
    frame=retain_control_pixels(source,target,state)
    with Image.open(target) as crop:
        assert crop.height>48 and decode_image(crop,x=.25,y=0)==state
    assert frame['capture_box'][3]>63 and not source.exists()


def test_packet_still_rejects_capacity_overrun_and_checksum_corruption():
    with pytest.raises(ValueError,match='length'):decode_packet(packet(CAPACITY))
    raw=bytearray(packet(7000));raw[-1]^=1
    with pytest.raises(ValueError,match='checksum'):decode_packet(raw)
