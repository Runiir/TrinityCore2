"""Translate character discovery using only the linked native account's rows."""
import time
import struct
from functools import lru_cache

from tools.client_compatibility.lab_runtime import connection
from tools.client_compatibility.auth.realms import ADDRESS
from .buffer import Writer, player_high


def rows(account_id):
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT guid,name,race,class,gender,level,map,zone,position_x,position_y,position_z,orientation,characterFlags,at_login,slot,logout_time FROM client442_characters.characters WHERE account=%s ORDER BY slot,guid", (account_id,))
        keys = [field[0] for field in cursor.description]
        return [dict(zip(keys, row)) for row in cursor.fetchall()]


def enumeration(account_id):
    characters = rows(account_id)
    equipment=visual_equipment(account_id)
    w = Writer()
    for value in [1, 0, 0, 1, 0, 0, 0, 1, 0]:
        w.bits(value, 1)
    w.pack("IIiIIIII", len(characters), 0, 85, 1, 0, 0, 0, 0)
    for c in characters:
        w.guid(c["guid"], player_high()).pack("IBBBBhI", ADDRESS, c["slot"], c["race"], c["gender"], c["class"], 0, 0)
        w.pack("Bii3fQ", c["level"], c["map"], c["zone"], c["position_x"], c["position_y"], c["position_z"], 0).guid()
        w.pack("IIIBIII", c.get('characterFlags',0)&0xc00, 0, 0, 0, 0, 0, 0)
        for item in equipment.get(c['guid'],[None]*19):
            w.pack('IBIBiII',*(item or (0,0,0,0,0,0,0)))
        w.pack("iQi5iIIiI", 0, int(c["logout_time"]), 60895, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        w.bits(len(c["name"].encode()), 6).bits(0, 1).raw(c["name"].encode())
        w.bits(0, 3).pack("III", 0, 0, 0)
    w.pack("i", 1).bits(1, 1).bits(1, 1).bits(0, 3)
    return w.finish()


def visual_equipment(account_id):
    """Use equipped inventory rows for only this authenticated account.

    The native item display is also used by the Classic character-list visual
    record. Ring/trinket slots retain their IDs without inventing a display.
    """
    result={}
    templates=item_displays()
    with connection() as conn,conn.cursor() as cursor:
        cursor.execute('''SELECT c.guid,ci.slot,ii.itemEntry
            FROM client442_characters.characters c
            JOIN client442_characters.character_inventory ci ON ci.guid=c.guid AND ci.bag=0 AND ci.slot<19
            JOIN client442_characters.item_instance ii ON ii.guid=ci.item AND ii.owner_guid=c.guid
            WHERE c.account=%s''',(account_id,))
        inventory=cursor.fetchall()
        cursor.execute('SELECT ID,DisplayInfoID,InventoryType,SubclassID FROM client442_hotfixes.item')
        templates={**templates,**{item:(display,kind,subclass) for item,display,kind,subclass in cursor.fetchall()}}
        for guid,slot,item in inventory:
            display,kind,subclass=templates.get(item,(0,0,0))
            result.setdefault(guid,[None]*19)[slot]=(display,kind,0,subclass,0,item,0)
    return result


@lru_cache(maxsize=1)
def item_displays():
    from ..lab_runtime import BASE
    data=(BASE/'data/dbc/enUS/Item.db2').read_bytes()
    magic,count,fields,width,strings,table_hash,build,stamp,minimum,maximum,locale,copy_size=struct.unpack_from('<4s11I',data)
    if magic!=b'WDB2' or fields!=8 or width!=32 or build!=15595:raise ValueError('unexpected native item display table')
    offset=48+(maximum-minimum+1)*6 if maximum else 48
    if offset+count*width+strings>len(data):raise ValueError('truncated item display table')
    rows=[struct.unpack_from('<8I',data,offset+i*width) for i in range(count)]
    return {row[0]:(row[5],row[6],row[2]) for row in rows}


def auth_success():
    w = Writer().pack("I", 0).bits(1, 1).bits(0, 1)
    w.pack("IIIBBIIIIq", ADDRESS, 1, 0, 3, 3, 0, 1, 0, 0, int(time.time()))
    w.pack("BI", 1, 1).pack("BBBB", 1, 0, 0, 0)
    w.bits(0, 6).pack("III", 0, 0, 0).bits(0, 3)
    name = b"Client442 Lab"
    normalized = b"Client442Lab"
    w.pack("I", ADDRESS).bits(1, 1).bits(0, 1).bits(len(name), 8).bits(len(normalized), 8).raw(name + normalized)
    return w.finish()
