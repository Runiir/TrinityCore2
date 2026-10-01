"""Pin native field IDs and movement sequences from this isolated checkout.

Definitions derive from TrinityCore, GPL-2.0-or-later, TrinityCore AUTHORS.
"""
import hashlib
import json
from pathlib import Path
import re


def generate(root):
    output = Path(__file__).parent
    header = root / "src/server/game/Entities/Object/Updates/UpdateFields.h"
    fields = {}
    for m in re.finditer(r"^\s*(\w+)\s*=\s*(?:(\w+) \+ )?(0x[0-9A-Fa-f]+)", header.read_text(), re.M):
        fields[m[1]] = fields.get(m[2], 0) + int(m[3], 16)
    (output / "native_fields.json").write_text(json.dumps(fields, indent=2) + "\n")
    path = root / "src/server/game/Movement/MovementStructures.cpp"
    source = path.read_text()
    tables = {m[1]: re.findall(r"MSE\w+", m[2]) for m in re.finditer(
        r"MovementStatusElements (?:const )?(\w+)\[\]\s*=\s*\{(.*?)\};", source, re.S)}
    sequences = {}
    for m in re.finditer(r"((?:\s*case \w+:)+)\s*return (\w+);", source):
        for name in re.findall(r"case (\w+):", m[1]):
            sequences[name] = tables[m[2]]
    (output / "native_movement.json").write_text(json.dumps({
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "field_source_sha256": hashlib.sha256(header.read_bytes()).hexdigest(),
        "license": "GPL-2.0-or-later", "sequences": sequences}, indent=2) + "\n")


if __name__ == "__main__":
    import sys
    generate(Path(sys.argv[1]))
