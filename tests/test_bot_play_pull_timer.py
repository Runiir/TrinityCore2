from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]


def test_pull_timers_from_dbm_bigwigs_and_raid_chat(tmp_path: Path) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(
        r'''
#include "Bots/BotPlayPullTimer.h"
#include <cstdio>
#include <string>

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

using namespace BotPlayPullTimer;

static int failures = 0;

static void Expect(bool condition, bool, bool, uint32, char const* label)
{
    if (!condition)
    {
        std::fprintf(stderr, "FAIL: %s\n", label);
        ++failures;
    }
}

static void Expect(std::optional<Signal> signal, bool present, bool cancel, uint32 seconds,
    char const* label)
{
    bool const ok = signal.has_value() == present
        && (!present || (signal->Cancel == cancel && signal->Seconds == seconds));
    if (!ok)
    {
        std::fprintf(stderr, "FAIL: %s\n", label);
        ++failures;
    }
}

int main()
{
    // DBM 4.3.4 (/dbm pull 10) and later D5 framing; 0 cancels.
    Expect(ParseAddon("D4", "PT\t10"), true, false, 10, "dbm d4");
    Expect(ParseAddon("D4", "PT\t10\t669\tMagmaw"), true, false, 10, "dbm d4 extra fields");
    Expect(ParseAddon("D5", "Runiir-Trinity\t1\tPT\t15\t669"), true, false, 15, "dbm d5");
    Expect(ParseAddon("D4", "PT\t0"), true, true, 0, "dbm cancel");
    Expect(ParseAddon("D4", "PT\t90"), true, false, 90, "dbm long timer");
    Expect(ParseAddon("D4", "PT\t900"), false, false, 0, "dbm over max ignored");
    // Cataclysm-era DBM: pizza timer "U\t<sec>\tPull in".
    Expect(ParseAddon("D4", "U\t10\tPull in"), true, false, 10, "dbm cata pizza pull");
    Expect(ParseAddon("D4", "U\t30\tBreak time"), false, false, 0, "dbm other pizza timer");
    Expect(ParseAddon("D4", "V\t12345\tv4.11"), false, false, 0, "dbm version sync");
    Expect(ParseAddon("D4", "PT\tabc"), false, false, 0, "dbm malformed");
    // BigWigs, old and new framing.
    Expect(ParseAddon("BigWigs", "T:BWPull 10"), true, false, 10, "bigwigs old");
    Expect(ParseAddon("BigWigs", "P^Pull^8"), true, false, 8, "bigwigs new");
    Expect(ParseAddon("BigWigs", "VR:12345"), false, false, 0, "bigwigs version");
    Expect(ParseAddon("BigWigs", "T:BWCustomBar 10 Pull 1"), false, false, 0, "bigwigs custom bar");
    Expect(ParseAddon("Recount", "PT\t10"), false, false, 0, "other addon");

    // Raid chat or raid warning from the leader.
    Expect(ParseChat("pull 10"), true, false, 10, "chat pull 10");
    Expect(ParseChat("Pull in 10 sec"), true, false, 10, "chat pull in");
    Expect(ParseChat("pulling in 5"), true, false, 5, "chat pulling in");
    Expect(ParseChat("pull now!"), true, false, 0, "chat pull now");
    Expect(ParseChat("cancel pull"), true, true, 0, "chat cancel");
    Expect(ParseChat("Pull cancelled"), true, true, 0, "chat cancelled");
    Expect(ParseChat("who pulls?"), false, false, 0, "chat question");
    Expect(ParseChat("nice pull guys"), false, false, 0, "chat chatter");
    Expect(ParseChat("pull the boss when ready"), false, false, 0, "chat no number");
    // Review of 1f4405f1dc: ordinary leader chat must not start timers.
    Expect(ParseChat("pull 1 more pack"), false, false, 0, "chat more pack");
    Expect(ParseChat("I'll pull in 5 min"), false, false, 0, "chat minutes");
    Expect(ParseChat("pull in 2 min, grab food"), false, false, 0, "chat minutes food");
    Expect(ParseChat("pull 2 packs then boss"), false, false, 0, "chat packs");
    Expect(ParseChat("pull in 90"), true, false, 90, "chat long timer");
    // Review of 65286275ed: a leader holding the raid must never trigger a pull.
    Expect(ParseChat("don't pull now"), true, true, 0, "chat dont pull now cancels");
    Expect(ParseChat("do not pull now, wait for mana"), true, true, 0, "chat do not pull cancels");
    Expect(ParseChat("can I pull now?"), false, false, 0, "chat question now");
    Expect(ParseChat("do not pull in 10"), true, true, 0, "chat do not pull in 10 cancels");
    Expect(ParseChat("dont pull 10"), true, true, 0, "chat dont pull 10 cancels");
    Expect(ParseChat("wait, hold the pull"), true, true, 0, "chat hold the pull");
    Expect(ParseChat("pull now wait"), false, false, 0, "chat now not ending");

    // Timer phases: counting down, released for a window, then over.
    Expect(Running(10000, 9999) && !Released(10000, 9999), true, false, 0, "running");
    Expect(!Running(10000, 10000) && Released(10000, 10000), true, false, 0, "released at zero");
    Expect(Released(10000, 10000 + ReleaseWindowMs - 1), true, false, 0, "released in window");
    Expect(!Released(10000, 10000 + ReleaseWindowMs) && !Running(10000, 50000), true, false, 0,
        "stale timer never permits");
    Expect(!Running(0, 5) && !Released(0, 5), true, false, 0, "no timer");
    return failures == 0 ? 0 : 1;
}
'''
    )
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
