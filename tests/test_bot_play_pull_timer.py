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
    Expect(ParseAddon("D4", "PT\t90"), true, false, 60, "dbm clamp");
    Expect(ParseAddon("D4", "V\t12345\tv4.11"), false, false, 0, "dbm version sync");
    Expect(ParseAddon("D4", "PT\tabc"), false, false, 0, "dbm malformed");
    // BigWigs, old and new framing.
    Expect(ParseAddon("BigWigs", "T:BWPull 10"), true, false, 10, "bigwigs old");
    Expect(ParseAddon("BigWigs", "P^Pull^8"), true, false, 8, "bigwigs new");
    Expect(ParseAddon("BigWigs", "VR:12345"), false, false, 0, "bigwigs version");
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
    return failures == 0 ? 0 : 1;
}
'''
    )
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
