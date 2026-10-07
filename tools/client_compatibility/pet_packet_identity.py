"""Read pet cast identities and public GUIDs without importing UI controllers."""
from .world.buffer import Reader
from .world.native_objects import guid as native_guid


def cast_identity(packet):
    r=Reader(bytes.fromhex(packet['body']));direction=packet['direction'];name=packet['name']
    if name=='CMSG_CAST_SPELL' and direction=='from_client':
        identity=r.guid();misc0,misc1,spell,visual=r.unpack('iiiI')
        return {'spell':spell,'guid':identity,'misc0':misc0,'misc1':misc1,'visual':visual}
    if name=='CMSG_CAST_SPELL' and direction=='to_native':
        counter,spell,misc,flags,target_flags=r.unpack('BiiBI')
        return {'counter':counter,'spell':spell,'misc':misc,'flags':flags,'target_flags':target_flags}
    if name=='SMSG_SPELL_GO' and direction=='from_native':
        caster=native_guid(r);unit=native_guid(r);counter,spell=r.unpack('Bi')
        return {'caster':caster,'unit':unit,'counter':counter,'spell':spell}
    if name=='SMSG_CAST_FAILED' and direction=='from_native':
        counter,spell,reason=r.unpack('BiB');return {'counter':counter,'spell':spell,'reason':reason}
    return None


def expected_guid(pet):
    guid=pet['guid'];return f"Pet-0-1-{pet['map']}-0-{guid>>32&0xfffff}-{guid&0xffffffff:010X}"
