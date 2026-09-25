"""Static checks for the split Nefarian's End native script.

The 2100-line boss_nefarians_end.cpp was split by concern without changing
statements; these checks pin that every script class is still registered once,
that the loader entry point still reaches every registration, that each file
stays under the 1,000-line module limit, and the Shadowblaze Spark floor.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
FILES = [
    SCRIPTS / "boss_nefarians_end.h",
    SCRIPTS / "boss_nefarians_end.cpp",
    SCRIPTS / "boss_nefarians_end_adds.cpp",
    SCRIPTS / "boss_nefarians_end_spells.cpp",
]
STRATEGY = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian"
LOADER = ROOT / "src/server/scripts/EasternKingdoms/eastern_kingdoms_script_loader.cpp"

DEFINITION = re.compile(r"^(?:struct|class) ((?:boss|npc|spell|go)_nefarians_end\w*)\b", re.M)
REGISTRATION = re.compile(
    r"Register(?:BlackwingDescentCreatureAI|SpellScript|GameObjectAI)\((\w+)\);")


def test_files_stay_under_the_module_limit() -> None:
    for path in FILES + sorted(STRATEGY.glob("*.h")):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path


def test_every_script_is_registered_exactly_once() -> None:
    defined: list[str] = []
    registered: list[str] = []
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        defined += DEFINITION.findall(text)
        registered += REGISTRATION.findall(text)
    assert len(defined) == 30
    assert sorted(defined) == sorted(registered)
    assert len(set(registered)) == len(registered)


def test_entry_point_reaches_split_registrations() -> None:
    main = (SCRIPTS / "boss_nefarians_end.cpp").read_text(encoding="utf-8")
    body = main[main.index("void AddSC_boss_nefarians_end()"):]
    assert "AddSC_boss_nefarians_end_adds();" in body
    assert "AddSC_boss_nefarians_end_spells();" in body
    for name in ("boss_nefarians_end_adds.cpp", "boss_nefarians_end_spells.cpp"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert f"void AddSC_{name[:-4]}()" in text
        assert '#include "boss_nefarians_end.h"' in text
    loader = LOADER.read_text(encoding="utf-8")
    assert loader.count("AddSC_boss_nefarians_end();") == 2
    assert "AddSC_boss_nefarians_end_adds" not in loader


def test_shadowblaze_spark_floor_is_fifteen_seconds_on_normal() -> None:
    spells = (SCRIPTS / "boss_nefarians_end_spells.cpp").read_text(encoding="utf-8")
    assert "std::max<uint32>(MinimumTriggerTicks(target), _nextTriggerTickNumber - 1)" in spells
    assert "return target->GetMap()->IsHeroic() ? 2 : 3;" in spells
    assert "std::max<uint32>(2, _nextTriggerTickNumber - 1)" not in spells
