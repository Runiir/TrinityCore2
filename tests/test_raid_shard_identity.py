from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.raid_program import raid_shard_identity as ids

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
LEGACY_FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
MODES = tuple(ids.MODES)
BOSSES = range(13)
BOSS_CODES = ("mgw", "omn", "chi", "atr", "mal", "nef", "hal", "val", "asc", "cho", "sin", "con", "ala")


def _all_tuples():
    for raid in ids.RAID_NUMBERS:
        for mode in MODES:
            for boss in BOSSES:
                for copy in range(ids.MAX_COPIES):
                    for slot in range(1, ids.MAX_SLOTS + 1):
                        yield raid, mode, boss, copy, slot


def test_documented_examples():
    packed = ids.packed_index("blackwing_descent", "10N", 0, 0, 1)
    assert packed == 1_000_001
    assert ids.character_guid(packed) == 11_000_001
    assert ids.account_id(packed) == 21_000_001
    assert ids.pet_id(packed) == 31_000_001
    assert ids.item_guid(packed, 0) == 1_100_000_100
    assert ids.item_guid(packed, 99) == 1_100_000_199
    assert ids.account_name(packed) == "RS1000001"
    assert ids.character_name("blackwing_descent", "mgw", "10N", 0, 1) == "Bwmgwnba"
    nefarian = ids.packed_index("blackwing_descent", "10N", 5, 1, 7)
    assert ids.character_guid(nefarian) == 11_005_107
    assert ids.cohort_id("blackwing_descent", "10N", "magmaw", 0) == "blackwing_descent_10n_magmaw_c0"
    assert ids.pool_tag("blackwing_descent_10n_magmaw_c0") == "blackwing_descent_10n_magmaw_c0_diagnostic"


def test_every_raid_thirteen_bosses_ten_copies_twenty_five_slots_never_collide():
    guids, accounts, pets, item_bases, names, usernames = set(), set(), set(), [], set(), set()
    count = 0
    for raid, mode, boss, copy, slot in _all_tuples():
        packed = ids.packed_index(raid, mode, boss, copy, slot)
        guids.add(ids.character_guid(packed))
        accounts.add(ids.account_id(packed))
        pets.add(ids.pet_id(packed))
        item_bases.append(ids.item_guid_base(packed))
        usernames.add(ids.account_name(packed))
        name = ids.character_name(raid, BOSS_CODES[boss], mode, copy, slot)
        assert ids.name_rule_failures(name) == [], name
        names.add(name)
        count += 1
    assert count == len(ids.RAID_NUMBERS) * 4 * 13 * 10 * 25 >= 5 * 4 * 13 * 10 * 25
    assert len(guids) == len(accounts) == len(pets) == len(usernames) == len(names) == count
    item_bases.sort()
    # Each character owns [base, base + 99]; distinct multiples of 100 never overlap.
    assert all(right - left >= ids.ITEMS_PER_CHARACTER for left, right in zip(item_bases, item_bases[1:]))
    assert max(item_bases) + ids.ITEMS_PER_CHARACTER - 1 <= ids.MAX_SIGNED_INT32
    assert max(max(guids), max(accounts), max(pets)) < ids.ITEM_GUID_BASE
    assert max(guids) < ids.ACCOUNT_ID_BASE and max(accounts) < ids.PET_ID_BASE


def test_every_identity_stays_outside_the_legacy_validation_ranges():
    legacy = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
    legacy_guids = {bot["character_guid"] for shard in legacy["shards"] for bot in shard["bots"]}
    legacy_accounts = {bot["account_id"] for shard in legacy["shards"] for bot in shard["bots"]}
    assert min(legacy_guids) == 30001 and max(legacy_guids) == 30510
    for raid in ids.RAID_NUMBERS:
        for mode in MODES:
            ranges = ids.reserved_ranges(raid, mode)
            for field, (low, high) in ranges.items():
                legacy_low, legacy_high = ids.LEGACY_RESERVED_RANGES[field]
                assert high < legacy_low or low > legacy_high, (raid, mode, field)
            assert not any(ranges["character_guid"][0] <= guid <= ranges["character_guid"][1] for guid in legacy_guids)
            assert not any(ranges["account_id"][0] <= account <= ranges["account_id"][1] for account in legacy_accounts)
    ranges = [ids.reserved_ranges(raid, mode)["character_guid"] for raid in ids.RAID_NUMBERS for mode in MODES]
    ranges.sort()
    assert all(left[1] < right[0] for left, right in zip(ranges, ranges[1:]))


def test_generated_suffixes_cannot_form_three_consecutive_letters():
    assert not set(ids.COPY_LETTERS) & {info["letter"] for info in ids.MODES.values()}
    for raid in ids.RAID_NUMBERS:
        for mode in MODES:
            for copy in range(ids.MAX_COPIES):
                for slot in range(1, ids.MAX_SLOTS + 1):
                    name = ids.character_name(raid, "mgw", mode, copy, slot)
                    assert ids.name_rule_failures(name) == [], name


@pytest.mark.parametrize("name,reason", [
    ("Bwmgw1ba", "letters_casing_or_length"),
    ("bwmgwnba", "letters_casing_or_length"),
    ("Bwmgwnaaa", "three_consecutive_letters"),
    ("Abcdefghijklm", "letters_casing_or_length"),
])
def test_native_name_rules_are_enforced(name, reason):
    assert reason in ids.name_rule_failures(name)


@pytest.mark.parametrize("args", [
    ("unknown_raid", "10N", 0, 0, 1),
    ("blackwing_descent", "40N", 0, 0, 1),
    ("blackwing_descent", "10N", 100, 0, 1),
    ("blackwing_descent", "10N", 0, 10, 1),
    ("blackwing_descent", "10N", 0, 0, 0),
    ("blackwing_descent", "10N", 0, 0, 26),
])
def test_out_of_range_identity_inputs_fail_closed(args):
    with pytest.raises(ids.ShardIdentityError):
        ids.packed_index(*args)


def test_item_offsets_are_bounded():
    with pytest.raises(ids.ShardIdentityError):
        ids.item_guid(1_000_001, 100)


@pytest.mark.skipif(not (DBC / "NamesReserved.dbc").is_file(), reason="client DBCs not hydrated")
def test_native_profanity_and_reserved_patterns_are_loaded():
    validators = ids.load_name_validators(DBC)
    assert validators is not None and validators.profane and validators.reserved
    assert "reserved_name_pattern" in ids.name_rule_failures("Arthas", validators)
    assert ids.name_rule_failures("Bwmgwnba", validators) == []
