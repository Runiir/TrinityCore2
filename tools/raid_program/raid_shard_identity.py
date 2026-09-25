"""Collision-free identities for raid x mode x boss x copy x slot shard characters.

Every raid-shard character owns one packed decimal index

    RMBBCSS = raid(1..9) * 10^6 + mode(0..3) * 10^5 + boss(0..99) * 10^3
              + copy(0..9) * 10^2 + slot(1..99)

and derives all native identities from it:

    character guid  = 10_000_000 + RMBBCSS     (e.g. 11_000_001)
    account id      = 20_000_000 + RMBBCSS
    hunter pet id   = 30_000_000 + RMBBCSS
    item guid       = 9_800_000 + 100 * character guid + k   (k in 0..99)

Each field has its own decimal digits, so distinct tuples cannot collide, and
every range lies above the legacy validation ranges (character GUIDs
30001-30510, accounts 20001-20510, pets 8_700_xxx, sequential items
9_700_xxx). The item block of a character is exactly the block
`provision_human_participant.item_guid_block` gives that character GUID, so
raid-shard and human item blocks are keyed by distinct character GUIDs and
cannot overlap. Offset 99 of every block is the character's bag, the highest
item a loadout writes.

These fixed blocks sit above the core's MAX+1 allocators. `raid_shard_preflight`
refuses an apply unless no foreign row is inside the plan's reservation and,
after the apply, every allocator stands above it (the plan's anchor cohort,
which holds the highest ID of every table, is present or written first).
Names are ASCII letters only and are checked against the native player-name
rules (length, casing, three consecutive letters, profanity and reserved-name
DBC patterns).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

RAID_NUMBERS: dict[str, int] = {
    "blackwing_descent": 1,
    "bastion_of_twilight": 2,
    "throne_of_the_four_winds": 3,
    "firelands": 4,
    "dragon_soul": 5,
    "baradin_hold": 6,
}
RAID_NAME_CODES: dict[str, str] = {
    "blackwing_descent": "bw",
    "bastion_of_twilight": "bt",
    "throne_of_the_four_winds": "tf",
    "firelands": "fl",
    "dragon_soul": "ds",
    "baradin_hold": "bh",
}
# TrinityCore raid difficulty enum: 10N=0, 25N=1, 10H=2, 25H=3.
MODES: dict[str, dict[str, Any]] = {
    "10N": {"digit": 0, "letter": "n", "size": 10, "difficulty": "normal_10man", "raid_difficulty": 0, "token": "10n"},
    "10H": {"digit": 1, "letter": "h", "size": 10, "difficulty": "heroic_10man", "raid_difficulty": 2, "token": "10h"},
    "25N": {"digit": 2, "letter": "t", "size": 25, "difficulty": "normal_25man", "raid_difficulty": 1, "token": "25n"},
    "25H": {"digit": 3, "letter": "w", "size": 25, "difficulty": "heroic_25man", "raid_difficulty": 3, "token": "25h"},
}
# Copy letters are disjoint from mode letters, so no run of three equal
# letters can span the mode/copy/slot suffix of a generated name.
COPY_LETTERS = "bcdfgjklpr"
SLOT_LETTERS = "abcdefghijklmnopqrstuvwxy"
MAX_COPIES = len(COPY_LETTERS)
MAX_BOSS_NUMBER = 99
MAX_SLOTS = len(SLOT_LETTERS)
ITEMS_PER_CHARACTER = 100

CHARACTER_GUID_BASE = 10_000_000
ACCOUNT_ID_BASE = 20_000_000
PET_ID_BASE = 30_000_000
# Same base and stride as provision_human_participant.HUMAN_ITEM_GUID_BASE/STRIDE.
ITEM_BLOCK_BASE = 9_800_000
ITEM_GUID_BASE = ITEM_BLOCK_BASE + CHARACTER_GUID_BASE * 100
ACCOUNT_PREFIX = "RS"
POOL_SUFFIX = "_diagnostic"

# Inclusive legacy ranges that raid-shard identities must never enter.
LEGACY_RESERVED_RANGES: dict[str, tuple[int, int]] = {
    "character_guid": (1, 99_999),
    "account_id": (1, 99_999),
    "pet_id": (8_700_000, 8_799_999),
    "item_guid": (9_700_000, 9_799_999),
}
MAX_SIGNED_INT32 = 2_147_483_647
NAME_PATTERN = re.compile(r"[A-Z][a-z]{1,11}")


class ShardIdentityError(ValueError):
    pass


def mode_info(mode: str) -> dict[str, Any]:
    info = MODES.get(str(mode))
    if info is None:
        raise ShardIdentityError(f"unsupported_mode:{mode}")
    return info


def packed_index(raid: str, mode: str, boss_number: int, copy: int, slot: int) -> int:
    if raid not in RAID_NUMBERS:
        raise ShardIdentityError(f"unknown_raid:{raid}")
    raid_number = RAID_NUMBERS[raid]
    if not 1 <= raid_number <= 9:
        raise ShardIdentityError(f"raid_number_out_of_range:{raid}")
    for label, value, low, high in (("boss_number", boss_number, 0, MAX_BOSS_NUMBER),
                                    ("copy", copy, 0, MAX_COPIES - 1),
                                    ("slot", slot, 1, MAX_SLOTS)):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ShardIdentityError(f"{label}_out_of_range:{value}")
    return (raid_number * 1_000_000 + mode_info(mode)["digit"] * 100_000
            + boss_number * 1_000 + copy * 100 + slot)


def character_guid(packed: int) -> int:
    return CHARACTER_GUID_BASE + packed


def account_id(packed: int) -> int:
    return ACCOUNT_ID_BASE + packed


def pet_id(packed: int) -> int:
    return PET_ID_BASE + packed


def item_block_for_character(guid: int) -> int:
    """First item GUID of a character's 100-item block (the human tool's formula)."""
    return ITEM_BLOCK_BASE + int(guid) * ITEMS_PER_CHARACTER


def item_guid_base(packed: int) -> int:
    return item_block_for_character(character_guid(packed))


def item_block_owner(item: int) -> int:
    """Character GUID whose block contains this item GUID."""
    return (int(item) - ITEM_BLOCK_BASE) // ITEMS_PER_CHARACTER


def item_guid(packed: int, offset: int) -> int:
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset < ITEMS_PER_CHARACTER:
        raise ShardIdentityError(f"item_offset_out_of_range:{offset}")
    return item_guid_base(packed) + offset


def account_name(packed: int) -> str:
    return f"{ACCOUNT_PREFIX}{packed}"


def character_name(raid: str, boss_code: str, mode: str, copy: int, slot: int) -> str:
    raid_code = RAID_NAME_CODES.get(raid)
    if not raid_code:
        raise ShardIdentityError(f"unknown_raid:{raid}")
    if not re.fullmatch(r"[a-z]{3}", str(boss_code or "")):
        raise ShardIdentityError(f"boss_code_must_be_three_lowercase_letters:{boss_code}")
    if not 0 <= copy < MAX_COPIES or not 1 <= slot <= MAX_SLOTS:
        raise ShardIdentityError(f"name_index_out_of_range:{copy}:{slot}")
    letters = raid_code + boss_code + mode_info(mode)["letter"] + COPY_LETTERS[copy] + SLOT_LETTERS[slot - 1]
    return letters[0].upper() + letters[1:]


def cohort_id(raid: str, mode: str, boss_key: str, copy: int) -> str:
    """`<raid>_<size><diff>_<boss>_c<copy>` from the round-1 naming contract."""
    return f"{raid}_{mode_info(mode)['token']}_{boss_key}_c{copy}"


def pool_tag(cohort: str) -> str:
    return cohort + POOL_SUFFIX


def name_rule_failures(name: str, validators: "NameValidators | None" = None) -> list[str]:
    """Return every native CheckPlayerName rule the name would fail."""
    failures: list[str] = []
    if not NAME_PATTERN.fullmatch(name or ""):
        failures.append("letters_casing_or_length")
    lowered = (name or "").lower()
    if any(lowered[i] == lowered[i - 1] == lowered[i - 2] for i in range(2, len(lowered))):
        failures.append("three_consecutive_letters")
    if validators is not None:
        failures.extend(validators.failures(lowered))
    return failures


class NameValidators:
    """Native enUS profanity/reserved name patterns from the client DBCs.

    Trinity loads language 0 (enUS) and -1 (all locales) patterns and matches
    them case-insensitively. The DBC patterns use `\\<`/`\\>` word anchors;
    they are translated to `\\b`, which is at least as strict for
    letters-only names.
    """

    def __init__(self, profane: list[re.Pattern[str]], reserved: list[re.Pattern[str]]):
        self.profane = profane
        self.reserved = reserved

    def failures(self, lowered: str) -> list[str]:
        result = []
        if any(pattern.search(lowered) for pattern in self.profane):
            result.append("profane_name_pattern")
        if any(pattern.search(lowered) for pattern in self.reserved):
            result.append("reserved_name_pattern")
        return result


def _compile_patterns(rows: Iterable[list[Any]]) -> list[re.Pattern[str]]:
    patterns = []
    for row in rows:
        if int(row[2]) not in (0, -1):
            continue
        text = str(row[1]).replace("\\<", r"\b").replace("\\>", r"\b")
        try:
            patterns.append(re.compile(text, re.IGNORECASE))
        except re.error:
            literal = re.sub(r"[^a-z]", "", text.lower())
            if literal:
                patterns.append(re.compile(re.escape(literal), re.IGNORECASE))
    return patterns


def load_name_validators(dbc_dir: Path) -> NameValidators | None:
    from tools.bot_ml.build_validation_provisioning import load_wdbc_values

    profanity = dbc_dir / "NamesProfanity.dbc"
    reserved = dbc_dir / "NamesReserved.dbc"
    if not profanity.is_file() or not reserved.is_file():
        return None
    return NameValidators(_compile_patterns(load_wdbc_values(profanity, "nsi")),
                          _compile_patterns(load_wdbc_values(reserved, "nsi")))


def reserved_ranges(raid: str, mode: str) -> dict[str, list[int]]:
    """Inclusive identity address space of one raid/mode (all bosses, copies, slots).

    This is the collision proof's address space, not the apply reservation:
    `raid_shard_preflight.plan_reservation` bounds each apply by the IDs the
    plan actually uses.
    """
    low = packed_index(raid, mode, 0, 0, 1)
    high = packed_index(raid, mode, MAX_BOSS_NUMBER, MAX_COPIES - 1, MAX_SLOTS)
    return {
        "character_guid": [character_guid(low), character_guid(high)],
        "account_id": [account_id(low), account_id(high)],
        "pet_id": [pet_id(low), pet_id(high)],
        "item_guid": [item_guid(low, 0), item_guid(high, ITEMS_PER_CHARACTER - 1)],
    }


def legacy_overlaps(identity: dict[str, int]) -> list[str]:
    """Names of identity fields that fall inside a legacy validation range."""
    overlaps = []
    for field, (low, high) in LEGACY_RESERVED_RANGES.items():
        value = identity.get(field)
        if value is not None and low <= int(value) <= high:
            overlaps.append(field)
    return overlaps


def scheme_description() -> dict[str, Any]:
    return {
        "schema": "raid_shard_identity_scheme_v1",
        "packed_index": "raid*10^6 + mode*10^5 + boss*10^3 + copy*10^2 + slot",
        "character_guid_base": CHARACTER_GUID_BASE,
        "account_id_base": ACCOUNT_ID_BASE,
        "pet_id_base": PET_ID_BASE,
        "item_guid": "9_800_000 + 100 * character_guid + offset (provision_human_participant.item_guid_block)",
        "item_block_base": ITEM_BLOCK_BASE,
        "items_per_character": ITEMS_PER_CHARACTER,
        "allocator_policy": "raid_shard_preflight: no foreign row in the plan reservation; every "
                            "core/auth allocator above it after the apply (anchor cohort present or first)",
        "raid_numbers": dict(RAID_NUMBERS),
        "mode_digits": {mode: info["digit"] for mode, info in MODES.items()},
        "limits": {"copies": MAX_COPIES, "boss_number_max": MAX_BOSS_NUMBER, "slots": MAX_SLOTS},
        "legacy_reserved_ranges": {key: list(value) for key, value in LEGACY_RESERVED_RANGES.items()},
        "name": "raid_code(2) + boss_code(3) + mode_letter + copy_letter + slot_letter",
    }
