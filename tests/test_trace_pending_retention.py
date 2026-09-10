"""Exercise the production retention and cursor together, including overflow."""
from pathlib import Path
import subprocess


def test_delayed_consumer_retains_pre_failure_context_and_reports_real_overflow(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "retention.cpp"
    binary = tmp_path / "retention"
    source.write_text(r'''
#include "Bots/BotWorldTraceExportCursor.h"
#include <cassert>
#include <deque>
#include <string>
struct Row { std::uint64_t Sequence; std::string Reason; };
int main() {
    std::deque<Row> rows;
    std::uint64_t cursor = 0;
    // The observed head-hide decision precedes 1000 later records, so the
    // former 128-row eviction loses it before an investigator can inspect it.
    for (std::uint64_t n = 1; n <= 1001; ++n) {
        rows.push_back({n, n == 1 ? "head_hidden_body_bind_failed" : "later"});
        BotWorldTrace::TrimExportedTrace(rows, cursor);
    }
    assert(rows.front().Reason == "head_hidden_body_bind_failed");
    std::size_t received = 0;
    while (cursor < 1001) {
        std::vector<std::uint64_t> sequences;
        for (auto const& row : rows) sequences.push_back(row.Sequence);
        auto batch = BotWorldTrace::BuildExportCursorTransition(sequences, cursor, cursor != 0, 128);
        assert(!batch.HasDiscontinuity && batch.EntryCount);
        assert(batch.PendingEntryCount == 1001 - batch.CursorAfter);
        received += batch.EntryCount;
        cursor = batch.CursorAfter;
        BotWorldTrace::TrimExportedTrace(rows, cursor);
    }
    assert(received == 1001 && rows.size() == 128);
    // An unavailable consumer cannot cause unlimited server memory growth.
    for (std::uint64_t n = 1002; n <= 6000; ++n) {
        rows.push_back({n, "later"});
        BotWorldTrace::TrimExportedTrace(rows, cursor);
    }
    assert(rows.size() == BotWorldTrace::PendingTraceCapacity + BotWorldTrace::ExportedTraceTail);
    std::vector<std::uint64_t> sequences;
    for (auto const& row : rows) sequences.push_back(row.Sequence);
    auto overflow = BotWorldTrace::BuildExportCursorTransition(sequences, cursor, true, 128);
    assert(overflow.HasDiscontinuity);
    assert(overflow.MissingSequenceStart == 1002);
    assert(overflow.MissingSequenceEnd == rows[BotWorldTrace::ExportedTraceTail].Sequence - 1);
    // Internal losses cannot be concealed by a contiguous-looking batch end.
    auto beforeGap = BotWorldTrace::BuildExportCursorTransition({1, 2, 4, 5}, 0, false, 128);
    assert(beforeGap.EntryCount == 2 && beforeGap.PendingEntryCount == 2);
    auto afterGap = BotWorldTrace::BuildExportCursorTransition({1, 2, 4, 5}, 2, true, 128);
    assert(afterGap.HasDiscontinuity && afterGap.MissingSequenceStart == 3);
    assert(afterGap.MissingSequenceEnd == 3 && afterGap.CursorAfter == 5);
}
''')
    subprocess.run(["c++", "-std=c++17", "-I", str(root / "src/server/game"),
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
