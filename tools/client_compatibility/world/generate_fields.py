"""Extract exact create-field order from the pinned generated Classic serializers.

Only source definitions are retained. Runtime/native player data never enters
this schema. Derived definitions are GPL-2.0-or-later, TrinityCore AUTHORS.
"""
import hashlib
import json
from pathlib import Path
import re

from tools.client_compatibility.auth.generate_schema import REVISION


def body_at(source, start):
    depth, pos = 1, start
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[start:pos - 1]


def template_type(declaration):
    declaration = declaration.strip()
    if declaration.startswith(("UpdateField<", "UpdateFieldArray<", "DynamicUpdateField<", "OptionalUpdateField<")):
        start = declaration.index("<") + 1
        depth = 0
        for pos in range(start, len(declaration)):
            char = declaration[pos]
            if char == "<": depth += 1
            elif char == ">": depth -= 1
            elif char == "," and depth == 0:
                return declaration[start:pos].removeprefix("UF::")
    return declaration.removeprefix("UF::")


def generate(root):
    base = root / "src/server/game/Entities/Object/Updates"
    header, source = (base / "UpdateFields.h").read_text(), (base / "UpdateFields.cpp").read_text()
    types = {}
    for match in re.finditer(r"^struct (\w+)[^\n]*\n\{", header, re.M):
        contents = body_at(header, match.end())
        fields = {}
        for line in contents.splitlines():
            parsed = re.fullmatch(r"\s*([^;{}()]+) (\w+);\s*", line)
            if parsed:
                fields[parsed[2]] = template_type(parsed[1])
        types[match[1]] = fields
    functions = {}
    for match in re.finditer(r"void (\w+)::WriteCreate\([^\n]+\) const\n\{", source):
        contents = body_at(source, match.end())
        functions[match[1]] = [line.strip() for line in contents.splitlines() if line.strip()]
    schema = {"source_revision": REVISION, "license": "GPL-2.0-or-later",
              "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [base / "UpdateFields.h", base / "UpdateFields.cpp"]},
              "types": types, "create": functions}
    Path(__file__).with_name("fields.json").write_text(json.dumps(schema, indent=2) + "\n")
    print(f"Pinned {len(functions)} create serializers and {len(types)} structure definitions.")


if __name__ == "__main__":
    import sys
    generate(Path(sys.argv[1]))
