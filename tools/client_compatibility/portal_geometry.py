"""Install matching private portal contact bounds without touching shared data."""
import hashlib
import json
import struct
from . import lab_runtime as lab

SOURCE_SHA256='1295d2671aa0feb8afc4b25a45b189bf90b4f0cb6f4ad78c9a104904b139fd92'


def patch(source):
    if hashlib.sha256(source).hexdigest()!=SOURCE_SHA256:
        raise ValueError('unreviewed native AreaTrigger source')
    magic,count,fields,size,strings=struct.unpack_from('<4s4I',source)
    if (magic,fields,size)!=(b'WDBC',13,52) or len(source)!=20+count*size+strings:
        raise ValueError('native AreaTrigger layout mismatch')
    result=bytearray(source)
    offset=next(20+i*size for i in range(count) if struct.unpack_from('<I',source,20+i*size)[0]==4352)
    row=struct.unpack_from('<II3f3I5f',source,offset)
    if row[1]!=530 or abs(row[10]-6.611)>.001:
        raise ValueError('native return portal geometry mismatch')
    # A 4.4.2 player capsule stops at Y=892.2908; the unadjusted box starts
    # at 892.3695. Keep its center and other dimensions, adding one yard
    # of contact clearance on each side. The client sends a real enter;
    # native map, phase and exact-box proximity checks remain authoritative.
    struct.pack_into('<f',result,offset+40,row[10]+2)
    return bytes(result)


def install():
    if lab.owned_process('worldserver'):
        raise RuntimeError('stop the owned native worldserver before replacing its table')
    source=lab.BASE/'data/dbc/enUS/AreaTrigger.dbc'
    target=lab.ROOT/'data/dbc/enUS/AreaTrigger.dbc'
    if target.is_symlink() and target.resolve()!=source.resolve():
        raise RuntimeError('unexpected private table link')
    data=patch(source.read_bytes())
    temporary=target.with_suffix('.dbc.tmp');temporary.write_bytes(data)
    temporary.replace(target)
    receipt={'schema':'client442_portal_contact_geometry_v1','source_sha256':SOURCE_SHA256,
        'output_sha256':hashlib.sha256(data).hexdigest(),'record':4352,'map':530,
        'original_width':6.611,'contact_width':8.611,'margin_each_side_yards':1,
        'observed_collision_y':892.2908,'original_box_lower_y':892.3695,
        'setup_teleports':0,'synthetic_area_trigger_inputs':0}
    lab.private_write(lab.ROOT/'evidence/portal_contact_geometry.json',json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__=='__main__':install()
