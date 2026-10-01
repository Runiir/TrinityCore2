"""Configure only Harnessone through an isolated native administrator session.

The temporary account permission is restored even if setup fails. No administrator
commands are exposed to the decision model or used to complete its archaeology trial.
"""
import asyncio
import argparse
import json
import time

from . import lab_runtime as lab
from .world import instance
from .world.buffer import Writer
from .world.legacy import Native
from .world.native_objects import find_self

CONFIG = lab.REPO / "experiments/configs/client_harness/85_archaeology_character_v1.json"


def verify(config):
    with lab.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT name,account,level,health,map,position_x,position_y,position_z FROM client442_characters.characters WHERE guid=%s", (config["guid"],))
        row = cur.fetchone()
        if not row or row[:3] != (config["character"], config["account_id"], config["level"]):
            raise RuntimeError("native character identity/level verification failed")
        cur.execute("SELECT skill,value,max FROM client442_characters.character_skills WHERE guid=%s", (config["guid"],))
        skills = {skill: (value, maximum) for skill, value, maximum in cur.fetchall()}
        for rank in config["profession_ranks"]:
            if skills.get(rank["skill"]) != (525, 525): raise RuntimeError("profession rank verification failed")
        cur.execute("SELECT ci.slot,ii.itemEntry FROM client442_characters.character_inventory ci JOIN client442_characters.item_instance ii ON ii.guid=ci.item WHERE ci.guid=%s AND ci.bag=0 AND ci.slot<19", (config["guid"],))
        equipped = dict(cur.fetchall())
        gear = json.loads((lab.REPO / config["gear_source"]).read_text())["items"]
        expected = {slot: item["id"] for slot, item in zip(config["gear_native_slots"], gear) if item.get("id")}
        if any(equipped.get(slot) != entry for slot, entry in expected.items()): raise RuntimeError("equipped gear verification failed")
        cur.execute("SELECT spell FROM client442_characters.character_spell WHERE guid=%s AND active=1 AND disabled=0", (config["guid"],))
        learned = {spell for spell, in cur.fetchall()}
        if not set(config["flight_spells"]) <= learned:
            raise RuntimeError("flight license verification failed")
        if skills.get(config["riding_skill"]) != (config["riding_value"], config["riding_value"]):
            raise RuntimeError("riding rank verification failed")
        if config["survey_spell"] not in learned:
            # Automatically learned child abilities are not necessarily separate
            # persistent character_spell rows. Verify the native login spell list.
            from .world.buffer import Reader
            known = set()
            for line in (lab.ROOT / "evidence/world_packets.jsonl").open():
                event = json.loads(line)
                if event["direction"] == "from_native" and event["name"] == "SMSG_SEND_KNOWN_SPELLS":
                    reader = Reader(bytes.fromhex(event["body"]))
                    initial, count = reader.unpack("BH")
                    known = {reader.unpack("Ih")[0] for _ in range(count)}
            if config["survey_spell"] not in known or 89722 not in learned:
                raise RuntimeError("native Survey is not learned")
        if learned.intersection(config["remove_conflicting_specializations"]): raise RuntimeError("conflicting Alchemy specializations remain")
        cur.execute("SELECT SecurityLevel FROM client442_auth.account_access WHERE AccountID=%s", (config["account_id"],))
        if cur.fetchall(): raise RuntimeError("temporary administrator permission remains")
    receipt = {"schema": "client442_archaeology_setup_v1", "config_sha256": lab.sha256(CONFIG),
        "identity": {"guid": config["guid"], "name": row[0], "account_id": row[1]}, "level": row[2],
        "health": row[3], "position": {"map": row[4], "xyz": list(row[5:])}, "equipped": expected,
        "professions": [{**rank, "value": 525, "max": 525} for rank in config["profession_ranks"]],
        "survey_learned": True, "normal_account_permissions": True, "learned_spell_count": len(learned),
        "gear_enchants_gems_applied": False, "flight_spells": config["flight_spells"],
        "riding_rank": config["riding_value"]}
    lab.private_write(lab.ROOT / "evidence/archaeology_character_setup.json", json.dumps(receipt, indent=2)+"\n")
    return receipt


async def setup(config, flight_only=False):
    n = Native("archaeology_setup")
    events = []
    logged_out = asyncio.Event()
    entered = asyncio.Event()
    enumerated = asyncio.Event()
    async def receive():
        while True:
            name, body = await n.receive()
            if name == "SMSG_ENUM_CHARACTERS_RESULT": enumerated.set()
            if name == "SMSG_UPDATE_OBJECT" and not entered.is_set():
                try:
                    if find_self(body, config["guid"]): entered.set()
                except ValueError: pass
            if name == "SMSG_TIME_SYNC_REQ": n.send("CMSG_TIME_SYNC_RESP", body + bytes(4))
            if name == "SMSG_MESSAGECHAT": events.append(body.hex())
            if name == "SMSG_LOGOUT_COMPLETE": logged_out.set()
    await n.connect(config["account_id"], "CLIENTLAB")
    pump = asyncio.create_task(receive())
    try:
        n.send("CMSG_ENUM_CHARACTERS")
        await asyncio.wait_for(enumerated.wait(), 10)
        n.send("CMSG_PLAYER_LOGIN", instance.native_login(config["guid"]))
        await asyncio.wait_for(entered.wait(), 15)
        n.send("CMSG_SET_ACTIVE_MOVER", instance.native_active_mover(config["guid"]))
        async def command(text, delay=.2):
            encoded = text.encode()
            n.send("CMSG_MESSAGECHAT_SAY", Writer().pack("I", 7).bits(len(encoded), 9).raw(encoded).finish())
            await asyncio.sleep(delay)
        if flight_only:
            for spell in config["flight_spells"]: await command(f".learn {spell}")
            await command(f".setskill {config['riding_skill']} {config['riding_value']} {config['riding_value']}")
            await command(".save", 1)
            n.send("CMSG_LOGOUT_REQUEST")
            await asyncio.wait_for(logged_out.wait(), 30)
            return
        await command(".gm off")
        await command(".gm visible on")
        await command(".character level Harnessone 85", .5)
        await command(".learn all my spells", .8)
        await command(".learn all default Harnessone")
        for spell in [750, 8737, 2457, 87500]:
            await command(f".learn {spell}")
        for rank in config["profession_ranks"]:
            await command(f".learn {rank['spell']}")
            await command(f".setskill {rank['skill']} 525 525")
        await command(f".learn {config['survey_spell']}")
        await command(f".learn {config['riding_spell']}")
        await command(f".setskill {config['riding_skill']} {config['riding_value']} {config['riding_value']}")
        for spell in config["flight_spells"]: await command(f".learn {spell}")
        await command(f".learn {config['mount_spell']}")
        with lab.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM client442_characters.character_spell WHERE guid=1")
            recipes_needed = cur.fetchone()[0] < 3000
        if recipes_needed: await command(".learn all crafts Harnessone", 3)
        for spell in config["remove_conflicting_specializations"]:
            await command(f".unlearn {spell}")
        for skill in [43, 44, 45, 46, 54, 55, 95, 136, 160, 162, 172, 173, 176, 226, 229, 473, 777, 803, 810]:
            await command(f".setskill {skill} 425 425")
        gear = json.loads((lab.REPO / config["gear_source"]).read_text())["items"]
        for item, target in zip(gear, config["gear_native_slots"]):
            if not item.get("id"): continue
            with lab.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM client442_characters.item_instance WHERE owner_guid=1 AND itemEntry=%s LIMIT 1", (item["id"],))
                exists = cur.fetchone()
            if not exists:
                await command(f".additem {item['id']}")
            await command(".save", 1)
            with lab.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT ci.slot FROM client442_characters.character_inventory ci JOIN client442_characters.item_instance ii ON ii.guid=ci.item WHERE ci.guid=1 AND ci.bag=0 AND ii.itemEntry=%s ORDER BY ci.slot", (item["id"],))
                slots = [row[0] for row in cur.fetchall()]
            if target not in slots:
                for _ in range(25):
                    if slots: break
                    await asyncio.sleep(.2)
                    with lab.connection() as conn, conn.cursor() as cur:
                        cur.execute("SELECT ci.slot FROM client442_characters.character_inventory ci JOIN client442_characters.item_instance ii ON ii.guid=ci.item WHERE ci.guid=1 AND ci.bag=0 AND ii.itemEntry=%s ORDER BY ci.slot", (item["id"],))
                        slots = [row[0] for row in cur.fetchall()]
                if not slots: raise RuntimeError(f"gear item {item['id']} was not created")
                await command(f".itemmove {slots[-1]} {target}")
        for button, spell in [(0, 6603), (1, config["survey_spell"]), (2, config["mount_spell"]),
                              (72, 6603), (73, config["survey_spell"]), (74, config["mount_spell"])]:
            n.send("CMSG_SET_ACTION_BUTTON", Writer().pack("BI", button, spell).finish())
        spawn = config["trial_spawn"]
        with lab.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM client442_characters.character_archaeology_sites WHERE guid=1 AND type=%s", (spawn["site"],))
            if not cur.fetchone(): raise RuntimeError("trial spawn is not an assigned digsite")
        await command(f".go xyz {spawn['x']} {spawn['y']}", 2)
        await command(".save", 1)
        await command(".gm off")
        n.send("CMSG_LOGOUT_REQUEST")
        await asyncio.wait_for(logged_out.wait(), 30)
    finally:
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
        await n.close()
        lab.private_write(lab.ROOT / "evidence/archaeology_setup_messages.json", json.dumps(events))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flight-only", action="store_true", help="Add the flight license/riding rank without repeating equipment or changing position")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    if (config["account_id"], config["guid"], config["character"]) != (1, 1, "Harnessone"):
        raise RuntimeError("setup identity does not match the owned lab character")
    if lab.owned_process("modern_world") or lab.owned_process("client"):
        raise RuntimeError("stop the owned frontend/client before native setup")
    with lab.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT name,account FROM client442_characters.characters WHERE guid=1")
        if cur.fetchone() != ("Harnessone", 1): raise RuntimeError("wrong character")
        cur.execute("SELECT SecurityLevel,RealmID FROM client442_auth.account_access WHERE AccountID=1")
        if cur.fetchall(): raise RuntimeError("setup requires a normal lab account")
    lab.server_command("account set gmlevel CLIENTLAB 3 -1")
    try:
        time.sleep(.5)
        asyncio.run(setup(config, flight_only=args.flight_only))
    finally:
        lab.server_command("account set gmlevel CLIENTLAB 0 -1")
        time.sleep(.5)
    verify(config)
    print("Verified level, all professions, equipped gear, Survey and normal account permissions.")


if __name__ == "__main__": main()
