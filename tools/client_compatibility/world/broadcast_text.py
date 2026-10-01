"""Public native greetings in the 4.4.2 BroadcastText hotfix wire layout.

Layout: pinned WPP 28fc3d, HotfixHandler.BroadcastTextHandler441.
Legacy SoundEntries IDs are not modern SoundKit IDs; omit their audio.
"""
from functools import lru_cache
from .buffer import Writer

TABLE_HASH = 0x021826BB


@lru_cache(maxsize=512)
def record(entry):
    from .. import lab_runtime as lab
    with lab.connection() as db, db.cursor() as cur:
        cur.execute('SELECT Text,Text1,ID,LanguageID,EmotesID,Flags,'
                    'EmoteID1,EmoteID2,EmoteID3,EmoteDelay1,EmoteDelay2,EmoteDelay3 '
                    'FROM client442_world.broadcast_text WHERE ID=%s', (entry,))
        row = cur.fetchone()
    if not row:return None
    male,female,ident,language,emotes,flags,*gestures = row
    strings = [value.encode('utf-8') for value in (male,female)]
    if any(len(value)>16384 or b'\0' in value for value in strings):
        raise ValueError('invalid public broadcast string')
    return (Writer().raw(strings[0]+b'\0').raw(strings[1]+b'\0')
            .pack('IiiHHIi2I6H',ident,language,0,emotes,flags,0,0,0,0,*gestures).finish())
