"""Interpret the bounded generated create serializers, with explicit field types.

Native fields populate supported values; modern-only collections default empty.
Unknown executable statements fail instead of silently changing packet layout.
"""
import json
from pathlib import Path
import re

SCHEMA = json.loads(Path(__file__).with_name("fields.json").read_text())
FORMATS = {"int8": "b", "uint8": "B", "int16": "h", "uint16": "H",
           "int32": "i", "uint32": "I", "int64": "q", "uint64": "Q", "float": "f"}


def expression(text, values, variables):
    text = text.strip().replace("->", ".")
    viewer = re.fullmatch(r"ViewerDependentValue<(\w+)Tag>::GetValue\(this, owner, receiver\)", text)
    if viewer:
        return values.get(viewer[1], 0)
    size = re.fullmatch(r"(.+)\.size\(\)", text)
    if size:
        return len(expression(size[1], values, variables) or [])
    optional = re.fullmatch(r"(.+)\.has_value\(\)", text)
    if optional:
        return bool(expression(optional[1], values, variables))
    if text in {"false", "true"}:
        return text == "true"
    if re.fullmatch(r"-?\d+(?:\.\d+)?f?", text):
        return float(text.removesuffix("f")) if "." in text else int(text)
    nested_index = re.fullmatch(r"(\w+)\[(\w+)\]\[(\w+)\]", text)
    if nested_index:
        array = expression(f"{nested_index[1]}[{nested_index[2]}]", values, variables) or []
        index = int(expression(nested_index[3], values, variables))
        return array[index] if index < len(array) else 0
    indexed = re.fullmatch(r"(\w+)\[(\w+)\]", text)
    if indexed:
        array = values.get(indexed[1], [])
        index = int(expression(indexed[2], values, variables))
        return array[index] if index < len(array) else 0
    if text in variables:
        return variables[text]
    if text.startswith("*"):
        return expression(text[1:], values, variables)
    member = re.fullmatch(r"(\w+)\.(\w+)", text)
    if member:
        return (values.get(member[1]) or {}).get(member[2], 0)
    if re.fullmatch(r"\w+", text):
        return values.get(text, 0)
    raise ValueError("unsupported create-field expression: " + text)


def serialize(writer, kind, values=None, visibility=1):
    values = values or {}
    lines = SCHEMA["create"][kind]
    types = SCHEMA["types"][kind]

    def block(start, variables, execute=True):
        pos = start
        while pos < len(lines):
            line = lines[pos]
            pos += 1
            if line == "}":
                return pos
            if line == "{":
                pos = block(pos, variables, execute)
                continue
            loop = re.fullmatch(r"for \(uint32 (\w+) = 0; \w+ < (.*); \+\+\w+\)", line)
            if loop:
                count = int(expression(loop[2], values, variables) or 0) if execute else 0
                if count > 10000:
                    raise ValueError("create array exceeds bound")
                if lines[pos] != "{":
                    raise ValueError("unbraced generated loop")
                end = block(pos + 1, variables, False)
                for index in range(count):
                    block(pos + 1, {**variables, loop[1]: index}, execute)
                pos = end
                continue
            condition = re.fullmatch(r"if \((.*)\)", line)
            if condition:
                text = condition[1]
                flags = re.fullmatch(r"fieldVisibilityFlags.HasFlag\((.+)\)", text)
                if flags:
                    masks = {"Owner": 1, "PartyMember": 2, "UnitAll": 4, "Empath": 8}
                    active = bool(visibility & sum(masks[name] for name in re.findall(r"UpdateFieldFlag::(\w+)", flags[1])))
                else:
                    active = bool(expression(text, values, variables)) if execute else False
                if lines[pos] != "{":
                    raise ValueError("unbraced generated condition")
                pos = block(pos + 1, variables, execute and active)
                continue
            if not execute:
                continue
            if line == "data.FlushBits();":
                writer.flush()
                continue
            bits = re.fullmatch(r"data.WriteBits\((.*), (\d+)\);", line)
            bit = re.fullmatch(r"data.WriteBit\((.*)\);", line)
            if bits or bit:
                writer.bits(int(expression((bits or bit)[1], values, variables)), int(bits[2]) if bits else 1)
                continue
            string = re.fullmatch(r"data.WriteString\((\w+)\);", line)
            if string:
                writer.raw(str(values.get(string[1], "")).encode())
                continue
            typed = re.fullmatch(r"data << (\w+)\((.*)\);", line)
            if typed and typed[1] in FORMATS:
                value = expression(typed[2], values, variables)
                writer.pack(FORMATS[typed[1]], value)
                continue
            nested = re.fullmatch(r"(.+?)(?:\.|->)WriteCreate\(data, owner, receiver\);", line)
            if nested:
                field = re.match(r"\w+", nested[1])[0]
                nested_type = types[field]
                dynamic = re.fullmatch(r"DynamicUpdateFieldBase<UF::(\w+)>", nested_type)
                if dynamic: nested_type = dynamic[1]
                serialize(writer, nested_type, expression(nested[1], values, variables) or {}, visibility)
                continue
            bare = re.fullmatch(r"data << (.+);", line)
            if bare:
                field = re.match(r"\w+", bare[1])[0]
                field_type = types[field]
                value = expression(bare[1], values, variables)
                if field_type == "ObjectGuid":
                    writer.guid(*(value or (0, 0)))
                elif field_type.endswith("DungeonScoreSummary"):
                    writer.pack("ffI", 0, 0, 0)
                elif field_type.endswith("PerksVendorItem"):
                    writer.raw(bytes(40)).bits(0, 2).flush()
                elif field_type.endswith("ItemBonusKey"):
                    value = value or {}
                    bonuses = value.get("BonusListIDs", [])
                    writer.pack("iI", value.get("ItemID", 0), len(bonuses))
                    writer.pack("i" * len(bonuses), *bonuses)
                elif field_type in FORMATS:
                    writer.pack(FORMATS[field_type], value)
                else:
                    raise ValueError("unsupported untyped create-field: " + field_type)
                continue
            if "stateWorldEffectIDs" in line and "=" in line:
                values["stateWorldEffectIDs"] = []
                continue
            raise ValueError("unsupported create-field statement: " + line)
        return pos

    block(0, {})
