"""Pin both sides' opcode identities; numbers alone never imply equal payloads."""
import hashlib
import json
from pathlib import Path
import re

from tools.client_compatibility.auth.generate_schema import REVISION


def generate(reference):
    repo = Path(__file__).resolve().parents[3]
    name = "src/server/game/Server/Protocol/Opcodes.h"
    tables, hashes = {}, {}
    for label, root in [("legacy", repo), ("modern", reference)]:
        raw = (root / name).read_bytes()
        hashes[label] = hashlib.sha256(raw).hexdigest()
        tables[label] = {name: int(value, 16) for name, value in re.findall(
            r"\b((?:CMSG|SMSG|MSG)_[A-Z0-9_]+)\s*=\s*(0x[0-9A-Fa-f]+)", raw.decode())}
    target = Path(__file__).with_name("opcodes.json")
    target.write_text(json.dumps({"source_revision": REVISION, "source_hashes": hashes,
                                 "license": "GPL-2.0-or-later", **tables}, indent=2) + "\n")
    print("Generated pinned world opcode identities.")


if __name__ == "__main__":
    import sys
    generate(Path(sys.argv[1]))
