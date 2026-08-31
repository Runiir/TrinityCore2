#ifndef TRINITY_BOT_INTENT_SINK_H
#define TRINITY_BOT_INTENT_SINK_H

#include "Bots/BotNativeActionIntent.h"

#include <utility>
#include <vector>

namespace BotDecision
{
// Passive collection boundary for shadow intent producers. It deliberately
// has no selection, ordering, arbitration, mutation, or execution behavior.
class BotIntentSink
{
public:
    void Propose(BotNativeAction::Candidate candidate)
    {
        _proposals.push_back(std::move(candidate));
    }

    std::vector<BotNativeAction::Candidate> const& Proposals() const
    {
        return _proposals;
    }

private:
    std::vector<BotNativeAction::Candidate> _proposals;
};
}

#endif
