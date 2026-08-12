from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bot_dataset_event_declares_rapidjson_assert_before_rapidjson_include() -> None:
    source = (ROOT / "src/server/game/Bots/BotDatasetEvent.cpp").read_text(encoding="utf-8")
    errors_include = source.index('#include "Errors.h"')
    rapidjson_include = source.index("#include <rapidjson/document.h>")

    assert errors_include < rapidjson_include
