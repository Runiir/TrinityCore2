"""Read-only comparison of the legacy core with a pinned Classic reference."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


FILES = [
    "CMakeLists.txt", "src/server/CMakeLists.txt", "sql/base/auth_database.sql",
    "src/server/shared/Realm/ClientBuildInfo.cpp",
    "src/server/shared/Realm/ClientBuildInfo.h",
    "src/server/authserver/Server/AuthSession.cpp",
    "src/server/bnetserver/Services/AuthenticationService.cpp",
    "src/server/bnetserver/Services/GameUtilitiesService.cpp",
    "src/server/bnetserver/REST/LoginRESTService.cpp",
    "src/server/bnetserver/bnetserver.conf.dist",
    "src/server/game/Server/WorldSocket.cpp",
    "src/server/game/Server/WorldSocket.h",
    "src/server/game/Server/Protocol/Opcodes.h",
    "src/server/game/Server/Packets/AuthenticationPackets.cpp",
    "src/server/game/Server/Packets/AuthenticationPackets.h",
    "src/server/game/Server/Packets/CharacterPackets.cpp",
    "src/server/game/Server/Packets/CharacterPackets.h",
    "src/server/game/Server/Packets/MovementPackets.cpp",
    "src/server/game/Server/Packets/MovementPackets.h",
    "src/server/game/Handlers/MovementHandler.cpp",
    "src/server/game/Entities/Object/MovementInfo.h",
    "src/server/game/Movement/MovementStructures.cpp",
    "src/server/game/Entities/Object/ObjectGuid.h",
    "src/server/game/Entities/Object/Updates/UpdateFields.h",
    "src/server/game/Entities/Object/Updates/UpdateFields.cpp",
    "src/server/game/Entities/Object/Updates/UpdateData.cpp",
    "src/server/game/DataStores/DBCStores.cpp",
    "src/server/game/DataStores/DB2Stores.cpp",
    "src/server/game/DataStores/DB2Metadata.h",
    "src/common/Cryptography/Authentication/WorldPacketCrypt.cpp",
    "src/common/Cryptography/Authentication/WorldPacketCrypt.h",
    "src/common/Cryptography/AES.cpp",
    "src/server/game/Server/Protocol/ServerPktHeader.h",
    "src/server/worldserver/worldserver.conf.dist",
    "sql/base/characters_database.sql",
    "sql/base/dev/hotfixes_database.sql",
    "src/tools/map_extractor/System.cpp",
    "src/common/Collision/Maps/MapDefines.h",
    "src/common/Collision/VMapDefinitions.h",
]


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def opcodes(text: str) -> dict[str, int]:
    return {name: int(value, 16) for name, value in re.findall(
        r"^\s*((?:CMSG|SMSG|MSG|UMSG)_[A-Z0-9_]+)\s*=\s*(0x[0-9A-Fa-f]+)\s*[,;]", text, re.M)}


def executable_identity(path: Path) -> dict:
    data = path.read_bytes()
    marker = struct.pack("<I", 0xFEEF04BD)
    versions, start = [], 0
    while (offset := data.find(marker, start)) >= 0:
        start = offset + 4
        if offset + 52 <= len(data):
            values = struct.unpack_from("<13I", data, offset)
            if values[1] == 0x10000:
                versions.append({
                    "resource_offset": offset,
                    "file_version": [values[2] >> 16, values[2] & 65535, values[3] >> 16, values[3] & 65535],
                    "product_version": [values[4] >> 16, values[4] & 65535, values[5] >> 16, values[5] & 65535],
                })
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "version_resources": versions,
            "limits": "Version resource and file hash only; no live protocol or patch behavior tested."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-root", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--reference-commit", required=True)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output already exists; preserve the previous audit")
    upstream_commit = git(args.reference_root, "rev-parse", args.reference_commit)
    if upstream_commit != args.reference_commit:
        raise SystemExit("reference must be an exact full commit hash")
    args.output.mkdir(parents=True)
    files, source = [], {"local": {}, "classic": {}}
    for name in FILES:
        record = {"path": name}
        for label, root in [("local", args.local_root), ("classic", args.reference_root)]:
            if label == "local":
                path = root / name
                data = path.read_bytes() if path.is_file() else None
            else:
                exists = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{upstream_commit}:{name}"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
                data = subprocess.check_output(["git", "-C", str(root), "show", f"{upstream_commit}:{name}"]) if exists else None
            if data is None:
                record[label] = {"present": False}
                continue
            destination = args.output / label / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            text = data.decode("utf-8")
            source[label][name] = text
            record[label] = {"present": True, "sha256": hashlib.sha256(data).hexdigest(), "lines": len(text.splitlines())}
        if name in source["local"] and name in source["classic"]:
            diff = "".join(difflib.unified_diff(source["local"][name].splitlines(True),
                source["classic"][name].splitlines(True), fromfile="legacy/" + name, tofile="classic/" + name))
            destination = args.output / "diffs" / (name + ".diff")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(diff)
            record["identical"] = not diff
        files.append(record)
    name = "src/server/game/Server/Protocol/Opcodes.h"
    left, right = opcodes(source["local"][name]), opcodes(source["classic"][name])
    common = sorted(left.keys() & right.keys())
    selected = ["CMSG_AUTH_SESSION", "SMSG_AUTH_CHALLENGE", "CMSG_PLAYER_LOGIN", "SMSG_LOGIN_VERIFY_WORLD",
                "SMSG_UPDATE_OBJECT", "MSG_MOVE_START_FORWARD", "CMSG_MOVE_START_FORWARD", "MSG_MOVE_STOP", "CMSG_MOVE_STOP"]
    comparison = {
        "legacy_count": len(left), "classic_count": len(right), "common_names": len(common),
        "same_numeric_value": sum(left[k] == right[k] for k in common),
        "changed_numeric_value": sum(left[k] != right[k] for k in common),
        "legacy_only": sorted(left.keys() - right.keys()), "classic_only": sorted(right.keys() - left.keys()),
        "selected": {k: {"legacy": hex(left[k]) if k in left else None, "classic": hex(right[k]) if k in right else None} for k in selected},
        "limits": "Static explicit-hex enumeration comparison. Renamed packets require semantic review; equal opcode numbers do not prove matching payloads.",
    }
    report = {
        "schema": "client_compatibility_static_audit_v1", "local_commit": git(args.local_root, "rev-parse", "HEAD"),
        "local_tracked_dirty": bool(git(args.local_root, "diff", "--name-only", "HEAD")),
        "reference_commit": upstream_commit,
        "reference_commit_metadata": git(args.reference_root, "show", "-s", "--format=%cI %s", upstream_commit),
        "client": executable_identity(args.client), "files": files, "opcodes": comparison,
        "audit_tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "live_tested": False, "database_accessed": False,
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "reference": upstream_commit,
                     "client_version": report["client"]["version_resources"], "opcodes": comparison["selected"]}, indent=2))


if __name__ == "__main__":
    main()
