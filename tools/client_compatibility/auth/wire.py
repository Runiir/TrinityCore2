"""Bounded Battle.net protobuf framing from the pinned Classic reference."""
import json
from pathlib import Path
import struct

from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
from google.protobuf.message import DecodeError

SCHEMA = json.loads(Path(__file__).with_name("protocol_schema.json").read_text())
POOL = descriptor_pool.DescriptorPool()
pending = {item["name"]: item for item in SCHEMA["files"]}
while pending:
    ready = [name for name, item in pending.items() if not any(dep in pending for dep in item.get("dependency", []))]
    if not ready:
        raise RuntimeError("cyclic or incomplete login descriptors")
    for name in ready:
        descriptor = json_format.ParseDict(pending.pop(name), descriptor_pb2.FileDescriptorProto())
        POOL.Add(descriptor)


def message(name, data=None, **fields):
    if not name.startswith("bgs."):
        name = "bgs.protocol." + name
    result = message_factory.GetMessageClass(POOL.FindMessageTypeByName(name))(**fields)
    if data is not None:
        try:
            result.ParseFromString(data)
        except DecodeError as error:
            raise ValueError("malformed RPC protobuf") from error
        if not result.IsInitialized():
            raise ValueError("required RPC fields are missing")
    return result


def frame(header, payload=b""):
    if hasattr(payload, "SerializeToString"):
        payload = payload.SerializeToString()
    header.size = len(payload)
    data = header.SerializeToString()
    return struct.pack(">H", len(data)) + data + payload


async def read(reader):
    size = struct.unpack(">H", await reader.readexactly(2))[0]
    if not 1 <= size <= 4096:
        raise ValueError("invalid RPC header length")
    header = message("Header", await reader.readexactly(size))
    if header.size > 65536:
        raise ValueError("RPC body exceeds the lab limit")
    return header, await reader.readexactly(header.size)


def response(token, payload=b"", status=0):
    return frame(message("Header", service_id=0xFE, token=token, status=status), payload)


def request(service_hash, method, token, payload):
    return frame(message("Header", service_id=0, service_hash=service_hash,
                         method_id=method, token=token), payload)
