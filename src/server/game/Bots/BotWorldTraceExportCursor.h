#ifndef TRINITY_BOT_WORLD_TRACE_EXPORT_CURSOR_H
#define TRINITY_BOT_WORLD_TRACE_EXPORT_CURSOR_H

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <ostream>
#include <vector>

namespace BotWorldTrace
{
// Keep the interactive tail, but do not discard pending delta evidence merely
// because the next poll was delayed. The hard cap protects server memory;
// BuildExportCursorTransition reports any cap overflow as an explicit gap.
inline constexpr std::size_t ExportedTraceTail = 128;
inline constexpr std::size_t PendingTraceCapacity = 4096;

template <class Entries>
void TrimExportedTrace(Entries& entries, std::uint64_t exportedCursor)
{
    auto const firstPending = std::upper_bound(entries.begin(), entries.end(),
        exportedCursor, [](std::uint64_t cursor, auto const& entry)
        { return cursor < entry.Sequence; });
    std::size_t exported = std::size_t(firstPending - entries.begin());
    while (exported > ExportedTraceTail)
    {
        entries.pop_front();
        --exported;
    }
    std::size_t const pending = entries.size() - exported;
    if (pending > PendingTraceCapacity)
        entries.erase(entries.begin() + exported,
            entries.begin() + exported + pending - PendingTraceCapacity);
}

struct ExportCursorTransition
{
    std::uint64_t CursorBefore = 0;
    std::uint64_t CursorAfter = 0;
    std::size_t FirstEntryIndex = 0;
    std::size_t EntryCount = 0;
    std::size_t PendingEntryCount = 0;
    bool HasDiscontinuity = false;
    std::uint64_t MissingSequenceStart = 0;
    std::uint64_t MissingSequenceEnd = 0;
    std::uint64_t OldestRetainedSequence = 0;
    std::uint64_t NewestRetainedSequence = 0;
};

inline ExportCursorTransition BuildExportCursorTransition(
    std::vector<std::uint64_t> const& retainedSequences,
    std::uint64_t cursor, bool cursorInitialized, std::size_t limit)
{
    ExportCursorTransition transition;
    transition.CursorBefore = cursor;
    transition.CursorAfter = cursor;
    transition.FirstEntryIndex = retainedSequences.size();
    if (!retainedSequences.empty())
    {
        transition.OldestRetainedSequence = retainedSequences.front();
        transition.NewestRetainedSequence = retainedSequences.back();
    }

    for (std::size_t index = 0; index < retainedSequences.size(); ++index)
    {
        if (retainedSequences[index] > cursor)
        {
            transition.FirstEntryIndex = index;
            break;
        }
    }

    if (transition.FirstEntryIndex == retainedSequences.size())
        return transition;

    std::uint64_t const firstRetained = retainedSequences[transition.FirstEntryIndex];
    std::uint64_t const expectedFirst = cursorInitialized ? cursor + 1 : 1;
    if (firstRetained > expectedFirst)
    {
        transition.HasDiscontinuity = true;
        transition.MissingSequenceStart = expectedFirst;
        transition.MissingSequenceEnd = firstRetained - 1;
        transition.OldestRetainedSequence = firstRetained;
        transition.NewestRetainedSequence = retainedSequences.back();
    }

    std::uint64_t previous = 0;
    for (std::size_t index = transition.FirstEntryIndex;
         index < retainedSequences.size() && transition.EntryCount < limit; ++index)
    {
        std::uint64_t const sequence = retainedSequences[index];
        if (transition.EntryCount &&
            (previous == std::numeric_limits<std::uint64_t>::max() || sequence != previous + 1))
            break;
        previous = sequence;
        transition.CursorAfter = sequence;
        ++transition.EntryCount;
    }
    transition.PendingEntryCount = retainedSequences.size()
        - transition.FirstEntryIndex - transition.EntryCount;
    return transition;
}

inline void WriteExportCursorFields(std::ostream& json, ExportCursorTransition const& transition)
{
    json << ",\"delta\":true"
         << ",\"cursor_before\":" << transition.CursorBefore
         << ",\"cursor_after\":" << transition.CursorAfter
         << ",\"pending_entry_count\":" << transition.PendingEntryCount
         << ",\"newest_retained_sequence\":" << transition.NewestRetainedSequence
         << ",\"gap\":" << (transition.HasDiscontinuity ? "true" : "false");
    if (transition.HasDiscontinuity)
    {
        json << ",\"discontinuity\":{\"missing_sequence_start\":" << transition.MissingSequenceStart
             << ",\"missing_sequence_end\":" << transition.MissingSequenceEnd
             << ",\"oldest_retained_sequence\":" << transition.OldestRetainedSequence
             << ",\"newest_retained_sequence\":" << transition.NewestRetainedSequence << "}";
    }
}
}

#endif
