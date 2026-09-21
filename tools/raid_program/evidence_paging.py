"""Presentation-only bounded pages. Omitted data always has an explicit locator."""
from __future__ import annotations

import json
import shlex


def encoded(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def pointer_child(pointer, key):
    return pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")


def command_with(argv, **options):
    result = list(argv)

    def without_flag(arguments, flag):
        clean, index = [], 0
        while index < len(arguments):
            token = arguments[index]
            if token == flag:
                index += 2
            elif token.startswith(flag + '='):
                index += 1
            else:
                clean.append(token)
                index += 1
        return clean

    for name, value in options.items():
        flag = "--" + name.replace("_", "-")
        result = without_flag(result, flag)
        if value is not None:
            result.extend((flag, str(value)))
    # Continuations should not overwrite a caller's exported full result.
    result = without_flag(result, '--output')
    return shlex.join(["pixi", "run", "python", "-m", "tools.raid_program.evidence_view", *result])


def outline(value, pointer, depth=0):
    """Retain small scalar observations, replace large branches with typed locators."""
    if isinstance(value, dict):
        if depth >= 2:
            return {"view": "object_not_expanded", "path": pointer, "keys": list(value)[:12],
                    "key_count": len(value)}
        return {k: outline(v, pointer_child(pointer, k), depth+1) for k, v in list(value.items())[:16]} | (
            {"_view": {"path": pointer, "omitted_keys": len(value)-16}} if len(value)>16 else {})
    if isinstance(value, list):
        return {"view": "array_not_expanded", "path": pointer, "items": len(value)}
    if isinstance(value, str) and len(value) > 300:
        return {"view": "text_preview", "path": pointer, "characters": len(value), "preview": value[:300]}
    return value


def bounded_select(document, pointer, offset, limit, argv, budget=12000, *, view_path=False):
    from tools.raid_program.evidence_inputs import select_path
    size = limit
    while True:
        result = select_path(document, pointer, offset, size)
        result["requested_limit"] = limit
        result["page_limit"] = size
        flag = "view_path" if view_path else "path"
        if result["next_offset"] is not None:
            result["next_command"] = command_with(argv, **{flag: pointer}, offset=result["next_offset"], limit=size)
        if len(encoded(result)) <= budget:
            return result
        if size > 1:
            size = max(1, size//2)
            continue
        value = result["value"]
        if isinstance(value, list):
            result["value"] = [outline(value[0], pointer_child(pointer, offset))] if value else []
        elif isinstance(value, dict):
            result["value"] = {k: outline(v, pointer_child(pointer, k)) for k, v in value.items()}
        else:
            result["value"] = outline(value, pointer)
        result["view"] = "structure_only_for_oversized_item"
        result["detail_command_template"] = command_with(argv, **{flag: "JSON_POINTER_FROM_VIEW"}, offset=0, limit=5)
        return result
