"""The combat resolver as one logical source for source-slicing tests.

Round 4 split BotWorldPopulationMgrCombatResolver.cpp by concern. The
per-candidate admission gates and the ranking loop moved verbatim into
BotWorldPopulationMgrCombatResolverAdmission.cpp
(BotWorldPopulationMgr::AdmitProfileCombatCandidates), which
ResolveProfileCombatAction calls between building the candidates and choosing
among the bests. Tests that slice production code out of the resolver read
combat_resolver_source(): the admission module's includes and helpers, then
the resolver file with the moved statements spliced back in at that call, so
slices, counts and order checks see one resolution in execution order. Checks
on the files themselves (line counts, CMake registration) use
COMBAT_RESOLVER_FILES.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
RESOLVER = BOTS / "BotWorldPopulationMgrCombatResolver.cpp"
ADMISSION = BOTS / "BotWorldPopulationMgrCombatResolverAdmission.cpp"
ADMISSION_CONTEXT = BOTS / "BotWorldPopulationMgrCombatResolverAdmission.h"
COMBAT_RESOLVER_FILES = (RESOLVER, ADMISSION)

# The call glue in ResolveProfileCombatAction, from its comment to the call.
CALL_START = "    // The per-candidate admission gates and ranking live in\n"
CALL_END = "    AdmitProfileCombatCandidates(admission);\n"
# AdmitProfileCombatCandidates binds its locals, then runs the moved statements.
ADMISSION_DEFINITION = "void BotWorldPopulationMgr::AdmitProfileCombatCandidates("
BODY_START = "    auto hasMechanicTag = [](std::string const& tags, char const* required) -> bool\n"


def admission_preamble() -> str:
    """The admission module's includes and anonymous-namespace helpers."""
    source = ADMISSION.read_text(encoding="utf-8")
    return source[:source.index(ADMISSION_DEFINITION)]


def admission_body() -> str:
    """The moved statements of AdmitProfileCombatCandidates, without its bindings."""
    source = ADMISSION.read_text(encoding="utf-8")
    start = source.index(BODY_START, source.index(ADMISSION_DEFINITION))
    end = source.rindex("\n}\n")
    return source[start:end + 1]


def combat_resolver_source() -> str:
    """The admission preamble, then the resolver with the admission statements
    spliced back at the call (the call glue and the local bindings dropped)."""
    resolver = RESOLVER.read_text(encoding="utf-8")
    start = resolver.index(CALL_START)
    end = resolver.index(CALL_END, start) + len(CALL_END)
    return admission_preamble() + resolver[:start] + admission_body() + resolver[end:]
