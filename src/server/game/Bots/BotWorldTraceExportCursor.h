#ifndef TRINITY_BOT_WORLD_TRACE_EXPORT_CURSOR_H
#define TRINITY_BOT_WORLD_TRACE_EXPORT_CURSOR_H

#include <cstddef>
#include <cstdint>
#include <limits>
#include <ostream>
#include <vector>

namespace BotWorldTrace
{
struct ExportCursorTransition
{
    std::uint64_t CursorBefore = 0;
    std::uint64_t CursorAfter = 0;
    std::size_t FirstEntryIndex = 0;
    std::size_t EntryCount = 0;
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
    return transition;
}

inline void WriteExportCursorFields(std::ostream& json, ExportCursorTransition const& transition)
{
    json << ",\"delta\":true"
         << ",\"cursor_before\":" << transition.CursorBefore
         << ",\"cursor_after\":" << transition.CursorAfter
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
