"""Native playable pairs and native expansion requirements for auth discovery."""
import struct
from .. import lab_runtime as lab


def expansions(name,fields,index):
    body=(lab.ROOT/'data/dbc/enUS'/(name+'.dbc')).read_bytes()
    magic,count,width,size,strings=struct.unpack_from('<4s4I',body)
    if magic!=b'WDBC' or (width,size)!=(fields,fields*4) or len(body)!=20+count*size+strings:
        raise ValueError('unexpected native '+name+' layout')
    return {row[0]:row[index] for row in
        (struct.unpack_from('<'+str(fields)+'I',body,20+i*size) for i in range(count))}


def native_rows():
    races=expansions('ChrRaces',24,20);classes=expansions('ChrClasses',14,10)
    with lab.connection() as con,con.cursor() as q:
        q.execute('SELECT race,class FROM client442_world.playercreateinfo ORDER BY race,class')
        return [{'race':r,'class':c,'expansion':max(races[r],classes[c])} for r,c in q.fetchall()]
