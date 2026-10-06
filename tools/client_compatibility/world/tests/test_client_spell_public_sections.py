"""Reject truncated public sections and keep encrypted sections out of evidence."""
import struct
import pytest
from tools.client_compatibility.client_spell_tables import public_sections
from tools.client_compatibility.client_spell_public_records import scalar


def prefix(*, key=0, stop=304, flags=4):
    data = bytearray(stop);data[:8] = b'WDC5\x05\0\0\0'
    header = [2, 1, 4, 0, 0, 0x7F31EDF7, 1, 2, 0, flags, 0, 1, 0, 0, 24, 0, 0, 1]
    struct.pack_into('<9I2H7I', data, 136, *header)
    struct.pack_into('<Q8I', data, 204, key, 288, 2, 0, 0, 8, 0, 0, 0)
    return data


def test_only_complete_plaintext_sections_are_admitted():
    assert public_sections(prefix(), 0x7F31EDF7)[1][0]['end'] == 304
    for data in [prefix(key=1), prefix(stop=303), prefix(flags=1), prefix()[:220]]:
        with pytest.raises(RuntimeError):public_sections(data, 0x7F31EDF7)


def test_common_values_bind_to_row_id_and_signed_values_keep_their_sign():
    assert scalar(0, (0, 0, 8, 2, 7, 0, 0), 44, [], {44:512}) == 512
    assert scalar(0, (0, 0, 8, 2, 7, 0, 0), 45, [], {44:512}) == 7
    assert scalar(15, (0, 4, 0, 5, 0, 4, 0), 1, [], {}) == -1
    with pytest.raises(ValueError):scalar(3, (0, 2, 4, 3, 0, 2, 0), 1, [9], {})
