from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIELD_CPP = ROOT / "src/server/database/Database/Field.cpp"
PLAYER_CPP = ROOT / "src/server/game/Entities/Player/Player.cpp"


def test_release_raw_field_keeps_owner_separate_from_following_modelid() -> None:
    harness = r'''
#include "Field.h"

#include <cassert>
#include <cstdint>

class RawField : public Field
{
public:
    void Bind(void const* value, uint32 length)
    {
        SetByteValue(static_cast<char const*>(value), length);
    }
};

struct PreparedOwnerAndModel
{
    std::uint32_t Owner;
    std::uint32_t ModelId;
};

int main()
{
    PreparedOwnerAndModel const row{30009, 4124};
    RawField owner;
    owner.Bind(&row.Owner, sizeof(row.Owner));

    assert(owner.GetUInt32() == 30009);
    assert(owner.GetUInt64() == ((std::uint64_t(4124) << 32) | 30009));

    PreparedOwnerAndModel const wrongRow{20009, 4124};
    RawField wrongOwner;
    wrongOwner.Bind(&wrongRow.Owner, sizeof(wrongRow.Owner));
    assert(wrongOwner.GetUInt32() == 20009);
    assert(wrongOwner.GetUInt32() != 30009);
}
'''
    include_dirs = [
        ROOT / "src/common",
        ROOT / "src/common/Asio",
        ROOT / "src/common/Debugging",
        ROOT / "src/common/Logging",
        ROOT / "src/common/Utilities",
        ROOT / "src/server/database/Database",
        ROOT / "dep/fmt/include",
        Path("/usr/include/mysql"),
    ]
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        source = directory_path / "player_pet_owner_field_width.cpp"
        binary = directory_path / "player_pet_owner_field_width"
        source.write_text(harness, encoding="utf-8")
        subprocess.run([
            "g++", "-std=c++17", "-O2",
            "-ffunction-sections", "-fdata-sections",
            "-Wall", "-Wextra", "-Werror",
            *(flag for path in include_dirs for flag in ("-I", str(path))),
            str(source), str(FIELD_CPP),
            "-Wl,--gc-sections", "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)


def test_player_pet_loader_uses_database_owner_width() -> None:
    source = PLAYER_CPP.read_text(encoding="utf-8")
    load = source[source.index("void Player::LoadPetsFromDB") :]
    assert "playerPetData->Owner         = fields[2].GetUInt32();" in load
    assert "playerPetData->Owner         = fields[2].GetUInt64();" not in load
