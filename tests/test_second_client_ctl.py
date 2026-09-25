from __future__ import annotations

from tools.second_client import ctl


def test_shifted_symbols_type_through_their_us_base_key() -> None:
    # Live 2026-09-24: '(' and ')' resolved to keypad keycodes and were dropped.
    assert ctl.key_for_char("(") == ("9", True)
    assert ctl.key_for_char(")") == ("0", True)
    assert ctl.key_for_char('"') == ("apostrophe", True)
    assert ctl.key_for_char("R") == ("r", True)
    assert ctl.key_for_char("\n") == ("Return", False)
    assert ctl.key_for_char("r") is None
    assert ctl.key_for_char(".") is None


def test_client_starts_on_the_sdl_backend_by_default() -> None:
    assert ctl.BACKEND == "sdl"
