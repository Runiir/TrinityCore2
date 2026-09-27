#ifndef TRINITY_BOT_RAID_SPEC_SWITCH_H
#define TRINITY_BOT_RAID_SPEC_SWITCH_H

// Per-boss talent group switching in a canonical full raid (round 10).
//
// A composition runs one set of characters, and a boss shard may put a member
// in its other talent group (BWD: the druid is Balance on Magmaw and
// Atramedes and the Feral tank elsewhere; the shaman is Elemental or
// Restoration). The full raid's route mirrors the shards
// (tools/raid_program/raid_full_route_mirror.py) and carries a `spec_contract`
// on a regroup node before every node set whose shard uses other groups: one
// row per roster slot with the wanted talent group and the identity (class
// spec, role) of each of the character's groups.
//
// At that node each member, out of combat at the anchor, does what a player
// does: casts its own Activate Primary/Secondary Spec spell (63645/63644,
// SPELL_EFFECT_TALENT_SPEC_SELECT -> Player::ActivateSpec, glyphs and action
// bars follow natively), then uses the group's equipment set through its own
// CMSG_EQUIPMENT_SET_USE handler (character_equipmentsets row setindex =
// talent group, provisioned by tools/raid_program/raid_loadout_sql.py), then
// its admission receipt is re-frozen for the new spec and the switch is
// receipted. The identity readers follow the active group
// (BotActiveSpecIdentity.h). Pure parsing and decisions live here.

#include "Bots/BotValidationRouteNativeJson.h"

#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace BotRaidSpecSwitch
{
using Json = BotValidationRouteNativeJson::Value;

constexpr std::uint32_t ActivatePrimarySpecSpellId = 63645;   // talent group 0
constexpr std::uint32_t ActivateSecondarySpecSpellId = 63644; // talent group 1
constexpr std::uint8_t MaxTalentGroups = 2;
constexpr std::uint32_t MaxRosterSlot = 40;
// Out-of-combat time a member may spend at a spec-switch node (a 5 s cast,
// the equipment swap and the retries) before the attempt fails typed.
constexpr std::uint64_t SwitchTimeoutMs = 60000;
constexpr std::uint64_t RetryIntervalMs = 2000;
constexpr char const* TimeoutPrefix = "route_spec_switch_timeout:";
constexpr char const* EventName = "validation_route_spec_switch";

struct GroupIdentity
{
    std::uint8_t TalentGroup = 0;
    std::string ClassSpec;
    std::string Role;
};

struct ContractRow
{
    std::uint32_t RosterSlot = 0;
    std::uint8_t TalentGroup = 0;
    std::string ClassSpec;
    std::string Role;
    std::string CharacterKey;
    std::vector<GroupIdentity> TalentGroups;
};

inline std::uint32_t ActivateSpellFor(std::uint8_t talentGroup)
{
    return talentGroup == 0 ? ActivatePrimarySpecSpellId : ActivateSecondarySpecSpellId;
}

inline bool KnownRole(std::string_view role)
{
    return role == "tank" || role == "healer" || role == "dps";
}

inline bool OnlyFields(Json const& object, std::vector<std::string_view> const& allowed, std::string& error)
{
    for (auto const& [key, value] : object.Members)
    {
        bool known = false;
        for (std::string_view name : allowed)
            known = known || key == name;
        if (!known)
        {
            error = "spec_contract_unknown_field:" + key;
            return false;
        }
    }
    return true;
}

// Fail-closed: an empty array, an unknown field, a duplicate slot or group, a
// wanted group the row does not declare, or a wanted identity that differs
// from the declared group's stops the manifest before any bot is admitted.
inline bool ParseContract(Json const& array, std::vector<ContractRow>& out, std::string& error)
{
    namespace J = BotValidationRouteNativeJson;
    out.clear();
    if (!array.IsArray() || array.Items.empty())
    {
        error = "spec_contract_shape";
        return false;
    }
    for (Json const& item : array.Items)
    {
        if (!item.IsObject())
        {
            error = "spec_contract_row_shape";
            return false;
        }
        if (!OnlyFields(item, { "roster_slot", "talent_group", "class_spec", "role",
                "character_key", "talent_groups" }, error))
            return false;
        ContractRow row;
        std::uint64_t slot = 0, group = 0;
        // Every identity field is required: a missing wanted group must not
        // silently become group 0.
        if (!item.Find("roster_slot") || !item.Find("talent_group") || !item.Find("class_spec")
            || !item.Find("role"))
        {
            error = "spec_contract_row_field_missing";
            return false;
        }
        if (!J::ReadUnsigned(item, "roster_slot", slot, MaxRosterSlot)
            || !J::ReadUnsigned(item, "talent_group", group, MaxTalentGroups - 1)
            || !J::ReadString(item, "class_spec", row.ClassSpec)
            || !J::ReadString(item, "role", row.Role)
            || !J::ReadString(item, "character_key", row.CharacterKey)
            || !slot || row.ClassSpec.empty() || !KnownRole(row.Role))
        {
            error = "spec_contract_row_invalid";
            return false;
        }
        row.RosterSlot = std::uint32_t(slot);
        row.TalentGroup = std::uint8_t(group);
        Json const* groups = item.Find("talent_groups");
        if (!groups || !groups->IsArray() || groups->Items.empty()
            || groups->Items.size() > MaxTalentGroups)
        {
            error = "spec_contract_talent_groups_shape";
            return false;
        }
        bool wantedDeclared = false;
        for (Json const& declared : groups->Items)
        {
            if (!declared.IsObject()
                || !OnlyFields(declared, { "talent_group", "class_spec", "role" }, error))
            {
                if (error.empty())
                    error = "spec_contract_talent_group_shape";
                return false;
            }
            GroupIdentity identity;
            std::uint64_t index = MaxTalentGroups;
            if (!declared.Find("talent_group") || !declared.Find("class_spec") || !declared.Find("role")
                || !J::ReadUnsigned(declared, "talent_group", index, MaxTalentGroups - 1)
                || !J::ReadString(declared, "class_spec", identity.ClassSpec)
                || !J::ReadString(declared, "role", identity.Role)
                || identity.ClassSpec.empty() || !KnownRole(identity.Role))
            {
                error = "spec_contract_talent_group_invalid";
                return false;
            }
            identity.TalentGroup = std::uint8_t(index);
            for (GroupIdentity const& other : row.TalentGroups)
                if (other.TalentGroup == identity.TalentGroup)
                {
                    error = "spec_contract_talent_group_duplicate";
                    return false;
                }
            if (identity.TalentGroup == row.TalentGroup)
            {
                if (identity.ClassSpec != row.ClassSpec || identity.Role != row.Role)
                {
                    error = "spec_contract_wanted_identity_mismatch";
                    return false;
                }
                wantedDeclared = true;
            }
            row.TalentGroups.push_back(std::move(identity));
        }
        if (!wantedDeclared)
        {
            error = "spec_contract_wanted_group_undeclared";
            return false;
        }
        for (ContractRow const& other : out)
            if (other.RosterSlot == row.RosterSlot)
            {
                error = "spec_contract_slot_duplicate";
                return false;
            }
        out.push_back(std::move(row));
    }
    return true;
}

// A manifest route row's `spec_contract` property, located structurally (a
// regex-style "next [" search would skip null, strings and objects, and would
// accept an object that merely wraps an array). `present` is false only when
// the property is absent; any present value goes to ParseContract, which
// accepts only a non-empty array of well-formed rows.
inline bool ParseRouteRowContract(std::string_view routeRowJson, std::vector<ContractRow>& out,
    bool& present, std::string& error)
{
    out.clear();
    present = false;
    Json row;
    std::string parseError;
    if (!BotValidationRouteNativeJson::Parse(routeRowJson, row, parseError) || !row.IsObject())
    {
        present = routeRowJson.find("\"spec_contract\"") != std::string_view::npos;
        error = "spec_contract_route_row_unparsable";
        return !present;
    }
    Json const* value = row.Find("spec_contract");
    if (!value)
        return true;
    present = true;
    return ParseContract(*value, out, error);
}

inline ContractRow const* FindRow(std::vector<ContractRow> const& contract, std::uint32_t rosterSlot)
{
    for (ContractRow const& row : contract)
        if (row.RosterSlot == rosterSlot)
            return &row;
    return nullptr;
}

// One member's next step at a spec-switch node, from what it observes.
enum class Step : std::uint8_t
{
    Done,           // the wanted group is active, its set equipped, identity re-frozen
    CastActivate,   // cast the wanted group's Activate Spec spell
    AwaitCast,      // the Activate Spec cast (or its effect) is still running
    EquipSet,       // the wanted group is active; equip its equipment set
    Refreeze,       // active and equipped; re-freeze the admission receipt
    Timeout,        // out of time: fail the attempt typed
};

struct Observation
{
    std::uint8_t ActiveGroup = 0;
    std::uint8_t WantedGroup = 0;
    bool Casting = false;
    bool SetEquipped = false;
    bool ReceiptCurrent = false;
    bool RetryDue = true;
    std::uint64_t WaitingSinceMs = 0;
    std::uint64_t NowMs = 0;
};

inline Step Decide(Observation const& in)
{
    bool const timedOut = in.WaitingSinceMs && in.NowMs >= in.WaitingSinceMs + SwitchTimeoutMs;
    if (in.ActiveGroup != in.WantedGroup)
    {
        if (timedOut)
            return Step::Timeout;
        return in.Casting || !in.RetryDue ? Step::AwaitCast : Step::CastActivate;
    }
    if (!in.SetEquipped)
        return timedOut ? Step::Timeout : (in.RetryDue ? Step::EquipSet : Step::AwaitCast);
    return in.ReceiptCurrent ? Step::Done : Step::Refreeze;
}

inline char const* StepName(Step step)
{
    switch (step)
    {
        case Step::Done: return "done";
        case Step::CastActivate: return "cast_activate_spec";
        case Step::AwaitCast: return "await_activate_spec";
        case Step::EquipSet: return "equip_group_set";
        case Step::Refreeze: return "refreeze_identity";
        case Step::Timeout: return "timeout";
    }
    return "unknown";
}
}

#endif
