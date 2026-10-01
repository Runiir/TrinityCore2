"""Extract pinned TrinityCore protobuf descriptors for the lab login adapter.

Derived protocol definitions retain TrinityCore's GPL-2.0-or-later license.
Only C++ generator options are removed; wire fields and service types are kept.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

from google.protobuf import descriptor_pb2, json_format

REVISION = "6426c2bdadb6273774a9e1c894a9ecb6a55ef0a2"
SEEDS = ["rpc_types.proto", "connection_service.proto", "authentication_service.proto",
         "challenge_service.proto", "account_service.proto", "game_utilities_service.proto"]


def extract(source: str) -> bytes:
    match = re.search(r'InternalAddGeneratedFile\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+),\s*(\d+)\)', source)
    if not match:
        raise ValueError("generated descriptor not found")
    parts = re.findall(r'"(?:[^"\\]|\\.)*"', match[1])
    data = b"".join(ast.literal_eval("b" + part.replace(r"\?", "?")) for part in parts)
    if len(data) != int(match[2]):
        raise ValueError("descriptor length does not match C++ source")
    return data


def clear_options(message):
    message.ClearField("options")
    for field, values in message.ListFields():
        if field.message_type:
            for value in values if field.is_repeated else [values]:
                clear_options(value)


def generate(reference: Path, output: Path):
    pending, descriptors, sources = list(SEEDS), {}, {}
    while pending:
        name = pending.pop()
        if name in descriptors or name.startswith("global_extensions/"):
            continue
        source_path = "src/server/proto/Client/" + name.replace(".proto", ".pb.cc")
        raw = subprocess.check_output(["git", "show", REVISION + ":" + source_path], cwd=reference)
        descriptor = descriptor_pb2.FileDescriptorProto.FromString(extract(raw.decode()))
        pending.extend(descriptor.dependency)
        keep = [dependency for dependency in descriptor.dependency if not dependency.startswith("global_extensions/")]
        del descriptor.dependency[:]
        descriptor.dependency.extend(keep)
        del descriptor.public_dependency[:]
        del descriptor.weak_dependency[:]
        clear_options(descriptor)
        descriptors[name] = json_format.MessageToDict(descriptor, preserving_proto_field_name=True)
        sources[source_path] = hashlib.sha256(raw).hexdigest()
    output.write_text(json.dumps({"source_repository": "https://github.com/TrinityCore/TrinityCore",
        "source_revision": REVISION, "license": "GPL-2.0-or-later", "source_sha256": sources,
        "files": [descriptors[key] for key in sorted(descriptors)]}, indent=2) + "\n")
    print(f"Extracted {len(descriptors)} pinned protocol files into {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    args = parser.parse_args()
    generate(args.reference, Path(__file__).with_name("protocol_schema.json"))
