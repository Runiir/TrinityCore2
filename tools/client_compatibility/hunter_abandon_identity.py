"""Pure saved-pet and exact request checks for disposable Abandon."""
import struct,time
from .world.buffer import Writer
from .world.gameobjects import modern_guid


def named_preserved(before,after):
    if len(before)!=2 or len(after)!=1 or after[0].get('id')!=4:return False
    old=next((r for r in before if r.get('id')==4),None);new=after[0]
    if not old or set(old)!=set(new) or not 0<old['savetime']<=new['savetime']<=time.time():return False
    expected={**old,'savetime':new['savetime']}
    return expected==new and (new['owner'],new['entry'],new['name'],new['renamed'],new['slot'],new['active'])==(
        6,42717,'Harnesswolf',1,5,0)


def exact_requests(packets,guid):
    modern=[p for p in packets if p.get('name')=='CMSG_PET_ABANDON' and p.get('direction')=='from_client']
    native=[p for p in packets if p.get('name')=='CMSG_PET_ABANDON' and p.get('direction')=='to_native']
    return {'one_exact_modern_abandon':len(modern)==1 and
        modern[0].get('body')==Writer().guid(*modern_guid(guid,0)).finish().hex(),
        'one_exact_native_abandon':len(native)==1 and native[0].get('body')==struct.pack('<Q',guid).hex()}
