"""Read the owned session's visible survey instruments from decoded TCP packets.

Only ordinary game-object create/remove messages are used. The server's private
archaeology target and site coordinates are never read.
"""
import json
import math

from .. import lab_runtime as lab
from ..world.native_objects import records
from .journal import Cursor, entries, player_entry

TOOLS = {206590: "red", 206589: "yellow", 204272: "green"}
FINDS = {203071, 203078, 204282, 206836, 202655, 207187, 207188, 207189, 207190}


def angle_error(heading, facing):
    return (heading - facing + math.pi) % math.tau - math.pi


class Observer:
    def __init__(self,*,guid=None,session=None,root=None):
        root=root or lab.ROOT
        entry = player_entry(root,guid,session)
        self.guid=entry['guid']
        self.session, self.started = entry["session"], entry["time"]
        self.offset, self.tool, self.finds, self.player = 0, None, {}, None
        self.cursor = Cursor(root / "evidence/world_packets.jsonl")

    def poll(self, facing):
        for packet in self.cursor.poll():
            if packet.get("session") != self.session or packet["time"] < self.started:
                continue
            if packet['direction']=='from_client':
                from ..world import movement
                if packet['name'] in movement.SUPPORTED or packet['name']=='CMSG_MOVE_SET_FACING_HEARTBEAT':
                    state=movement.parse(bytes.fromhex(packet['body']),self.guid)
                    self.player={'position':list(state['position']),'seen_at':packet['time'],
                                 'source':'owned_session_client_movement_packets'}
            if packet["direction"] != "from_native":
                continue
            if packet["name"] == "SMSG_DESTROY_OBJECT":
                from ..world.buffer import Reader
                r = Reader(bytes.fromhex(packet["body"]))
                guid, _ = r.unpack("QB"); r.end()
                self.finds.pop(guid, None)
                if self.tool and self.tool["guid"] == guid: self.tool["visible"] = False
                continue
            if packet["name"] != "SMSG_UPDATE_OBJECT": continue
            for record in records(bytes.fromhex(packet["body"])):
                if record.get('guid')==self.guid and 'movement' in record:
                    self.player={'position':list(record['movement']['position']),'seen_at':packet['time'],
                                 'source':'owned_session_native_visible_player_create'}
                if record["update_type"] == 3:
                    for guid in record["removed"]:
                        self.finds.pop(guid, None)
                        if self.tool and self.tool["guid"] == guid: self.tool["visible"] = False
                elif record.get("kind") == 5:
                    from ..world.objects import INDEX
                    creator = record["fields"].get(INDEX["OBJECT_FIELD_CREATED_BY"], 0) | record["fields"].get(INDEX["OBJECT_FIELD_CREATED_BY"] + 1, 0) << 32
                    if creator != self.guid: continue
                    entry = record["guid"] >> 32 & 0xFFFFF
                    if entry not in TOOLS and entry not in FINDS: continue
                    x, y, z, heading = record["movement"]["position"]
                    observed = {"guid": record["guid"], "entry": entry, "map":record['map'], "seen_at": packet["time"],
                                "position": [x, y, z], "heading_radians": heading, "visible": True}
                    if entry in TOOLS:
                        self.tool = {**observed, "color": TOOLS[entry]}
                    else: self.finds[record["guid"]] = observed
        # Rendering can lag behind physical input. Prefer the latest normal
        # owned movement packet so a stale screenshot cannot reverse a turn.
        if self.player:facing=self.player['position'][3]
        tool = dict(self.tool) if self.tool else None
        if tool: tool["turn_error_radians"] = angle_error(tool["heading_radians"], facing)
        return {"source": "owned_session_visible_object_tcp_packets", "session": self.session,
                "tool": tool, "finds": list(self.finds.values()), 'player':self.player,
                'facing_source':self.player['source'] if self.player else 'addon_screenshot'}


def collected(session, since):
    """Confirm a physical loot click using native loot and currency replies."""
    from ..world.currency import translate
    from ..world.buffer import Reader
    replies = list(entries(lab.ROOT / "evidence/world_packets.jsonl"))
    replies = [r for r in replies if r.get("session") == session and r["time"] >= since and r["direction"] == "from_native"]
    openings=[i for i,r in enumerate(replies) if r['name']=='SMSG_LOOT_RESPONSE']
    if not openings:return None
    replies=replies[openings[0]:openings[1] if len(openings)>1 else len(replies)]
    removed={bytes.fromhex(r['body'])[0] for r in replies if r['name']=='SMSG_CURRENCY_LOOT_REMOVED'}
    if not removed:return None
    awarded={}
    for reply in replies:
        if reply['name']!='SMSG_LOOT_RESPONSE':continue
        r=Reader(bytes.fromhex(reply['body']));_,reason=r.unpack('QB')
        if not reason:continue
        _,items,currencies=r.unpack('IBB')
        for _ in range(items):r.unpack('BIIiiiB')
        for _ in range(currencies):
            slot,kind,quantity=r.unpack('BII')
            if slot in removed:awarded[kind]=quantity
        r.end()
    for reply in replies:
        if reply["name"] != "SMSG_SET_CURRENCY": continue
        r = Reader(translate(reply["name"], bytes.fromhex(reply["body"])))
        currency, quantity = r.unpack("ii")
        if currency in awarded and awarded[currency]>0:
            return {"time": reply["time"], "session": session, "currency": currency,
                    "quantity": awarded[currency], "balance":quantity,
                    "source": "native_loot_amount_removed_and_currency_reply"}
    return None
