"""Modern realm discovery while preserving the native world's actual build."""
import base64
import json
import struct
import zlib

from tools.client_compatibility.lab_runtime import connection
from .wire import message

ADDRESS = 0x01010001
SUBREGION = "1-1-0"
COMMANDS = {"Command_RealmListTicketRequest_v1", "Command_LastCharPlayedRequest_v1",
            "Command_RealmListRequest_v1", "Command_RealmJoinRequest_v1"}


def command_name(name):
    if name.startswith("Command_") and name not in COMMANDS:
        return name.rsplit("_", 1)[0]
    return name


def compressed(tag, data):
    raw = (tag + ":" + json.dumps(data, separators=(",", ":"))).encode() + b"\0"
    return struct.pack("<I", len(raw)) + zlib.compress(raw)


def variant(value):
    if isinstance(value, bytes):
        return message("Variant", blob_value=value)
    if isinstance(value, str):
        return message("Variant", string_value=value)
    if isinstance(value, int):
        return message("Variant", uint_value=value)
    raise ValueError("unsupported realm variant")


def attributes(response, values):
    for name, value in values.items():
        attr = response.attribute.add(name=name)
        attr.value.CopyFrom(variant(value))
    return response


def tagged_json(value):
    raw = value.blob_value
    if len(raw) > 32768 or b":" not in raw:
        raise ValueError("invalid realm JSON")
    return json.loads(raw.split(b":", 1)[1].rstrip(b"\0"))


def process(session, request):
    if not session.account:
        return 3, None
    params = {command_name(attr.name): attr.value for attr in request.attribute}
    commands = [name for name in params if name.startswith("Command_")]
    if len(commands) != 1:
        return 0xBC5, None
    command = commands[0]
    response = message("game_utilities.v1.ClientResponse")
    if command == "Command_RealmListTicketRequest_v1":
        identity = tagged_json(params["Param_Identity"])
        info = tagged_json(params["Param_ClientInfo"])["info"]
        if int(identity["gameAccountID"]) != session.account["id"]:
            return 0x8000006E, None
        secret = info["secret"]
        secret = base64.b64decode(secret, validate=True) if isinstance(secret, str) else bytes(secret)
        if len(secret) != 32:
            return 0x80000132, None
        session.client_secret = secret
        session.client_info = info
        return 0, attributes(response, {"Param_RealmListTicket": b"AuthRealmListTicket\0"})
    if not session.client_secret:
        return 0x80000132, None
    if command == "Command_LastCharPlayedRequest_v1":
        return 0, response
    if command == "Command_RealmListRequest_v1":
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT name,gamebuild,flag,timezone,icon FROM client442_auth.realmlist WHERE id=1")
            name, build, flags, timezone, icon = cursor.fetchone()
            cursor.execute("SELECT numchars FROM client442_auth.realmcharacters WHERE realmid=1 AND acctid=%s", (session.account["id"],))
            count = cursor.fetchone()
        # Do not relabel a 4.3.4 listener as 4.4.2. Auth can succeed independently.
        entry = {"wowRealmAddress": ADDRESS, "cfgTimezonesID": 1, "populationState": 1,
            "cfgCategoriesID": timezone, "version": {"versionMajor": 4, "versionMinor": 3,
                "versionRevision": 4, "versionBuild": build}, "cfgRealmsID": 1,
            "flags": flags | (0x10 if build != session.build else 0), "name": name,
            "cfgConfigsID": 1 if icon == 0 else 2, "cfgLanguagesID": 1}
        updates = {"updates": [{"wowRealmAddress": ADDRESS, "update": entry, "deleting": False}]}
        counts = {"counts": [{"wowRealmAddress": ADDRESS, "count": count[0] if count else 0}]}
        return 0, attributes(response, {"Param_RealmList": compressed("JSONRealmListUpdates", updates),
            "Param_CharacterCountList": compressed("JSONRealmCharacterCountList", counts)})
    if command == "Command_RealmJoinRequest_v1":
        # Native world authentication must be ported before modern join is valid.
        return 0x800000E1, None
    return 0xBC7, None
