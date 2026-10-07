"""Beast Lore learning needs exact owned wire, stock UI and preserved state."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import zlib

import pytest

from tools.client_compatibility import hunter_learn_contract as contract
from tools.client_compatibility import hunter_learn_evidence as evidence
from tools.client_compatibility import hunter_learn_pet as pet_evidence
from tools.client_compatibility import hunter_learn_preservation as preservation
from tools.client_compatibility import hunter_learn_sources as sources
from tools.client_compatibility import review_hunter_learn_checkpoint as reviewer
from tools.client_compatibility.hunter_rest_accrual import native_rest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_hunter_learn_trainer import trainer_fixture, SPAWN_BYTES
from tools.client_compatibility.world.tests.test_hunter_learn_trainer import (object_body as trainer_object_body,
    packed_guid as trainer_packed_guid, teleport_body as trainer_teleport_body)
from tools.client_compatibility import hunter_learn_trainer as trainer_evidence
from tools.client_compatibility import hunter_learn_reconciliation as reconciliation
from tools.client_compatibility.world.tests.test_hunter_learn_reconciliation import failed_case, navigation_case


SESSION = "native-owned-hunter"


def png_bytes(label):
    """A valid one-pixel RGB PNG makes the archive fixture structurally realistic."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    pixel = hashlib.sha256(label.encode()).digest()[:3]
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\x00" + pixel)) + chunk(b"IEND", b""))


def snapshot():
    value = {
        str(guid): {
            "native": {"guid": guid, "account": 1, "name": "Protected" + str(guid),
                       "online": 0, "money": 1000},
            "saved": {"spells": [], "auras": [], "quests": [], "actions": []},
            "inventory": [{"slot": 0, "item": 6948, "count": 1}],
            "pets": [],
        }
        for guid in range(1, 7)
    }
    value["6"]["native"] = {
        "guid": 6, "account": 2, "name": "Harnesshunt", "race": 1,
        "class": 3, "level": 10, "xp": 45, "online": 0,
        "money": contract.MONEY, "rest_bonus": 100.0, "is_logout_resting": 0,
        "totaltime": 100, "leveltime": 100, "logout_time": 1000, "latency": 0,
        "position_x": -9460.0, "position_y": 114.0, "position_z": 58.0,
        "orientation": 1.0, "map": 0,
    }
    value["6"]["saved"]["spells"] = deepcopy(contract.BASE_SPELLS)
    value["6"]["pets"] = [
        {"id": 4, "owner": 6, "entry": 42717, "name": "Harnesswolf",
         "renamed": 1, "slot": 5, "active": 0, "curhealth": 278,
         "savetime": 100, "CreatedBySpell": 883, "PetType": 1, "level": 10},
        {"id": 16, "owner": 6, "entry": 299, "name": "Wolf", "renamed": 0,
         "slot": 0, "active": 1, "curhealth": 278, "savetime": 200,
         "CreatedBySpell": 13481, "PetType": 1, "level": 10},
    ]
    return value


def learned_snapshot(before):
    after = deepcopy(before)
    after["6"]["native"]["money"] -= contract.PRICE
    after["6"]["saved"]["spells"] = sorted(contract.BASE_SPELLS + [[contract.SPELL, 1, 0]])
    return after


def resource_observation(money):
    empty = {"guid": 0, "id": 0, "count": 0}
    backpack = [deepcopy(empty) for _ in range(16)]
    backpack[0] = {"guid": 1234, "id": 6948, "count": 1}
    return {"money": money, "equipment": [deepcopy(empty) for _ in range(19)], "backpack": backpack,
            "bags": [[deepcopy(empty) for _ in range(36)] for _ in range(4)]}


def packet(direction, name, body, time):
    return {"session": SESSION, "direction": direction, "name": name,
            "body": body.hex(), "time": time}


def learn_packets():
    return [
        packet("to_native", "CMSG_TRAINER_BUY_SPELL",
               struct.pack("<QII", contract.TRAINER_GUID, 40, 1462), 1012.0),
        packet("from_native", "SMSG_LEARNED_SPELL", struct.pack("<II", 1462, 0), 1012.1),
        packet("to_client", "SMSG_LEARNED_SPELLS", struct.pack("<IIBIB", 1, 0, 0, 1462, 0), 1012.2),
    ]


def learn_checks(rows=None, before=None, after=None):
    before = snapshot() if before is None else before
    after = learned_snapshot(before) if after is None else after
    return contract.learned_checks(
        learn_packets() if rows is None else rows,
        before["6"]["saved"]["spells"], after["6"]["saved"]["spells"],
        before["6"]["native"], after["6"]["native"], SESSION, 1011.0, 1013.0,
    )


def book(learned):
    kind = "SPELL" if learned else "FUTURESPELL"
    return {"visible": True, "book_type": "spell", "skill_line": 1,
            "tabs": [{"index": 1, "name": "Beast Mastery", "checked": True}],
            "rows": [{"id": 1462, "api_id": 1462, "action": 1462,
                      "kind": kind, "api_kind": kind, "known": learned,
                      "trainer": not learned, "shown_name": "|cffffffffBeast Lore|r",
                      "name": "Beast Lore", "button": "SpellButton7"}]}


def precision_row(native, exact):
    return {**{key: native[key] for key in ("guid", "account", "name", "class", "level", "xp",
                                          "online", "rest_bonus", "logout_time", "is_logout_resting")},
            "exact_rest_bonus": exact, "exact_rest_bonus_float32_bits": struct.pack("<f", exact).hex()}


def parking_fixture():
    before = snapshot()
    after = learned_snapshot(before)
    exact, text = native_rest(100.0, 10, 7600, 1)
    after["6"]["native"].update(rest_bonus=text, totaltime=105, leveltime=105, logout_time=1020)
    after["6"]["pets"][1]["savetime"] = 201
    entry = {"phase": "owned_class_entered", "actor": {"guid": 6}, "native_session": SESSION,
             "started_at": 1009.9, "finished_at": 1010.3,
             "native_before_entry": deepcopy(before["6"]["native"]),
             "entered_native": {**before["6"]["native"], "online": 1},
             "state": {"player": "Harnesshunt", "level": 10, "xp_max": 7600,
                       "xp": 45, "xp_exhaustion": 2 * int(exact)},
             "login_packets": [packet("to_native", "CMSG_PLAYER_LOGIN", struct.pack("<Q", 6), 1010.1),
                               packet("from_native", "SMSG_LOGIN_VERIFY_WORLD", b"", 1010.2)]}
    return before, after, entry, precision_row(before["6"]["native"], 100.0), precision_row(after["6"]["native"], exact)


def assert_parking(value):
    before, after, entry, exact_before, exact_after = value
    return preservation.parked_preservation(before, after, entry, exact_before, exact_after,
                                           contract.MONEY - contract.PRICE, learned_snapshot(before)["6"]["saved"])


def test_exact_direct_1462_purchase_delivery_and_charge_are_required():
    assert all(learn_checks().values())
    packets = learn_packets()
    checks = learn_checks(packets)
    known = contract.reconciled_known({1515, 79682}, packets, checks)
    assert known == {1515, 79682, 1462}


@pytest.mark.parametrize("fault", [
    "foreign_guid", "foreign_trainer", "dependent_spell", "native_suffix", "modern_count",
    "missing_native", "missing_modern", "duplicate_buy", "duplicate_native", "duplicate_modern",
    "foreign_session", "outside_window", "reversed_delivery", "delivery_delay", "buy_failure",
])
def test_purchase_cannot_borrow_or_approximate_one_owned_direct_learn(fault):
    rows = learn_packets()
    if fault == "foreign_guid":
        rows[0]["body"] = struct.pack("<QII", contract.TRAINER_GUID + 1, 40, 1462).hex()
    elif fault == "foreign_trainer":
        rows[0]["body"] = struct.pack("<QII", contract.TRAINER_GUID, 154, 1462).hex()
    elif fault == "dependent_spell":
        rows[1]["body"] = struct.pack("<II", 93321, 0).hex()
    elif fault == "native_suffix":
        rows[1]["body"] += "00"
    elif fault == "modern_count":
        rows[2]["body"] = struct.pack("<IIBIB", 2, 0, 0, 1462, 0).hex()
    elif fault in ("missing_native", "missing_modern"):
        rows.pop(1 if fault == "missing_native" else 2)
    elif fault.startswith("duplicate_"):
        rows.append(deepcopy(rows[{"duplicate_buy": 0, "duplicate_native": 1, "duplicate_modern": 2}[fault]]))
    elif fault == "foreign_session":
        rows[2]["session"] = "foreign"
    elif fault == "outside_window":
        rows[2]["time"] = 1013.1
    elif fault == "reversed_delivery":
        rows[2]["time"] = 1012.05
    elif fault == "delivery_delay":
        rows[1]["time"], rows[2]["time"] = 1011.0, 1013.0
    else:
        rows.append(packet("from_native", "SMSG_TRAINER_BUY_FAILED", b"", 1012.15))
    assert not all(learn_checks(rows).values())


def test_foreign_and_outside_packets_do_not_supply_or_duplicate_owned_evidence():
    rows = learn_packets()
    rows += [{**rows[0], "session": "foreign"}, {**rows[1], "time": 1010.0}]
    assert all(learn_checks(rows).values())


@pytest.mark.parametrize("fault", ["already_known", "child_row", "extra_saved_row", "inactive_row",
                                  "wrong_cost", "xp_changed", "extra_native_field"])
def test_learning_cannot_hide_saved_or_resource_changes(fault):
    before = snapshot()
    after = learned_snapshot(before)
    if fault == "already_known":
        before["6"]["saved"]["spells"].append([1462, 1, 0])
    elif fault == "child_row":
        after["6"]["saved"]["spells"][-1] = [93321, 1, 0]
    elif fault == "extra_saved_row":
        after["6"]["saved"]["spells"].append([883, 1, 0])
    elif fault == "inactive_row":
        next(row for row in after["6"]["saved"]["spells"] if row[0] == 1462)[1] = 0
    elif fault == "wrong_cost":
        after["6"]["native"]["money"] -= 1
    elif fault == "xp_changed":
        after["6"]["native"]["xp"] += 1
    else:
        after["6"]["native"]["unknown_resource"] = 1
    assert not all(learn_checks(before=before, after=after).values())


@pytest.mark.parametrize("fault", ["login_known", "claimed_false", "claimed_truthy", "missing_event", "second_event"])
def test_reconciled_authority_requires_untrained_login_and_one_exact_native_event(fault):
    rows, login = learn_packets(), {1515, 79682}
    checks = learn_checks(rows)
    if fault == "login_known":
        login.add(1462)
    elif fault.startswith("claimed_"):
        checks["one_exact_native_purchase"] = False if fault == "claimed_false" else 1
    elif fault == "missing_event":
        rows.pop(1)
    else:
        rows.append(deepcopy(rows[1]))
    with pytest.raises(RuntimeError):
        contract.reconciled_known(login, rows, checks)


@pytest.mark.parametrize("learned", [False, True])
def test_stock_book_row_is_exact_for_untrained_and_learned_states(learned):
    probe = book(learned)
    assert contract.book_row(probe, learned) == probe["rows"][0]


@pytest.mark.parametrize("fault", ["duplicate", "missing", "hidden", "pet_book", "wrong_tab", "unchecked_tab",
                                  "api_id", "action", "api_kind", "kind", "known", "trainer", "name", "button"])
def test_spellbook_label_cannot_replace_exact_stock_beast_lore_identity(fault):
    probe = book(True)
    row = probe["rows"][0]
    if fault == "duplicate":
        probe["rows"].append(deepcopy(row))
    elif fault == "missing":
        probe["rows"] = []
    elif fault == "hidden":
        probe["visible"] = False
    elif fault == "pet_book":
        probe["book_type"] = "pet"
    elif fault == "wrong_tab":
        probe["tabs"][0]["name"] = "Survival"
    elif fault == "unchecked_tab":
        probe["tabs"][0]["checked"] = False
    elif fault in ("api_id", "action"):
        row[fault] = 1515
    elif fault in ("api_kind", "kind"):
        row[fault] = "FUTURESPELL"
    elif fault == "known":
        row["known"] = 1
    elif fault == "trainer":
        row["trainer"] = True
    elif fault == "name":
        row["shown_name"] = "Tame Beast"
    else:
        row["button"] = "CustomBeastLoreButton"
    with pytest.raises(RuntimeError):
        contract.book_row(probe, True)


def test_cleanup_restores_only_direct_spell_and_accepted_charge_without_mutating_sources():
    before, parked, _, _, _ = parking_fixture()
    original = deepcopy((before, parked))
    expected = contract.cleanup_expected(before, parked)
    assert (before, parked) == original
    assert expected["6"]["saved"] == before["6"]["saved"]
    assert expected["6"]["native"]["money"] == contract.MONEY
    expected["6"]["saved"]["spells"] = deepcopy(parked["6"]["saved"]["spells"])
    expected["6"]["native"]["money"] = contract.MONEY - contract.PRICE
    assert expected == parked


@pytest.mark.parametrize("fault", ["protected_actor", "hunter_online", "protected_online", "actor_identity",
                                  "inventory", "extra_saved", "wrong_charge", "already_known"])
def test_offline_cleanup_refuses_unaccepted_actor_saved_or_resource_changes(fault):
    before = snapshot()
    parked = learned_snapshot(before)
    if fault == "protected_actor":
        parked["2"]["native"]["money"] -= 1
    elif fault in ("hunter_online", "protected_online"):
        parked["6" if fault == "hunter_online" else "1"]["native"]["online"] = 1
    elif fault == "actor_identity":
        parked["6"]["native"]["account"] = 1
    elif fault == "inventory":
        parked["6"]["inventory"][0]["count"] += 1
    elif fault == "extra_saved":
        parked["6"]["saved"]["quests"].append([1, 1])
    elif fault == "wrong_charge":
        parked["6"]["native"]["money"] += 1
    else:
        before["6"]["saved"]["spells"].append([1462, 1, 0])
    with pytest.raises(RuntimeError):
        contract.cleanup_expected(before, parked)


def test_parking_attributes_rest_to_one_exact_native_login_and_preserves_living_pets():
    value = parking_fixture()
    proof = assert_parking(value)
    assert proof["matches"][0]["native_login_second"] == 1010
    assert proof["matches"][0]["offline_seconds"] == 10
    assert proof["rounded_baseline_reconstruction"] is False


@pytest.mark.parametrize("fault", ["protected_actor", "pose", "inventory", "saved", "xp", "accounting",
                                  "named_pet", "wolf_health", "wolf_name", "wolf_slot", "wolf_owner",
                                  "wolf_creator", "wolf_savetime", "missing_pet", "rest_bits", "login_session",
                                  "duplicate_login", "public_exhaustion"])
def test_parking_rejects_resource_pet_or_unattributed_login_changes(fault):
    value = parking_fixture()
    before, after, entry, _, exact_after = value
    native = after["6"]["native"]
    wolf = after["6"]["pets"][1]
    if fault == "protected_actor":
        after["1"]["native"]["money"] -= 1
    elif fault == "pose":
        native["position_x"] += 1
    elif fault == "inventory":
        after["6"]["inventory"] = []
    elif fault == "saved":
        after["6"]["saved"]["quests"] = [[1, 1]]
    elif fault == "xp":
        native["xp"] += 1
    elif fault == "accounting":
        native["totaltime"] = before["6"]["native"]["totaltime"] - 1
    elif fault == "named_pet":
        after["6"]["pets"][0]["savetime"] += 1
    elif fault.startswith("wolf_"):
        key, replacement = {"wolf_health": ("curhealth", 0), "wolf_name": ("name", "Harnesswolf"),
                            "wolf_slot": ("slot", 5), "wolf_owner": ("owner", 1),
                            "wolf_creator": ("CreatedBySpell", 982), "wolf_savetime": ("savetime", 199)}[fault]
        wolf[key] = replacement
    elif fault == "missing_pet":
        after["6"]["pets"].pop()
    elif fault == "rest_bits":
        exact_after["exact_rest_bonus_float32_bits"] = "00000000"
    elif fault == "login_session":
        entry["login_packets"][0]["session"] = "foreign"
    elif fault == "duplicate_login":
        entry["login_packets"].append(deepcopy(entry["login_packets"][0]))
    else:
        entry["state"]["xp_exhaustion"] += 1
    with pytest.raises(RuntimeError):
        assert_parking(value)


def reload_proof():
    return {"owner": 6, "pet_number": 16, "created_by_spell": 13481, "health": 278,
            "native_reload_source_verified": True}


def test_cast_free_creator_guard_preserves_exact_tame_creator_and_both_living_pets():
    before, current, _, _, _ = parking_fixture()
    original = deepcopy(current)
    expected = preservation.creator_expected(before, current, reload_proof())
    assert current == original
    assert expected == current


@pytest.mark.parametrize("fault", ["health", "named_pet", "creator", "savetime", "owner", "pet_number",
                                  "proof_health", "proof_creator", "unverified"])
def test_creator_normalization_cannot_repair_health_or_borrow_another_reload(fault):
    before, current, _, _, _ = parking_fixture()
    proof = reload_proof()
    if fault == "health":
        current["6"]["pets"][1]["curhealth"] = 0
    elif fault == "named_pet":
        current["6"]["pets"][0]["name"] = "Wolf"
    elif fault == "creator":
        current["6"]["pets"][1]["CreatedBySpell"] = 883
    elif fault == "savetime":
        current["6"]["pets"][1]["savetime"] = 199
    elif fault == "unverified":
        proof["native_reload_source_verified"] = False
    else:
        proof[{"owner": "owner", "pet_number": "pet_number", "proof_health": "health",
               "proof_creator": "created_by_spell"}[fault]] += 1
    with pytest.raises(RuntimeError):
        preservation.creator_expected(before, current, proof)


def native_packed_guid(guid):
    octets = [(guid >> (index * 8)) & 255 for index in range(8)]
    return bytes([sum(bool(value) << index for index, value in enumerate(octets))]) + bytes(value for value in octets if value)


def native_update_body(guid, fields, creation=False):
    blocks = max(fields) // 32 + 1
    masks = [sum(1 << (index % 32) for index in fields if index // 32 == block) for block in range(blocks)]
    prefix = struct.pack("<HIB", 0, 1, 1 if creation else 0) + native_packed_guid(guid)
    if creation:
        prefix += bytes([3]) + Writer().bits(0, 8).bits(0, 24).bits(0, 2).bits(1, 1).bits(0, 3).pack("4f", 1, -9460, 114, 58).finish()
    return prefix + struct.pack("<B" + "I" * blocks, blocks, *masks) + b"".join(struct.pack("<I", fields[index]) for index in sorted(fields))


def pet_creation(session, time):
    guid = (0xF14 << 52) | (299 << 32) | 16
    fields = {5: 299, 16: 6, 17: 0, 18: 6, 19: 0, 26: 198, INDEX["UNIT_FIELD_MAXHEALTH"]: 198,
              48: 10, 69: 16, 76: 13481}
    created = {**packet("from_native", "SMSG_UPDATE_OBJECT", native_update_body(guid, fields, True), time), "session": session}
    scale = {**packet("from_native", "SMSG_UPDATE_OBJECT", native_update_body(guid, {
        INDEX["UNIT_FIELD_HEALTH"]: 278, INDEX["UNIT_FIELD_MAXHEALTH"]: 278}), time + .01), "session": session}
    summon = INDEX["UNIT_FIELD_SUMMON"]
    owner = {**packet("from_native", "SMSG_UPDATE_OBJECT", native_update_body(6, {
        summon: guid & 0xFFFFFFFF, summon + 1: guid >> 32}), time + .02), "session": session}
    return json.loads(json.dumps(pet_evidence.reload_proof([created, scale, owner], session, time, time + .1, snapshot()["6"]["pets"][1])))


def actual_fixture(same_owner=False):
    entries, known = [], []
    tracking = evidence.tracking_state()
    tracking["members"] = set(evidence.TRACKING_MEMBERS)
    for index, start in enumerate((1010.0, 2010.0)):
        session = SESSION if index == 0 or same_owner else "native-restored-hunter"
        login = [
            {**packet("to_native", "CMSG_PLAYER_LOGIN", struct.pack("<Q", 6), start + .1), "session": session},
            {**packet("from_native", "SMSG_LOGIN_VERIFY_WORLD", b"", start + .2), "session": session},
        ]
        reload = pet_creation(session, start + .3)
        pet_packets = [reload["packet"], *reload["update_packets"]]
        entry = {"native_session": session, "started_at": start, "finished_at": start + 1,
                 "login_packets": login, "native_pet_reload": reload, "pet_reload_packets": pet_packets,
                 "learn_offline_baseline": snapshot()}
        known_body = struct.pack("<BH", 1, 2) + struct.pack("<IhIhH", 1515, 0, 79682, 0, 0)
        known_packet = {**packet("from_native", "SMSG_SEND_KNOWN_SPELLS", known_body, start + .25), "session": session}
        tracking["packets"].extend([*login, known_packet, *pet_packets])
        tracking["events"].append({"event": "instance_authenticated", "session": "physical" + str(index),
                                    "account_id": 2, "time": start + .05})
        known.append({"login_known_spell_ids": [1515, 79682], "native_known_spell_packet": {
            "ids": [1515, 79682], "body_sha256": hashlib.sha256(known_body).hexdigest(),
            "session": session, "time": known_packet["time"], "initial_login": 1}})
        entries.append(entry)
    high = (8 << 58) | (1 << 42) | (((contract.TRAINER_GUID >> 32) & 0xFFFFF) << 6)
    modern_body = Writer().guid(contract.TRAINER_GUID & 0xFFFFFFFF, high).pack("ii", 40, 1462).finish()
    modern = packet("from_client", "CMSG_TRAINER_BUY_SPELL", modern_body, 1011.9)
    purchases = [modern, *learn_packets()]
    purchase = {"native_session": SESSION, "purchase_packets": deepcopy(purchases)}
    tracking["packets"].extend(purchases)
    tracking["events"].extend({"session": SESSION if row["direction"] in ("to_native", "from_native") else "physical0",
                               "event": "native_packet" if row["direction"] in ("to_native", "from_native") else "modern_packet",
                               "name": row["name"], "direction": row["direction"],
                               "bytes": len(bytes.fromhex(row["body"])), "time": row["time"] - .00002}
                              for row in purchases)
    identity, trainer_packets = trainer_fixture(with_facing=True)
    purchase.update(trainer_identity=identity, native_catalog=identity['native_catalog'], runtime=identity['runtime'],
        entry_source=identity['entry_source'], trainer_identity_checked_at=1011.8, purchase_started_at=1011.8)
    tracking['packets'].extend(trainer_packets)
    tracking['events'].extend({'event': 'native_packet', 'session': SESSION, 'direction': row['direction'],
        'name': row['name'], 'bytes': len(bytes.fromhex(row['body'])), 'time': row['time'] - .00002}
        for row in trainer_packets)
    return purchase, entries, tracking, known


def test_actual_journals_bind_direct_delivery_to_two_fresh_owned_logins_and_modern_train():
    purchase, entries, tracking, known = actual_fixture()
    assert evidence.actual_packets(purchase, entries, tracking, known) == learn_packets()


def retarget_purchase_session(purchase, tracking, new_session):
    old = purchase["native_session"]
    names = {"CMSG_TRAINER_BUY_SPELL", "SMSG_LEARNED_SPELL", "SMSG_LEARNED_SPELLS"}
    purchase["native_session"] = new_session
    for row in [*purchase["purchase_packets"], *tracking["packets"]]:
        if row.get("session") == old and row.get("name") in names:
            row["session"] = new_session
    for row in tracking["events"]:
        if row.get("session") == old and row.get("name") in names:
            row["session"] = new_session


@pytest.mark.parametrize("fault", ["unlogged_purchase_session", "empty_instance", "missing_instance_id"])
def test_ownership_requires_purchase_on_the_entered_session_and_identifiable_physical_instances(fault):
    purchase, entries, tracking, known = actual_fixture()
    if fault == "unlogged_purchase_session":
        retarget_purchase_session(purchase, tracking, "third-session-without-owned-login")
    else:
        for row in tracking["events"]:
            if row.get("session") == "physical0":
                row["session"] = "" if fault == "empty_instance" else None
    with pytest.raises(RuntimeError):
        evidence.actual_packets(purchase, entries, tracking, known)


@pytest.mark.parametrize("fault", ["missing_journal", "missing_native", "second_learn", "second_modern",
                                  "wrong_modern_guid", "wrong_modern_spell", "modern_suffix", "late_modern",
                                  "cast", "pet_action", "missing_login", "missing_pet", "untrained_known",
                                  "known_duplicate", "forged_known_receipt", "wrong_pet_health", "pet_body_mismatch",
                                  "no_instance", "shared_instance", "wrong_account", "missing_metadata",
                                  "wrong_metadata_bytes", "foreign_metadata", "duplicate_metadata"])
def test_archive_claims_cannot_replace_owned_raw_packets_fresh_instances_and_metadata(fault):
    purchase, entries, tracking, known = actual_fixture()
    modern = next(row for row in tracking["packets"] if row["direction"] == "from_client")
    native = next(row for row in tracking["packets"] if row["name"] == "SMSG_LEARNED_SPELL")
    if fault == "missing_journal":
        tracking["members"].remove(evidence.TRACKING_MEMBERS[1])
    elif fault == "missing_native":
        tracking["packets"].remove(native)
    elif fault == "second_learn":
        tracking["packets"].append({**native, "session": entries[1]["native_session"], "time": 2010.5})
    elif fault == "second_modern":
        tracking["packets"].append({**modern, "time": modern["time"] + .01})
    elif fault in ("wrong_modern_guid", "wrong_modern_spell", "modern_suffix", "late_modern"):
        claimed = purchase["purchase_packets"][0]
        if fault == "late_modern":
            modern["time"] = 1012.01
        elif fault == "modern_suffix":
            modern["body"] += "00"
        else:
            high = (8 << 58) | (1 << 42) | (((contract.TRAINER_GUID >> 32) & 0xFFFFF) << 6)
            modern["body"] = Writer().guid((contract.TRAINER_GUID & 0xFFFFFFFF) + (fault == "wrong_modern_guid"), high).pack(
                "ii", 40, 1515 if fault == "wrong_modern_spell" else 1462).finish().hex()
        claimed.update(modern)
    elif fault in ("cast", "pet_action"):
        tracking["packets"].append(packet("to_native", "CMSG_CAST_SPELL" if fault == "cast" else "CMSG_PET_ACTION", b"", 1012.5))
    elif fault == "missing_login":
        tracking["packets"].remove(entries[0]["login_packets"][0])
    elif fault == "missing_pet":
        tracking["packets"].remove(entries[0]["native_pet_reload"]["packet"])
    elif fault in ("untrained_known", "known_duplicate"):
        row = next(row for row in tracking["packets"] if row["name"] == "SMSG_SEND_KNOWN_SPELLS")
        if fault == "known_duplicate":
            tracking["packets"].append(deepcopy(row))
        else:
            row["body"] = (struct.pack("<BH", 1, 3) + struct.pack("<IhIhIhH", 1515, 0, 79682, 0, 1462, 0, 0)).hex()
    elif fault == "forged_known_receipt":
        known[0]["native_known_spell_packet"]["body_sha256"] = "0" * 64
    elif fault == "wrong_pet_health":
        entries[0]["native_pet_reload"]["health"] = 0
    elif fault == "pet_body_mismatch":
        entries[0]["native_pet_reload"]["object"]["fields"]["26"] = 0
    elif fault == "no_instance":
        tracking["events"] = [row for row in tracking["events"] if row["event"] != "instance_authenticated"]
    elif fault == "shared_instance":
        tracking["events"][1]["session"] = tracking["events"][0]["session"]
    elif fault == "wrong_account":
        tracking["events"][0]["account_id"] = 1
    elif fault == "missing_metadata":
        tracking["events"].pop()
    elif fault == "wrong_metadata_bytes":
        tracking["events"][-1]["bytes"] += 1
    elif fault == "foreign_metadata":
        tracking["events"][-1]["session"] = "foreign"
    else:
        tracking["events"].append(deepcopy(tracking["events"][-1]))
    with pytest.raises((RuntimeError, ValueError)):
        evidence.actual_packets(purchase, entries, tracking, known)


def logout_fixture():
    park = {"completed": True, "failure": None, "phase": "await_original_selection_review",
            "started_at": 1020.0, "finished_at": 1021.0,
            "checks": {name: True for name in evidence.PARK_NAMES},
            "logout_packets": [packet("to_native", "CMSG_LOGOUT_REQUEST", b"", 1020.1),
                               packet("from_native", "SMSG_LOGOUT_COMPLETE", b"", 1020.2),
                               packet("to_client", "SMSG_LOGOUT_COMPLETE", b"\x00", 1020.3)]}
    return park, {"native_session": SESSION}


def test_logout_requires_installed_native_empty_and_modern_one_zero_byte_layouts():
    park, entry = logout_fixture()
    assert evidence.logout(park, entry) == park["logout_packets"]
    park["logout_packets"][-1]["body"] = ""
    with pytest.raises(RuntimeError, match="logout packets"):
        evidence.logout(park, entry)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "foreign", "late", "reversed", "request_body", "native_body"])
def test_logout_requires_one_owned_ordered_and_complete_ordinary_roundtrip(fault):
    park, entry = logout_fixture()
    rows = park["logout_packets"]
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif fault == "foreign":
        rows[-1]["session"] = "foreign"
    elif fault == "late":
        rows[-1]["time"] = 1021.1
    elif fault == "reversed":
        rows[-1]["time"] = 1020.15
    else:
        rows[0 if fault == "request_body" else 1]["body"] = "00"
    with pytest.raises(RuntimeError):
        evidence.logout(park, entry)


def closure_fixture():
    return {"schema": evidence.SCHEMA, "phase": evidence.PHASE, "completed": True,
            "failure": None, "started_at": 1, "finished_at": 2, "input_sent": False,
            "mutation_sent": False, "qualification_added": False, "actor": {"guid": 2},
            "primary_stop_source": {"path": "/synthetic/episode.json", "sha256": "a" * 64},
            "sources": {role: {"path": "/synthetic/" + role + "/episode.json", "sha256": "b" * 64} for role in evidence.ROLES},
            "checks": {name: True for name in evidence.CLOSURE_NAMES}, "all_offline_snapshot": snapshot(),
            "proof": {"operation": "spellbook.learn_spell", "owner": 6, "spell": 1462,
                      "native_purchases": 1, "native_learn_events": 1, "modern_learn_events": 1,
                      "cleanup_removed_spell": 1462, "cleanup_refund": 646,
                      "restored_untrained_reentry": True, "all_six_offline": True,
                      "primary_stopped": True, "qualification_added": False, "closure_checks": 28}}


def test_distinct_learning_closure_requires_all_28_checks_and_semantic_restoration():
    closure = closure_fixture()
    assert len(evidence.closure_checks(closure)) == 28


@pytest.mark.parametrize("fault", ["schema", "phase", "actor", "input", "qualification", "missing_role",
                                  "extra_role", "missing_check", "extra_check", "truthy_check", "truthy_proof",
                                  "wrong_refund", "saved_learned"])
def test_labeled_or_partial_closure_is_not_complete_semantic_proof(fault):
    closure = closure_fixture()
    if fault in ("schema", "phase"):
        closure[fault] = "another-operation"
    elif fault == "actor":
        closure["actor"]["guid"] = 6
    elif fault in ("input", "qualification"):
        closure["input_sent" if fault == "input" else "qualification_added"] = True
    elif fault == "missing_role":
        closure["sources"].pop("cleaned")
    elif fault == "extra_role":
        closure["sources"]["borrowed_cast"] = {}
    elif fault == "missing_check":
        closure["checks"].pop("exact_offline_cleanup")
    elif fault == "extra_check":
        closure["checks"]["invented"] = True
    elif fault == "truthy_check":
        closure["checks"]["exact_offline_cleanup"] = 1
    elif fault == "truthy_proof":
        closure["proof"]["native_purchases"] = True
    elif fault == "wrong_refund":
        closure["proof"]["cleanup_refund"] = 680
    else:
        closure["all_offline_snapshot"]["6"]["saved"]["spells"].append([1462, 1, 0])
    with pytest.raises(RuntimeError):
        evidence.closure_checks(closure)


def lifecycle_fixture(monkeypatch, automatic_bar=False, settled_cleanup=False, trainer_exposed=False, settled_purchase=False):
    """Build closed synthetic source bytes; never borrow a live episode or archive."""
    data, digests, payloads, refs = {}, {}, {}, {}
    runtime = {"client": {"pid": 123, "instance": "fresh-scout"}, "native": {"pid": 321},
               "worldserver": deepcopy(trainer_evidence.NATIVE)}
    previous_runtime = {**runtime, "client": {"pid": 122, "instance": "stopped-scout"}}
    origin = {"guid": 2, "character_name": "Harnesstwo"}
    actor = {"guid": 6, "account_id": 2, "character_name": "Harnesshunt", "race": 1, "class": 3, "level": 10}
    base = snapshot()
    if settled_purchase:
        base['6']['saved']['actions'] = deepcopy(reconciliation.ACTIONS)
    purchase, entries, tracking, known = actual_fixture(same_owner=True)
    first_exact, first_text = native_rest(100.0, 10, 7600, 1)
    parked = learned_snapshot(base)
    parked["6"]["native"].update(rest_bonus=first_text, totaltime=105, leveltime=105, logout_time=1020)
    parked["6"]["pets"][1]["savetime"] = 201
    cleaned = contract.cleanup_expected(base, parked)
    final_exact, final_text = native_rest(first_exact, 990, 7600, 1)
    final = deepcopy(cleaned)
    final["6"]["native"].update(rest_bonus=final_text, totaltime=110, leveltime=110, logout_time=2020)
    final["6"]["pets"][1]["savetime"] = 202

    def put(name, value, filename="episode.json"):
        member = "evidence/synthetic/" + name + "/" + filename
        body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        payloads[member] = body
        data[member] = json.loads(body)
        digests[member] = hashlib.sha256(body).hexdigest()
        refs[name] = {"path": str(evidence.lab.ROOT / member), "sha256": digests[member]}
        return refs[name]

    spawn_member = str(Path(trainer_evidence.SPAWN_SOURCE['path']).relative_to(evidence.lab.ROOT))
    data[spawn_member] = json.loads(SPAWN_BYTES)
    payloads[spawn_member] = SPAWN_BYTES
    digests[spawn_member] = hashlib.sha256(SPAWN_BYTES).hexdigest()
    refs['trainer_spawn'] = deepcopy(trainer_evidence.SPAWN_SOURCE)

    def episode(phase, start, finish, who=None, **fields):
        return {"completed": True, "failure": None, "phase": phase, "started_at": start,
                "finished_at": finish, "runtime": runtime, "actor": actor if who is None else who,
                "native_session": SESSION,
                "qualification_added": False, "controller": "code", "model": None,
                "custom_script_permission": "blocked_by_user",
                "softTargetInteract": {"original": "0", "current_stock_disabled": "1", "original_restored": False}, **fields}

    def checkset(names):
        return {name: True for name in names}

    def frame_for(name):
        png_name = name + ".png"
        png_member = "evidence/synthetic/screens/" + png_name
        png = png_bytes(name)
        payloads[png_member], digests[png_member] = png, hashlib.sha256(png).hexdigest()
        return {"file": png_name, "sha256": digests[png_member], "monitor": {
            "second_monitor_verified": True, "monitor": {"name": "HDMI-1"}, "pid": 123,
            "input_isolation": {"actor": "scout", "host_activation_sent": False}}}

    def screen(name, source, fixture, control, **extra):
        frame = frame_for(name)
        value = {"reviewed": True, "control": control, "frame": frame,
                 "fixture_source_sha256": fixture["sha256"], "source": source, **extra}
        if control == "Harnesstwo":
            value.update(selected_character="Harnesstwo", selected_level=1)
        ref = put(name + "_screen", value, "review.json")
        return {**ref, "frame": frame}

    bindings = {"rate": 1, "formula_snippets": evidence.FORMULA_SNIPPETS,
                "config_source": {"path": str(evidence.lab.ROOT / "config/worldserver.conf"), "sha256": evidence.REST_CONFIG_SHA256},
                "native_formula_source": {"path": str(evidence.lab.REPO / evidence.FORMULA_SOURCE), "sha256": evidence.REST_FORMULA_SHA256},
                "native_float_storage_sources": [{"path": str(evidence.lab.REPO / path), "sha256": sha}
                                                  for path, sha in evidence.FLOAT_SOURCES.items()]}

    def exact_source(name, source, state, exact, start):
        return put(name, episode("hunter_learn_rest_precision_complete", start, start + .1,
                   query=preservation.PRECISION_QUERY, source=source, before=state, after=state,
                   input_sent=False, mutation_sent=False, row=precision_row(state["6"]["native"], exact),
                   checks=checkset(evidence.PRECISION_NAMES), rest_sources=bindings))

    put("primary_stop", episode("user_requested_primary_client_stopped", 100, 101, origin,
                               before=base["1"], after=base["1"], checks=checkset(range(8))))
    put("previous_preparation", episode("await_owned_class_lobby_review", 200, 201, origin))
    put("previous_normalized", episode("owned_revive_fixture_normalized", 300, 301, after=base))
    put("previous_closure", episode("owned_revive_parked_boundary", 400, 401, origin,
                                    checks=checkset(range(21)), all_offline_snapshot=base,
                                    primary_stop_source=refs["primary_stop"]))
    put("previous_pause", episode("parked_scout_resource_paused", 500, 501, origin,
                                  runtime=previous_runtime, checks=checkset(range(8)), before=base, after=base,
                                  source=refs["previous_closure"]))
    previous = [refs[name] for name in ("previous_preparation", "previous_normalized", "previous_closure", "previous_pause")]
    put("previous_checkpoint", {"file": sources.POINTER[:-4], "sha256": sources.ARCHIVE_SHA256,
        "bytes": sources.ARCHIVE_BYTES, "cloud_verified": True, "file_manifest": [
            {"path": str(Path(ref["path"]).relative_to(evidence.lab.ROOT)), "sha256": ref["sha256"]} for ref in previous]}, "checkpoint.json")
    put("previous_remote", {"actual_remote_verified": True, "complete_json_png_verified": True,
        "pointer": sources.POINTER, "archive_sha256": sources.ARCHIVE_SHA256, "bytes": sources.ARCHIVE_BYTES,
        "proof": {"operation": "pets.revive", "qualification_added": False}}, "remote.json")
    monkeypatch.setattr(evidence, "REMOTE_SHA256", refs["previous_remote"]["sha256"])
    monkeypatch.setattr(evidence, "CHECKPOINT_SHA256", refs["previous_checkpoint"]["sha256"])
    ancestry = []
    for name in ("primary_stop", "previous_preparation", "previous_normalized", "previous_closure",
                 "previous_pause", "previous_checkpoint", "previous_remote", "trainer_spawn"):
        original = str(Path(refs[name]["path"]).relative_to(evidence.lab.ROOT))
        copy = "evidence/synthetic/ancestry/" + refs[name]["sha256"] + ".json"
        ancestry.append({"original_path": refs[name]["path"], "sha256": refs[name]["sha256"],
                         "copy_path": str(evidence.lab.ROOT / copy), "bytes": len(payloads[original])})
        data[copy], payloads[copy], digests[copy] = data.pop(original), payloads.pop(original), digests.pop(original)
    put("ancestry", {"schema": "client442_hunter_learn_ancestry_v1", "sources": ancestry}, "manifest.json")
    put("scout_restored", episode("hunter_learn_scout_original_restored", 610, 611, origin, checks=checkset(range(3))))
    put("resume", episode("hunter_learn_scout_resumed", 600, 620, origin,
        schema="client442_hunter_learn_scout_resume_v1", checks=checkset(range(7)), sources=previous,
        remote_source=refs["previous_remote"], primary_stop_source=refs["primary_stop"], offline_baselines=base,
        restoration_source=refs["scout_restored"], previous_runtime=previous_runtime, launch_finished_at=609,
        checkpoint_source=refs["previous_checkpoint"]))
    put("preparation", episode("await_owned_class_lobby_review", 1001, 1001.1, origin,
        origin_actor=origin, class_actor=actor, learn_offline_baseline=base, accepted_previous_sources=previous,
        remote_source=refs["previous_remote"], primary_stop_source=refs["primary_stop"],
        sources=[refs["resume"], refs["scout_restored"]]))
    exact_source("initial_precision", refs["preparation"], base, 100.0, 1002)

    def entered(index, baseline, precise, preparation):
        value = entries[index]
        exact_after = first_exact if index == 0 else final_exact
        return put("entry" + str(index), episode("owned_class_entered", value["started_at"], value["finished_at"],
            **{key: val for key, val in value.items() if key not in ("started_at", "finished_at", "learn_offline_baseline")},
            learn_offline_baseline=baseline,
            fixture_source=preparation, rest_baseline_source=precise,
            native_before_entry=baseline["6"]["native"], entered_native={**baseline["6"]["native"], "online": 1},
            state={"player": "Harnesshunt", "level": 10, "xp": 45, "xp_max": 7600, "xp_exhaustion": 2 * int(exact_after)}))

    entered(0, base, refs["initial_precision"], refs["preparation"])
    spell = [1462, 65536, 132096] + [0] * 45
    prerequisite = {"dbc_hashes": contract.DBC_HASHES, "spell": [spell], "effects": [contract.EFFECT],
                    "abilities": [contract.ABILITY], "matching_criteria": [], "trainer": [contract.TRAINER_ROW],
                    "lesson": [[40, 1462, 680, 0, 0, 0, 0, 0, 10]],
                    "relations": {name: [] for name in ("learn", "required", "pet", "linked")}}
    prerequisite["sha256"] = contract.fingerprint(prerequisite)
    baseline = {"snapshot": base, "saved": base["6"]["saved"], "resources": resource_observation(contract.MONEY),
                "entry_source": refs["entry0"], "rest_baseline_source": refs["initial_precision"],
                "native_pet_reload": entries[0]["native_pet_reload"], "active_spec": 0, "prerequisite_fingerprint": prerequisite}
    future, learned = book(False), book(True)
    put("untrained", episode("hunter_learn_untrained_reconciled", 1011.1, 1011.15,
        baseline=baseline, entry_source=refs["entry0"], future_probe=future, future_row=future["rows"][0], **known[0]))
    put("staged", episode("hunter_learn_trainer_staged", 1011.2, 1011.25, source=refs["untrained"], frame=frame_for("trainer")))
    identity, _ = trainer_fixture(runtime=runtime, entry_ref=refs['entry0'], with_facing=True)
    catalog = identity['native_catalog']
    purchase.update(trainer_identity=identity, native_catalog=catalog, runtime=runtime, entry_source=refs['entry0'])
    opened = episode("hunter_learn_trainer_open", 1011.3, 1011.35, source=refs["staged"], native_catalog=catalog,
        trainer_identity=identity, state={'target': identity['target']},
        fixture_source=refs["preparation"], entry_source=refs["entry0"], baseline=baseline,
        login_known_spell_ids=known[0]["login_known_spell_ids"], frame=frame_for("lesson"),
        screen_review=screen("trainer", refs["staged"], refs["preparation"], "Benjamin Foxworthy"))
    put("opened", opened)
    trainer_view, lesson_frame = refs["opened"], "lesson"
    if trainer_exposed:
        exposed = {**opened, "phase": "hunter_learn_trainer_exposed", "started_at": 1011.36,
                   "finished_at": 1011.38, "source": refs["opened"], "frame": frame_for("exposed_lesson")}
        put("exposed", exposed)
        trainer_view, lesson_frame = refs["exposed"], "exposed_lesson"
    layout = {"book_type": "spell", "skill_line": 1, "pages": [1], "page": 1}
    put("selected", episode("hunter_learn_lesson_selected", 1011.4, 1011.45, source=trainer_view, native_catalog=catalog,
        trainer_identity=identity, entry_source=refs['entry0'],
        baseline=baseline, login_known_spell_ids=known[0]['login_known_spell_ids'], book_layout_baseline=layout,
        fixture_source=refs['preparation'],
        controller='code_diagnostic_ordinary_inputs' if settled_purchase else 'code',
        state={"trainer": {"service": {"name": "Beast Lore"}}, 'target': identity['target']}, frame=frame_for("train"),
        screen_review=screen(lesson_frame, trainer_view, refs["preparation"], "Beast Lore")))
    public = {"active_spec": 1, "frames": {"MainMenuBar": True}, "actions": [
        {"button": "ActionButton" + str(index), "slot": index, "kind": None, "id": None, "visible": True} for index in range(1, 13)]}
    if settled_purchase:
        public.update(power=100, power_type=2)
        for slot, ident, kind in ((0, 3044, 'spell'), (9, 59752, 'spell'), (10, 9, 'flyout'), (11, 982, 'spell')):
            public['actions'][slot].update(kind=kind, id=ident)
    purchase_saved, learned_public, addition = deepcopy(parked["6"]["saved"]), deepcopy(public), None
    if automatic_bar:
        purchase_saved["actions"] = [[0, 0, 1462, 0]]
        learned_public["actions"][0].update(kind="spell", id=1462)
        action_packets = [packet("from_client", "CMSG_SET_ACTION_BUTTON", struct.pack("<IB", 1462, 0), 1012.22),
                          packet("to_native", "CMSG_SET_ACTION_BUTTON", struct.pack("<BI", 0, 1462), 1012.23)]
        purchase["purchase_packets"].extend(action_packets)
        tracking["packets"].extend(action_packets)
        addition = evidence.addition_guard([], purchase_saved["actions"], purchase["purchase_packets"],
                                          SESSION, 1011.8, 1012.3, 0, learned_public)
    purchase_value = episode("hunter_learn_transition_complete", 1011.8, 1013,
        **{k: v for k, v in purchase.items() if k not in ('runtime', 'entry_source', 'purchase_started_at')},
        baseline=baseline, entry_source=refs["entry0"], purchase_source=refs["selected"], source=refs['selected'],
        purchase_started_at=1011.8, purchase_finished_at=1012.3, after_saved=purchase_saved,
        state={'target': identity['target']},
        after_resources=resource_observation(contract.MONEY - contract.PRICE),
        learned_probe=learned, learned_row=learned["rows"][0], **known[0],
        reconciled_known_spell_ids=[1462, 1515, 79682], purchase_checks=checkset(evidence.PURCHASE_NAMES),
        purchase_input_sent=True, input_sent=True, auto_action_placement=addition,
        actionbar_restoration_required=automatic_bar, public_actionbar_after=learned_public, book_layout_baseline=layout,
        screen_review=screen("train", refs["selected"], refs["preparation"], "Train"))
    if settled_purchase:
        success = packet('from_native', 'SMSG_TRAINER_BUY_SUCCEEDED', struct.pack('<QI', contract.TRAINER_GUID, 1462), 1012.21)
        purchase_value['purchase_packets'].append(success)
        tracking['packets'].append(success)
        purchase_value.update(fixture_source=refs['preparation'], controller='code_diagnostic_ordinary_inputs')
        purchase_value['state'].update(player='Harnesshunt', level=10, money=8062, guid='Player-1-00000006',
            world_position=[-9464.400390625, 120.40000152588, 0, 0], player_stats={'health': 209})
        purchase_value['frame'] = frame_for('reconciliation_current')
        purchase_value['frame']['movement'] = {'health_percent': 100, 'dead': False, 'in_combat': False, 'speed': 0}
        failure = deepcopy(purchase_value)
        failure.update(phase='hunter_learn_purchase_started', completed=False, failure=reconciliation.FAILURE,
            purchase_checks=None, cases=[failed_case(identity['target'])], protected_checks=deepcopy(reconciliation.PROTECTED))
        for key in ('learned_probe', 'learned_row', 'reconciled_known_spell_ids'):
            failure.pop(key)
        put('failed_purchase', failure)
        monkeypatch.setattr(reconciliation, 'FAILED_SOURCE', refs['failed_purchase'])
        selected = data[str(Path(refs['selected']['path']).relative_to(evidence.lab.ROOT))]
        current_state = purchase_value['state']
        proof = reconciliation.observation_reconciliation(failure, refs['failed_purchase'], selected, refs['selected'],
            saved=purchase_saved, resources=purchase_value['after_resources'], protected_checks=reconciliation.PROTECTED,
            public=learned_public, state=current_state, frame=purchase_value['frame'], rows=tracking['packets'], observed_until=1013.8)
        purchase_value.update(started_at=1013.1, finished_at=1013.9, observation_settlement_source=refs['failed_purchase'],
            original_purchase_interval=[1011.8, 1012.3], original_case=deepcopy(failure['cases'][0]),
            original_purchase_input_sent=True, purchase_input_sent=False, input_sent=True, gameplay_input_sent=False,
            train_input_replayed=False,
            book_navigation_input_sent=True, observation_only=True, mutation_sent=False,
            observation_reconciliation=proof, protected_checks=deepcopy(reconciliation.PROTECTED),
            cases=[navigation_case()])
    put('purchase', purchase_value)
    if automatic_bar:
        clear_packets = [packet("from_client", "CMSG_SET_ACTION_BUTTON", struct.pack("<IB", 0, 0), 1013.2),
                         packet("to_native", "CMSG_SET_ACTION_BUTTON", struct.pack("<BI", 0, 0), 1013.21)]
        tracking["packets"].extend(clear_packets)
        clear = evidence.clear_guard(addition, [], clear_packets, SESSION, 1013.2, 1013.21, public)
        put("bar_capture", episode("hunter_learn_auto_action_capture_complete", 1013.02, 1013.05,
            frame=frame_for("bar"), source=refs["purchase"]))
        reviewed = screen("bar", refs["bar_capture"], refs["preparation"], "ActionButton1", point=[100, 100], empty_point=[200, 100])
        review_ref = {key: reviewed[key] for key in ("path", "sha256")}
        put("bars", episode("hunter_learn_auto_action_restored", 1013.1, 1013.9,
            source=refs["purchase"], purchase_source=refs["purchase"], auto_action_placement=addition,
            before_saved=purchase_saved, after_saved=parked["6"]["saved"],
            before_resources=resource_observation(contract.MONEY - contract.PRICE),
            after_resources=resource_observation(contract.MONEY - contract.PRICE), native_session=SESSION,
            clear_packets=clear_packets, clear_started_at=1013.2, clear_finished_at=1013.21,
            public_after=public, public_after_clear=public, clear_proof=clear,
            clear_request_proof={key: clear[key] for key in ("modern", "native", "button")},
            actionbar_restored=True, stock_pickup_sources=[evidence.PICKUP_SOURCE, evidence.BINDING_SOURCE],
            cursor_before_clear=None, cursor_before_cancel=["spell", 7, "spell", 1462], cursor_after_cancel=None,
            restoration_checks=checkset(range(12)), screen_review=reviewed, capture_source=refs["bar_capture"],
            bar_restore_input={"kind": "shift_drag", "slot0": 0, "spell": 1462, "source": review_ref,
                               "start": [100, 100], "end": [200, 100], "reviewed_frame": reviewed["frame"]},
            cursor_cancel_input={"kind": "click", "button": 3, "value": [200, 100], "source": review_ref},
            geometry_proof={"exact_pixels": True}, input_sent=True, clear_input_sent=True))
    pose = [base["6"]["native"][key] for key in preservation.POSE_KEYS]
    put("restoration", episode("hunter_learn_online_restored", 1014, 1015,
        purchase_source=refs["purchase"], book_layout_restored=layout,
        **({"action_cleanup_source": refs["bars"]} if automatic_bar else {}),
        pose_restoration={"restored": pose, "fixture": {"before": pose, "rows": [[77]]}, "removed": [77], "checks": {"pose": True}}))

    def parking(name, start, source, entry, state):
        logout = [packet("to_native", "CMSG_LOGOUT_REQUEST", b"", start + .1),
                  packet("from_native", "SMSG_LOGOUT_COMPLETE", b"", start + .2),
                  packet("to_client", "SMSG_LOGOUT_COMPLETE", b"\x00", start + .3)]
        tracking["packets"].extend(logout)
        return put(name, episode("await_original_selection_review", start, start + 1,
            source=source, entry_source=entry, all_offline_snapshot=state, logout_packets=logout, checks=checkset(evidence.PARK_NAMES)))

    parking("first_park", 1020, refs["restoration"], refs["entry0"], parked)
    exact_source("first_precision", refs["first_park"], parked, first_exact, 1022)
    cleanup = episode("hunter_learn_offline_cleaned", 1024, 1025,
        before=parked, after=cleaned, expected_after=cleaned, input_sent=False, mutation_sent=True,
        preparation_source=refs["preparation"], purchase_source=refs["purchase"], restoration_source=refs["restoration"],
        park_source=refs["first_park"], precision_source=refs["first_precision"], creator_normalization_source=None,
        removed_spell=1462, refunded_copper=646, checks=checkset(evidence.CLEAN_NAMES))
    if settled_cleanup:
        failed = {**cleanup, "phase": "hunter_learn_offline_cleanup_started", "completed": False,
                  "failure": "synthetic: commit completed before receipt write failed", "commit_attempted": True,
                  "started_at": 1023.1, "finished_at": 1023.9}
        put("failed_cleanup", failed)
        cleanup.update(settled_commit_only=True, cleanup_failed_source=refs["failed_cleanup"], mutation_sent=False,
                       original_mutation_sent=True, transaction_committed=True, commit_attempted=False,
                       sources=failed.get("sources", []) + [refs["failed_cleanup"]])
    put("cleaned", cleanup)
    put("original_finish", episode("original_selection_restored", 1026, 1027, origin,
        fixture_source=refs["preparation"], checks=checkset(range(5)),
        screen_review=screen("first_selection", None, refs["preparation"], "Harnesstwo")))
    put("reentry_preparation", episode("await_owned_class_lobby_review", 1028, 1029, origin,
        learning_reentry_only=True, learn_offline_baseline=cleaned, cleaned_source=refs["cleaned"],
        previous_preparation_source=refs["preparation"], original_finish_source=refs["original_finish"]))
    exact_source("second_precision", refs["reentry_preparation"], cleaned, first_exact, 1030)
    entered(1, cleaned, refs["second_precision"], refs["reentry_preparation"])
    put("reentry", episode("hunter_learn_reentry_verified", 2012, 2013,
        entry_source=refs["entry1"], cleaned_source=refs["cleaned"],
        baseline={"snapshot": cleaned, "saved": cleaned["6"]["saved"], "resources": resource_observation(contract.MONEY), "prerequisite_fingerprint": prerequisite},
        **known[1], future_probe=future, future_row=future["rows"][0], checks=checkset(evidence.REENTRY_NAMES)))
    parking("final_park", 2020, refs["reentry"], refs["entry1"], final)
    exact_source("final_precision", refs["final_park"], final, final_exact, 2022)
    put("finish", episode("original_selection_restored", 2024, 2025, origin,
        fixture_source=refs["reentry_preparation"], checks=checkset(range(5)),
        qualified_scope="Original parked character, saved rows and selected identity restored; synthetic evidence",
        screen_review=screen("final_selection", None, refs["reentry_preparation"], "Harnesstwo")))
    roles = {role: refs[role] for role in evidence.ROLES}
    result, after, _ = evidence.lifecycle(evidence.Sources(data, digests), roles)
    put("closure", episode(evidence.PHASE, 2026, 2027, origin, schema=evidence.SCHEMA,
        input_sent=False, mutation_sent=False, sources=roles, primary_stop_source=refs["primary_stop"],
        all_offline_snapshot=after, proof=result, checks=checkset(evidence.CLOSURE_NAMES)))
    put("pause", episode("hunter_learn_scout_resource_paused", 2028, 2029, origin,
        source=refs["closure"], primary_stop_source=refs["primary_stop"], before=after, after=after,
        input_sent=False, checks=checkset(evidence.PAUSE_NAMES),
        action="stop_parked_scout_after_learning_restoration", game_before={"pid": 123, "start_ticks": "456"}))
    tracking["digests"] = digests
    tracking["manifest"] = {member: {"bytes": len(body), "sha256": digests[member]} for member, body in payloads.items()}
    return data, digests, tracking, payloads, refs


@pytest.mark.parametrize("automatic_bar", [False, True])
def test_whole_lifecycle_and_actual_journals_prove_learning_cleanup_and_untrained_reentry(monkeypatch, automatic_bar):
    data, digests, tracking, _, _ = lifecycle_fixture(monkeypatch, automatic_bar=automatic_bar)
    proof = evidence.proof(data, digests, tracking)
    assert proof["operation"] == "spellbook.learn_spell"
    assert proof["native_purchases"] == proof["native_learn_events"] == proof["modern_learn_events"] == 1
    assert proof["cleanup_removed_spell"] == 1462 and proof["cleanup_refund"] == 646
    assert proof["ordinary_login_count"] == proof["ordinary_logout_count"] == 2
    assert proof["all_six_offline"] and proof["both_owned_clients_stopped"]
    assert proof["qualification_added"] is False


@pytest.mark.parametrize("automatic_bar", [False, True])
def test_whole_lifecycle_streams_from_verified_archive_bytes_without_receipt_shortcuts(monkeypatch, automatic_bar):
    _, _, tracking, payloads, _ = lifecycle_fixture(monkeypatch, automatic_bar=automatic_bar)
    members = list(payloads.items()) + [
        (evidence.TRACKING_MEMBERS[0], b"".join(json.dumps(row).encode() + b"\n" for row in tracking["packets"])),
        (evidence.TRACKING_MEMBERS[1], b"".join(json.dumps(row).encode() + b"\n" for row in tracking["events"])),
    ]
    compressed, checkpoint, _ = archive_fixture(members)
    data, digests, journals, _ = reviewer.inspect_archive(io.BytesIO(compressed), checkpoint, "evidence/synthetic/")
    assert evidence.proof(data, digests, journals)["actual_packet_journals_verified"] is True


def test_source_specific_observation_reconciliation_proves_whole_lifecycle_and_complete_archive(monkeypatch):
    data, digests, tracking, payloads, refs = lifecycle_fixture(monkeypatch, settled_purchase=True)
    assert evidence.proof(data, digests, tracking)['native_purchases'] == 1
    store = evidence.Sources(data, digests)
    failed, current = store.get(refs['failed_purchase'], False), store.get(refs['purchase'])
    assert failed['completed'] is False and failed['cases'][0]['status'] == 'infrastructure_failure'
    assert current['started_at'] > current['purchase_finished_at']
    members = list(payloads.items()) + [
        (evidence.TRACKING_MEMBERS[0], b''.join(json.dumps(row).encode() + b'\n' for row in tracking['packets'])),
        (evidence.TRACKING_MEMBERS[1], b''.join(json.dumps(row).encode() + b'\n' for row in tracking['events'])),
    ]
    compressed, checkpoint, _ = archive_fixture(members)
    archived, hashes, journals, _ = reviewer.inspect_archive(io.BytesIO(compressed), checkpoint, 'evidence/synthetic/')
    assert evidence.proof(archived, hashes, journals)['actual_packet_journals_verified'] is True


@pytest.mark.parametrize('forbidden', [None, 'CMSG_CAST_SPELL', 'CMSG_PET_ACTION', 'CMSG_SET_ACTION_BUTTON'])
def test_native_authority_filter_preserves_gameplay_requests_among_discarded_modern_object_duplicates(monkeypatch, forbidden):
    _, _, tracking, payloads, _ = lifecycle_fixture(monkeypatch, settled_purchase=True)
    modern_duplicates = [packet('to_client', 'SMSG_UPDATE_OBJECT', b'not-native-object-wire', 1013.6)] * 20001
    rows = [*tracking['packets'], *modern_duplicates]
    if forbidden:
        rows.append(packet('to_native', forbidden, b'\0', 1013.7))
    members = list(payloads.items()) + [
        (evidence.TRACKING_MEMBERS[0], b''.join(json.dumps(row).encode() + b'\n' for row in rows)),
        (evidence.TRACKING_MEMBERS[1], b''.join(json.dumps(row).encode() + b'\n' for row in tracking['events'])),
    ]
    compressed, checkpoint, _ = archive_fixture(members)
    data, digests, journals, _ = reviewer.inspect_archive(io.BytesIO(compressed), checkpoint, 'evidence/synthetic/')
    assert not any(p['name'] == 'SMSG_UPDATE_OBJECT' and p['direction'] == 'to_client' for p in journals['packets'])
    assert any(p['name'] == 'SMSG_UPDATE_OBJECT' and p['direction'] == 'from_native' for p in journals['packets'])
    if forbidden:
        assert any(p['name'] == forbidden and p['direction'] == 'to_native' for p in journals['packets'])
        with pytest.raises(RuntimeError):
            evidence.proof(data, digests, journals)
    else:
        assert evidence.proof(data, digests, journals)['actual_packet_journals_verified'] is True


def test_native_authority_filter_keeps_staging_teleports_and_other_protocol_directions(monkeypatch):
    data, digests, _, _, _ = lifecycle_fixture(monkeypatch)
    authority = evidence.NATIVE_AUTHORITY_NAMES
    retained = ('MSG_MOVE_TELEPORT', 'SMSG_MOVE_TELEPORT', 'CMSG_MOVE_TELEPORT_ACK', 'MSG_MOVE_TELEPORT_ACK',
        'SMSG_TRANSFER_PENDING', 'SMSG_NEW_WORLD', 'CMSG_WORLD_PORT_RESPONSE', 'MSG_MOVE_WORLDPORT_ACK',
        'SMSG_UPDATE_ACTION_BUTTONS', 'CMSG_TRAINER_BUY_SPELL', 'SMSG_LEARNED_SPELLS', 'SMSG_SEND_KNOWN_SPELLS',
        'CMSG_PLAYER_LOGIN', 'CMSG_LOGOUT_REQUEST', 'CMSG_SET_ACTION_BUTTON', 'CMSG_CAST_SPELL')
    rows = [packet(direction, name, b'', 1013.6) for name in (*authority, *retained)
        for direction in ('from_native', 'to_native', 'from_client', 'to_client')]
    journals = {**evidence.tracking_state(), 'digests': digests}
    for member in evidence.TRACKING_MEMBERS:
        evidence.collect(member, iter(rows), data, journals)
    expected = [p for p in rows if p['name'] not in authority or p['direction'] == 'from_native']
    assert journals['packets'] == journals['events'] == expected


@pytest.mark.parametrize('fault', ['missing_failed', 'changed_failed_source', 'rewritten_failure', 'fake_train',
    'native_later_cast', 'native_before_purchase_cast', 'claimed_proof', 'lost_extended_native', 'controller', 'missing_gameplay_flag'])
def test_whole_observation_reconciliation_refuses_missing_or_changed_original_facts(monkeypatch, fault):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch, settled_purchase=True)
    store = evidence.Sources(data, digests)
    purchase = store.get(refs['purchase'])
    if fault == 'missing_failed':
        data.pop(str(Path(refs['failed_purchase']['path']).relative_to(evidence.lab.ROOT)))
    elif fault == 'changed_failed_source': purchase['observation_settlement_source']['sha256'] = 'f' * 64
    elif fault == 'rewritten_failure': store.get(refs['failed_purchase'], False)['failure'] = 'different failure'
    elif fault == 'fake_train': purchase['cases'].append({'id': 'spellbook.learn_spell.train1462', 'status': 'hunter_learning_pass'})
    elif fault in ('native_later_cast', 'native_before_purchase_cast'):
        tracking['packets'].append(packet('to_native', 'CMSG_CAST_SPELL', b'\0', 1013.7 if fault == 'native_later_cast' else 1011.7))
    elif fault == 'claimed_proof': purchase['observation_reconciliation']['original_case']['status'] = 'hunter_learning_pass'
    elif fault == 'lost_extended_native': purchase['observation_reconciliation']['trainer_wire_packets'].pop(1)
    elif fault == 'controller': purchase['controller'] = 'code'
    else: purchase.pop('gameplay_input_sent')
    with pytest.raises((RuntimeError, ValueError)):
        evidence.proof(data, digests, tracking)


@pytest.mark.parametrize('controller', ['code', 'code_diagnostic_ordinary_inputs'])
def test_whole_pause_uses_the_actual_ordinary_trial_controller_without_rewriting_sources(monkeypatch, controller):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch)
    evidence.Sources(data, digests).get(refs['pause'])['controller'] = controller
    assert evidence.proof(data, digests, tracking)['both_owned_clients_stopped'] is True


@pytest.mark.parametrize('ticks', [456, 456.0, True, None, '', '0', '0456', '+456', '-456', '456.0', 'nan'])
def test_whole_pause_refuses_noncanonical_process_start_ticks(monkeypatch, ticks):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch)
    evidence.Sources(data, digests).get(refs['pause'])['game_before']['start_ticks'] = ticks
    with pytest.raises(RuntimeError, match='canonical decimal start ticks'):
        evidence.proof(data, digests, tracking)


def test_whole_pause_preserves_actual_decimal_string_process_lifetime(monkeypatch):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch)
    pause = evidence.Sources(data, digests).get(refs['pause'])
    assert pause['game_before'] == {'pid': 123, 'start_ticks': '456'}
    assert evidence.proof(data, digests, tracking)['both_owned_clients_stopped'] is True
    assert pause['game_before']['start_ticks'] == '456'


@pytest.mark.parametrize("fault", ["missing_clear", "altered_bar_restore", "missing_actual_action", "unreviewed_drag",
                                  "geometry", "cursor_not_canceled", "wrong_cursor_spell", "unrelated_action"])
def test_automatic_placement_requires_the_complete_original_bar_and_reviewed_ordinary_clear(monkeypatch, fault):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch, automatic_bar=True)
    bars = evidence.Sources(data, digests).get(refs["bars"])
    if fault == "missing_clear":
        bars["clear_packets"].pop()
    elif fault == "altered_bar_restore":
        bars["after_saved"]["actions"].append([0, 1, 1515, 0])
    elif fault == "missing_actual_action":
        tracking["packets"] = [row for row in tracking["packets"] if not (
            row["name"] == "CMSG_SET_ACTION_BUTTON" and row["direction"] == "to_native" and row["time"] == 1013.21)]
    elif fault == "unreviewed_drag":
        bars["bar_restore_input"]["start"] = [101, 100]
    elif fault == "geometry":
        bars["geometry_proof"]["exact_pixels"] = False
    elif fault == "cursor_not_canceled":
        bars["cursor_after_cancel"] = ["spell", 1462]
    elif fault == "wrong_cursor_spell":
        bars["cursor_before_cancel"] = ["spell", 7, "spell", 1515]
    else:
        tracking["packets"].append(packet("to_native", "CMSG_SET_ACTION_BUTTON", struct.pack("<BI", 1, 1515), 1013.3))
    with pytest.raises(RuntimeError):
        evidence.proof(data, digests, tracking)


def test_readonly_cleanup_settlement_requires_the_same_attempted_committed_transaction(monkeypatch):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch, settled_cleanup=True)
    assert evidence.proof(data, digests, tracking)["cleanup_refund"] == 646
    failed = evidence.Sources(data, digests).get(refs["failed_cleanup"], False)
    failed["commit_attempted"] = False
    with pytest.raises(RuntimeError, match="settlement"):
        evidence.proof(data, digests, tracking)


@pytest.mark.parametrize('fault', ['missing_creation', 'missing_catalog', 'missing_creation_metadata',
    'missing_catalog_metadata', 'creation_body', 'hidden_movement', 'hidden_transport_movement',
    'hidden_destroy', 'hidden_remove', 'hidden_recreate', 'hidden_dead', 'hidden_nontrainer', 'hidden_petnumber', 'hidden_teleport',
    'changed_selected_proof', 'changed_purchase_proof', 'changed_public_target', 'changed_check_time',
    'changed_creation_claim', 'changed_unique_spawn', 'missing_unique_spawn'])
def test_whole_proof_requires_pinned_source_and_actual_current_trainer_packets(monkeypatch, fault):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch)
    store = evidence.Sources(data, digests)
    purchase = store.get(refs['purchase'])
    identity = purchase['trainer_identity']
    creation = identity['creation']['packet']
    catalog = identity['native_catalog']['packet']
    key = evidence.packet_key
    if fault in ('missing_creation', 'missing_catalog'):
        removed = creation if fault == 'missing_creation' else catalog
        tracking['packets'] = [p for p in tracking['packets'] if key(p) != key(removed)]
    elif fault in ('missing_creation_metadata', 'missing_catalog_metadata'):
        removed = creation if fault == 'missing_creation_metadata' else catalog
        tracking['events'] = [e for e in tracking['events'] if not (e.get('name') == removed['name'] and
            abs(e.get('time', 0) - removed['time']) < .001)]
    elif fault == 'creation_body':
        for p in tracking['packets']:
            if key(p) == key(creation):
                p['body'] = trainer_object_body(map_id=1).hex()
    elif fault.startswith('hidden_'):
        name = 'SMSG_UPDATE_OBJECT'
        if fault in ('hidden_movement', 'hidden_transport_movement'):
            name = 'SMSG_ON_MONSTER_MOVE' if fault == 'hidden_movement' else 'SMSG_ON_MONSTER_MOVE_TRANSPORT'
            body = trainer_packed_guid(contract.TRAINER_GUID)
        elif fault == 'hidden_destroy':
            name, body = 'SMSG_DESTROY_OBJECT', struct.pack('<Q', contract.TRAINER_GUID)
        elif fault == 'hidden_teleport':
            name, body = 'SMSG_MOVE_UPDATE_TELEPORT', trainer_teleport_body(contract.TRAINER_GUID)
        elif fault == 'hidden_remove':
            body = struct.pack('<HIBI', 0, 1, 3, 1) + trainer_packed_guid(contract.TRAINER_GUID)
        elif fault == 'hidden_recreate':
            body = trainer_object_body()
        else:
            field = {'hidden_dead': 'UNIT_FIELD_HEALTH', 'hidden_nontrainer': 'UNIT_NPC_FLAGS',
                     'hidden_petnumber': 'UNIT_FIELD_PETNUMBER'}[fault]
            body = trainer_object_body({trainer_evidence.INDEX[field]: 0 if fault == 'hidden_dead' else 1}, creation=False)
        tracking['packets'].append(packet('from_native', name, body, 1011.95))
    elif fault == 'changed_selected_proof':
        store.get(refs['selected'])['trainer_identity']['final_fields']['26'] = 0
    elif fault == 'changed_purchase_proof':
        purchase['trainer_identity']['entry_source']['sha256'] = 'f' * 64
    elif fault == 'changed_public_target':
        purchase['state']['target']['guid'] = 'Creature-0-1-0-0-46983-000002F78E'
    elif fault == 'changed_check_time':
        purchase['trainer_identity_checked_at'] += .1
    elif fault == 'changed_creation_claim':
        for value in data.values():
            if isinstance(value, dict) and value.get('trainer_identity'):
                value['trainer_identity']['creation']['object']['movement']['position'][0] += 1
    else:
        member = str(Path(store.ancestry[0]['sources'][-1]['copy_path']).relative_to(evidence.lab.ROOT))
        if fault == 'changed_unique_spawn':
            data[member]['rows'][0][0] += 1
        else:
            data.pop(member)
    with pytest.raises((RuntimeError, ValueError)):
        evidence.proof(data, digests, tracking)


@pytest.mark.parametrize('movement_name', ['SMSG_ON_MONSTER_MOVE', 'SMSG_ON_MONSTER_MOVE_TRANSPORT'])
def test_archive_stream_preserves_hidden_trainer_movement_for_whole_proof_rejection(monkeypatch, movement_name):
    _, _, tracking, payloads, _ = lifecycle_fixture(monkeypatch)
    tracking['packets'].append(packet('from_native', movement_name, trainer_packed_guid(contract.TRAINER_GUID), 1011.95))
    members = list(payloads.items()) + [
        (evidence.TRACKING_MEMBERS[0], b''.join(json.dumps(row).encode() + b'\n' for row in tracking['packets'])),
        (evidence.TRACKING_MEMBERS[1], b''.join(json.dumps(row).encode() + b'\n' for row in tracking['events'])),
    ]
    compressed, checkpoint, _ = archive_fixture(members)
    data, digests, journals, _ = reviewer.inspect_archive(io.BytesIO(compressed), checkpoint, 'evidence/synthetic/')
    assert any(p['name'] == movement_name for p in journals['packets'])
    with pytest.raises(RuntimeError, match='movement'):
        evidence.proof(data, digests, journals)


@pytest.mark.parametrize("fault", ["purchase_charge", "learned_caption", "trainer_identity", "runtime_actor",
                                  "screen_monitor", "missing_png", "stock_layout", "pose", "logout_body",
                                  "cleanup_refund", "reentry_known", "rest_float_bits", "final_pet_health",
                                  "primary_preservation", "pause_check", "missing_pause", "qualification",
                                  "prior_manifest", "ancestry_bytes", "hidden_cast", "unlogged_purchase_session",
                                  "backpack_resource", "bag_resource"])
def test_whole_lifecycle_refuses_unsupported_receipt_caption_state_or_shutdown_claims(monkeypatch, fault):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch)
    store = evidence.Sources(data, digests)
    if fault == "purchase_charge":
        store.get(refs["purchase"])["after_resources"]["money"] -= 1
    elif fault == "learned_caption":
        store.get(refs["purchase"])["learned_probe"]["rows"][0]["kind"] = "FUTURESPELL"
    elif fault == "trainer_identity":
        store.get(refs["opened"])["native_catalog"]["guid"] += 1
    elif fault == "runtime_actor":
        store.get(refs["selected"])["actor"]["guid"] = 2
    elif fault == "screen_monitor":
        store.get(refs["trainer_screen"], False)["frame"]["monitor"]["monitor"]["name"] = "DP-1"
    elif fault == "missing_png":
        digests.pop("evidence/synthetic/screens/trainer.png")
    elif fault == "stock_layout":
        store.get(refs["restoration"])["book_layout_restored"]["page"] = 2
    elif fault == "pose":
        store.get(refs["restoration"])["pose_restoration"]["restored"][0] += 1
    elif fault == "logout_body":
        store.get(refs["first_park"])["logout_packets"][-1]["body"] = ""
    elif fault == "cleanup_refund":
        store.get(refs["cleaned"])["refunded_copper"] = 680
    elif fault == "reentry_known":
        store.get(refs["reentry"])["login_known_spell_ids"].append(1462)
    elif fault == "rest_float_bits":
        store.get(refs["final_precision"])["row"]["exact_rest_bonus_float32_bits"] = "00000000"
    elif fault == "final_pet_health":
        store.get(refs["final_park"])["all_offline_snapshot"]["6"]["pets"][1]["curhealth"] = 0
    elif fault == "primary_preservation":
        store.get(refs["primary_stop"])["after"]["native"]["money"] -= 1
    elif fault == "pause_check":
        store.get(refs["pause"])["checks"]["owned_game_absent"] = False
    elif fault == "missing_pause":
        data.pop(str(Path(refs["pause"]["path"]).relative_to(evidence.lab.ROOT)))
    elif fault == "qualification":
        store.get(refs["purchase"])["qualification_added"] = True
    elif fault == "prior_manifest":
        store.get(refs["previous_checkpoint"], False)["file_manifest"][0]["sha256"] = "0" * 64
    elif fault == "ancestry_bytes":
        row = store.ancestry[0]["sources"][0]
        row["bytes"] += 1
    elif fault == "unlogged_purchase_session":
        retarget_purchase_session(store.get(refs["purchase"]), tracking, "third-session-without-owned-login")
    elif fault == "backpack_resource":
        store.get(refs["purchase"])["after_resources"]["backpack"][0]["count"] += 1
    elif fault == "bag_resource":
        store.get(refs["purchase"])["after_resources"]["bags"][0][0] = {"guid": 1235, "id": 6948, "count": 1}
    else:
        tracking["packets"].append(packet("to_native", "CMSG_CAST_SPELL", b"", 2012.5))
    with pytest.raises(RuntimeError):
        evidence.proof(data, digests, tracking)


def test_one_source_bound_trainer_exposure_can_precede_reviewed_lesson_selection(monkeypatch):
    data, digests, tracking, _, _ = lifecycle_fixture(monkeypatch, trainer_exposed=True)
    assert evidence.proof(data, digests, tracking)["native_purchases"] == 1


@pytest.mark.parametrize("fault", ["wrong_original", "changed_catalog", "extra_exposure"])
def test_trainer_exposure_cannot_substitute_another_source_or_add_an_unreviewed_branch(monkeypatch, fault):
    data, digests, tracking, _, refs = lifecycle_fixture(monkeypatch, trainer_exposed=True)
    exposed = evidence.Sources(data, digests).get(refs["exposed"])
    if fault == "wrong_original":
        exposed["source"] = refs["staged"]
    elif fault == "changed_catalog":
        exposed["native_catalog"]["guid"] += 1
    else:
        exposed["source"] = refs["exposed"]
    with pytest.raises(RuntimeError):
        evidence.proof(data, digests, tracking)


def archive_fixture(members=None):
    members = members or [
        ("evidence/synthetic/closure/episode.json", json.dumps(closure_fixture()).encode()),
        ("evidence/synthetic/closure/frame.png", png_bytes("archive")),
        (evidence.TRACKING_MEMBERS[0], b"{}\n"),
        (evidence.TRACKING_MEMBERS[1], b"{}\n"),
    ]
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as archive:
        for name, body in members:
            info = tarfile.TarInfo(name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    compressed = raw.getvalue()
    checkpoint = {"bytes": len(compressed), "sha256": hashlib.sha256(compressed).hexdigest(),
                  "file_manifest": [{"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                                    for name, body in members if name.startswith("evidence/")]}
    return compressed, checkpoint, members


def collect_archive_journal(member, rows, data, tracking):
    # Lifecycle semantics have their own tests; isolate the forward-only tar verifier.
    tracking["members"].add(member)
    tracking["packets" if member == evidence.TRACKING_MEMBERS[0] else "events"].extend(rows)


def test_remote_archive_verifier_hashes_complete_compressed_stream_and_selected_members(monkeypatch):
    monkeypatch.setattr(evidence, "collect", collect_archive_journal)
    compressed, checkpoint, _ = archive_fixture()
    data, digests, tracking, count = reviewer.inspect_archive(io.BytesIO(compressed), checkpoint, "evidence/synthetic/")
    assert count == len(compressed)
    assert data["evidence/synthetic/closure/episode.json"] == closure_fixture()
    assert set(digests) == {row["path"] for row in checkpoint["file_manifest"]}
    assert tracking["members"] == set(evidence.TRACKING_MEMBERS)


@pytest.mark.parametrize("fault", ["compressed_hash", "compressed_size", "member_hash", "member_size",
                                  "missing_selected", "missing_journal", "duplicate_selected", "duplicate_journal", "invalid_png"])
def test_actual_remote_archive_cannot_substitute_missing_duplicate_or_changed_bytes(monkeypatch, fault):
    monkeypatch.setattr(evidence, "collect", collect_archive_journal)
    compressed, checkpoint, members = archive_fixture()
    if fault == "compressed_hash":
        checkpoint["sha256"] = "0" * 64
    elif fault == "compressed_size":
        checkpoint["bytes"] += 1
    elif fault == "member_hash":
        checkpoint["file_manifest"][0]["sha256"] = "0" * 64
    elif fault == "member_size":
        checkpoint["file_manifest"][0]["bytes"] += 1
    elif fault == "missing_selected":
        checkpoint["file_manifest"].append({"path": "evidence/synthetic/missing.json", "bytes": 2,
                                           "sha256": hashlib.sha256(b"{}").hexdigest()})
    else:
        changed = list(members)
        if fault == "missing_journal":
            changed.pop()
        elif fault == "duplicate_selected":
            changed.append(members[0])
        elif fault == "duplicate_journal":
            changed.append(members[-1])
        else:
            changed[1] = (changed[1][0], b"not-png!synthetic")
        compressed, changed_checkpoint, _ = archive_fixture(changed)
        checkpoint.update(bytes=changed_checkpoint["bytes"], sha256=changed_checkpoint["sha256"])
        if fault == "invalid_png":
            checkpoint["file_manifest"] = changed_checkpoint["file_manifest"]
    with pytest.raises(RuntimeError):
        reviewer.inspect_archive(io.BytesIO(compressed), checkpoint, "evidence/synthetic/")


@pytest.mark.parametrize("extra", ["episode.json", "frame.png"])
def test_complete_batch_manifest_cannot_hide_an_undeclared_json_or_png(monkeypatch, extra):
    monkeypatch.setattr(evidence, "collect", collect_archive_journal)
    _, checkpoint, members = archive_fixture()
    body = b"{}" if extra.endswith(".json") else png_bytes("undeclared")
    compressed, changed, _ = archive_fixture([*members, ("evidence/synthetic/undeclared/" + extra, body)])
    checkpoint.update(bytes=changed["bytes"], sha256=changed["sha256"])
    with pytest.raises(RuntimeError, match="manifest"):
        reviewer.inspect_archive(io.BytesIO(compressed), checkpoint, "evidence/synthetic/")


@pytest.mark.parametrize("fault", ["duplicate", "absolute", "traversal", "negative_size", "truthy_size", "bad_hash", "no_png"])
def test_checkpoint_manifest_requires_unique_safe_json_png_paths_and_exact_sizes(fault):
    _, checkpoint, _ = archive_fixture()
    row = checkpoint["file_manifest"][0]
    if fault == "duplicate":
        checkpoint["file_manifest"].append(deepcopy(row))
    elif fault == "absolute":
        row["path"] = "/" + row["path"]
    elif fault == "traversal":
        row["path"] = "evidence/synthetic/../borrowed/episode.json"
    elif fault in ("negative_size", "truthy_size"):
        row["bytes"] = -1 if fault == "negative_size" else True
    elif fault == "bad_hash":
        row["sha256"] = "g" * 64
    else:
        checkpoint["file_manifest"].pop()
    with pytest.raises(RuntimeError):
        reviewer.manifest(checkpoint, "evidence/synthetic/")


def test_review_reads_the_published_pointer_and_builds_configured_remote_object_request(tmp_path):
    archive = "artifacts/client_harness/synthetic.tar.gz"
    pointer = tmp_path / (archive + ".dvc")
    pointer.parent.mkdir(parents=True)
    oid = "0123456789abcdef0123456789abcdef"
    pointer.write_text("outs:\n- md5: " + oid + "\n  size: 123\n  hash: md5\n  path: synthetic.tar.gz\n")
    assert reviewer.dvc_object(tmp_path, {"file": archive, "bytes": 123}) == (archive + ".dvc", oid)
    request = reviewer.remote_request({"url": "https://example.invalid/dvc"}, oid)
    assert request.full_url == "https://example.invalid/dvc/files/md5/01/23456789abcdef0123456789abcdef"
    request = reviewer.remote_request({"url": "s3://test-bucket/prefix", "endpointurl": "https://example.invalid",
                                       "access_key_id": "test-key", "secret_access_key": "test-secret", "region": "test-region"},
                                      oid, datetime(2026, 10, 7, tzinfo=timezone.utc))
    assert request.full_url == "https://example.invalid/test-bucket/prefix/files/md5/01/23456789abcdef0123456789abcdef"
    assert request.get_header("X-amz-date") == "20261007T000000Z"
    assert "test-key/20261007/test-region/s3/aws4_request" in request.get_header("Authorization")
    pointer.write_text(pointer.read_text().replace("size: 123", "size: 124"))
    with pytest.raises(RuntimeError, match="identity differs"):
        reviewer.dvc_object(tmp_path, {"file": archive, "bytes": 123})


@pytest.mark.parametrize("url", ["https://user:password@example.invalid/dvc", "https://example.invalid/dvc?borrowed=1",
                                "https://example.invalid/dvc#fragment", "file:///tmp/archive"])
def test_remote_request_cannot_borrow_an_implicit_or_local_object_root(url):
    with pytest.raises(RuntimeError):
        reviewer.remote_request({"url": url}, "0" * 32)


def test_all_learning_modules_import_without_client_input_or_optional_ui_dependencies():
    root = Path(__file__).resolve().parents[4]
    script = r'''
import importlib
import importlib.abc
from pathlib import Path
import sys

class PureOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname == "PIL" or fullname.startswith("PIL.") or
            fullname == "google.protobuf" or fullname.startswith("google.protobuf.") or
            fullname.rsplit(".", 1)[-1].startswith("interaction_")):
            raise AssertionError("pure learning module attempted forbidden import: " + fullname)

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
sys.meta_path.insert(0, PureOnly())
directory = root / "tools/client_compatibility"
modules = sorted(path.stem for path in directory.glob("hunter_learn_*.py"))
assert {"hunter_learn_contract", "hunter_learn_preservation", "hunter_learn_sources", "hunter_learn_evidence"} <= set(modules)
modules.append("review_hunter_learn_checkpoint")
for module in modules:
    importlib.import_module("tools.client_compatibility." + module)
assert not any(name == "PIL" or name.startswith("PIL.") or name == "google.protobuf" or
               name.startswith("google.protobuf.") or name.rsplit(".", 1)[-1].startswith("interaction_")
               for name in sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", script, str(root)], cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
