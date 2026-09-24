#ifndef TRINITY_BOT_RAID_MEMBER_H
#define TRINITY_BOT_RAID_MEMBER_H

#include "ObjectGuid.h"

#include <algorithm>
#include <string>
#include <string_view>
#include <vector>

// One raid of a play cohort: the cohort's bots plus its registered external
// members (humans, or simulated humans in tests). Classification is by
// cohort membership, never by session type, so a simulated external is
// treated exactly like a human. Validation cohorts have no externals.
namespace BotRaidMember
{
enum class Kind : uint8
{
    Bot,
    External
};

enum class ExternalSource : uint8
{
    Human,
    Sim
};

struct Member
{
    ObjectGuid Guid;
    Kind MemberKind = Kind::Bot;
    ExternalSource Source = ExternalSource::Human;
    std::string Role;
    std::string ClassSpec;
    // Trained roster slot, or -1 when the member holds none.
    int32 SlotIndex = -1;
    uint8 SubGroup = 0;
    bool Online = true;
    bool InInstance = true;
    bool Alive = true;

    bool IsBot() const { return MemberKind == Kind::Bot; }
    bool IsExternal() const { return MemberKind == Kind::External; }
};

class View
{
public:
    View() = default;
    explicit View(std::vector<Member> members) : _members(std::move(members)) { }

    std::vector<Member> const& All() const { return _members; }

    std::vector<Member const*> Bots() const
    {
        return Select([](Member const& member) { return member.IsBot(); });
    }

    std::vector<Member const*> Externals() const
    {
        return Select([](Member const& member) { return member.IsExternal(); });
    }

    // Play-mode pull and taunt authority order: bot tanks first, then
    // external tanks; each by roster slot (unslotted last), then raw GUID.
    // Dead members are included. Validation's Magmaw pull tank is decided
    // elsewhere (main_tank lease, else lowest living GUID).
    std::vector<Member const*> DeclaredTanks() const
    {
        std::vector<Member const*> tanks = Select([](Member const& member)
        {
            return member.Role == "tank";
        });
        std::stable_sort(tanks.begin(), tanks.end(),
            [](Member const* left, Member const* right)
            {
                if (left->IsBot() != right->IsBot())
                    return left->IsBot();
                bool const leftSlotted = left->SlotIndex >= 0;
                bool const rightSlotted = right->SlotIndex >= 0;
                if (leftSlotted != rightSlotted)
                    return leftSlotted;
                if (left->SlotIndex != right->SlotIndex)
                    return left->SlotIndex < right->SlotIndex;
                return left->Guid.GetRawValue() < right->Guid.GetRawValue();
            });
        return tanks;
    }

    Member const* Find(ObjectGuid guid) const
    {
        auto member = std::find_if(_members.begin(), _members.end(),
            [guid](Member const& candidate) { return candidate.Guid == guid; });
        return member == _members.end() ? nullptr : &*member;
    }

    bool IsExternal(ObjectGuid guid) const
    {
        Member const* member = Find(guid);
        return member && member->IsExternal();
    }

    std::size_t CountRole(std::string_view role, bool aliveOnly) const
    {
        return std::size_t(std::count_if(_members.begin(), _members.end(),
            [role, aliveOnly](Member const& member)
            {
                return member.Role == role && (!aliveOnly || member.Alive);
            }));
    }

private:
    template <typename Predicate>
    std::vector<Member const*> Select(Predicate predicate) const
    {
        std::vector<Member const*> selected;
        for (Member const& member : _members)
            if (predicate(member))
                selected.push_back(&member);
        return selected;
    }

    std::vector<Member> _members;
};
}

#endif
