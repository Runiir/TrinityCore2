#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotActiveSpecIdentity.h"
#include "Bots/BotRaidSpecSwitch.h"
#include "Bots/BotWorldPopulationMgrSpellSemantics.h"

#include "DatabaseEnv.h"
#include "Item.h"
#include "ObjectGuid.h"
#include "Opcodes.h"
#include "Player.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <array>
#include <map>
#include <mutex>
#include <string>
#include <utility>

// The canonical full raid's per-boss talent group switch (BotRaidSpecSwitch.h).
// Everything a member does here is its own player action: the Activate Spec
// spell through the ordinary cast path, the equipment set through its own
// CMSG_EQUIPMENT_SET_USE handler. Completion is observed on the Player.

using BotWorldPopulationMgrSpellSemantics::NowMs;

namespace
{
struct EquipmentSetRow
{
    bool Present = false;
    uint32 IgnoreMask = 0;
    std::array<uint32, EQUIPMENT_SLOT_END> Items = {};
};

// character_equipmentsets is provisioned (tools/raid_program/raid_loadout_sql.py)
// and never written during a run, so each set is read once per process.
EquipmentSetRow LoadEquipmentSet(uint32 guidLow, uint8 talentGroup)
{
    static std::mutex lock;
    static std::map<std::pair<uint32, uint8>, EquipmentSetRow> cache;
    {
        std::lock_guard<std::mutex> guard(lock);
        auto const itr = cache.find({ guidLow, talentGroup });
        if (itr != cache.end())
            return itr->second;
    }
    EquipmentSetRow row;
    if (QueryResult result = CharacterDatabase.PQuery(
            "SELECT ignore_mask, item0, item1, item2, item3, item4, item5, item6, item7, item8, item9, "
            "item10, item11, item12, item13, item14, item15, item16, item17, item18 "
            "FROM character_equipmentsets WHERE guid = %u AND setindex = %u LIMIT 1",
            guidLow, uint32(talentGroup)))
    {
        Field* fields = result->Fetch();
        row.Present = true;
        row.IgnoreMask = fields[0].GetUInt32();
        for (uint8 slot = 0; slot < EQUIPMENT_SLOT_END; ++slot)
            row.Items[slot] = fields[1 + slot].GetUInt32();
    }
    std::lock_guard<std::mutex> guard(lock);
    cache[{ guidLow, talentGroup }] = row;
    return row;
}

bool SetEquipped(Player const* bot, EquipmentSetRow const& set)
{
    for (uint8 slot = 0; slot < EQUIPMENT_SLOT_END; ++slot)
    {
        if (set.IgnoreMask & (1u << slot))
            continue;
        Item const* current = bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot);
        if (set.Items[slot] ? !current || current->GetGUID().GetCounter() != set.Items[slot] : current != nullptr)
            return false;
    }
    return true;
}
}

bool BotWorldPopulationMgr::EquipTalentGroupSet(Player* bot, uint8 talentGroup, bool& equipped,
    std::string& reason)
{
    equipped = false;
    if (!bot || !bot->GetSession())
    {
        reason = "equipment_set_owner_missing";
        return false;
    }
    EquipmentSetRow const set = LoadEquipmentSet(bot->GetGUID().GetCounter(), talentGroup);
    if (!set.Present)
    {
        reason = "equipment_set_missing:" + std::to_string(talentGroup);
        return false;
    }
    if (SetEquipped(bot, set))
    {
        equipped = true;
        return true;
    }

    // The client's packet: per equipment slot a packed item GUID (raw 1 =
    // ignored slot, 0 = leave the slot empty) and the item's source bag/slot.
    WorldPacket packet(CMSG_EQUIPMENT_SET_USE, EQUIPMENT_SLOT_END * 10);
    for (uint8 slot = 0; slot < EQUIPMENT_SLOT_END; ++slot)
    {
        ObjectGuid itemGuid;
        uint8 sourceBag = 0;
        uint8 sourceSlot = 0;
        if (set.IgnoreMask & (1u << slot))
            itemGuid = ObjectGuid(uint64(1));
        else if (set.Items[slot])
        {
            itemGuid = ObjectGuid::Create<HighGuid::Item>(set.Items[slot]);
            Item const* item = bot->GetItemByGuid(itemGuid);
            if (!item)
            {
                reason = "equipment_set_item_missing:" + std::to_string(slot);
                return false;
            }
            sourceBag = item->GetBagSlot();
            sourceSlot = item->GetSlot();
        }
        packet << itemGuid.WriteAsPacked() << uint8(sourceBag) << uint8(sourceSlot);
    }
    bot->GetSession()->HandleEquipmentSetUse(packet);
    equipped = SetEquipped(bot, set);
    if (!equipped)
        reason = "equipment_set_use_incomplete";
    return true;
}

bool BotWorldPopulationMgr::HasValidationRouteSpecContracts() const
{
    for (auto const& node : Party().ValidationRouteManifest)
        if (!node.SpecContract.empty())
            return true;
    return false;
}

bool BotWorldPopulationMgr::ActiveSpecContractRoleCounts(uint32& tanks, uint32& healers, uint32& dps,
    bool& switching) const
{
    switching = false;
    auto const& manifest = Party().ValidationRouteManifest;
    if (manifest.empty())
        return false;
    size_t const current = std::min<size_t>(Party().ValidationRouteManifestIndex, manifest.size() - 1);
    for (size_t index = current + 1; index-- > 0;)
    {
        if (manifest[index].SpecContract.empty())
            continue;
        switching = index == current;
        tanks = healers = dps = 0;
        for (BotRaidSpecSwitch::ContractRow const& row : manifest[index].SpecContract)
            ++(row.Role == "tank" ? tanks : (row.Role == "healer" ? healers : dps));
        return true;
    }
    return false;
}

// One member's step at the current spec-switch node. True while it is still
// switching (the caller holds its arrival); false once its wanted group is
// active, the group's set is equipped and its receipt is re-frozen.
bool BotWorldPopulationMgr::TryRaidSpecSwitch(WorldBotState& state, Player* bot,
    std::vector<BotRaidSpecSwitch::ContractRow> const& contract, std::string& action)
{
    namespace Switch = BotRaidSpecSwitch;
    uint64 const nowMs = NowMs();
    uint64 const generation = Party().ValidationRouteGeneration;
    if (state.SpecSwitchGeneration != generation)
    {
        state.SpecSwitchGeneration = generation;
        state.SpecSwitchSinceMs = 0;
        state.SpecSwitchLastAttemptMs = 0;
        state.SpecSwitchFromGroup = bot->GetActiveSpec();
    }
    uint32 const guid = bot->GetGUID().GetCounter();
    auto const roster = Cohort().Raid.RosterByGuid.find(guid);
    if (roster == Cohort().Raid.RosterByGuid.end())
    {
        action = "validation_route_spec_switch_roster_pending";
        return true;
    }
    Switch::ContractRow const* row = Switch::FindRow(contract, roster->second.SlotIndex + 1);
    if (!row)
    {
        FailValidationAttemptOnce(state, bot, "route_spec_contract_slot_missing:"
            + std::to_string(roster->second.SlotIndex + 1), generation);
        action = "validation_route_spec_switch_contract_invalid";
        return true;
    }
    BotActiveSpecIdentity::Groups groups;
    for (Switch::GroupIdentity const& group : row->TalentGroups)
        groups.push_back({ group.TalentGroup, { group.ClassSpec, group.Role } });
    BotActiveSpecIdentity::Register(guid, std::move(groups));
    if (bot->IsInCombat())
    {
        action = "validation_route_spec_switch_combat_hold";
        return true;
    }

    Switch::Observation in;
    in.ActiveGroup = bot->GetActiveSpec();
    in.WantedGroup = row->TalentGroup;
    in.Casting = bot->IsNonMeleeSpellCast(false);
    std::string equipReason;
    if (in.ActiveGroup == in.WantedGroup)
    {
        EquipmentSetRow const set = LoadEquipmentSet(guid, in.WantedGroup);
        if (!set.Present)
        {
            FailValidationAttemptOnce(state, bot, std::string(Switch::TimeoutPrefix) + std::to_string(guid)
                + ":equipment_set_missing:" + std::to_string(in.WantedGroup), generation);
            action = "validation_route_spec_switch_equipment_set_missing";
            return true;
        }
        in.SetEquipped = SetEquipped(bot, set);
    }
    auto const receipt = Cohort().Raid.AdmissionReceiptByGuid.find(guid);
    in.ReceiptCurrent = receipt != Cohort().Raid.AdmissionReceiptByGuid.end()
        && receipt->second.ActiveSpecIndex == in.ActiveGroup
        && receipt->second.ClassSpec == row->ClassSpec && receipt->second.Role == row->Role
        && state.RosterClassSpec == row->ClassSpec;
    in.RetryDue = !state.SpecSwitchLastAttemptMs
        || nowMs >= state.SpecSwitchLastAttemptMs + Switch::RetryIntervalMs;
    in.WaitingSinceMs = state.SpecSwitchSinceMs;
    in.NowMs = nowMs;
    Switch::Step const step = Switch::Decide(in);
    if (step == Switch::Step::Done)
    {
        state.SpecSwitchPending = false;
        state.SpecSwitchSinceMs = 0;
        return false;
    }
    if (!state.SpecSwitchSinceMs)
        state.SpecSwitchSinceMs = nowMs;

    std::string const raw = BuildRawJson(bot, nullptr);
    std::string const semantic = BuildSemanticJson(bot, nullptr, Switch::EventName);
    auto record = [&](std::string const& result, uint32 spellId = 0)
    {
        RecordEvent(state, bot, Switch::EventName, nullptr, result.c_str(), raw.c_str(), semantic.c_str(),
            float(nowMs - state.SpecSwitchSinceMs) / 1000.0f, uint32(row->TalentGroup), spellId);
    };
    std::string const transition = std::to_string(state.SpecSwitchFromGroup) + "->"
        + std::to_string(row->TalentGroup) + ":" + row->ClassSpec + ":" + row->Role;
    switch (step)
    {
        case Switch::Step::CastActivate:
        {
            state.SpecSwitchPending = true;
            state.SpecSwitchLastAttemptMs = nowMs;
            uint32 const spellId = Switch::ActivateSpellFor(row->TalentGroup);
            std::string failure;
            bool const submitted = TryCastFriendlySpell(bot, bot, spellId, &failure);
            record((submitted ? "activate_spec_cast_submitted:" : "activate_spec_cast_rejected:" + failure + ":")
                + transition, spellId);
            action = submitted ? "validation_route_spec_switch_cast" : "validation_route_spec_switch_cast_retry";
            return true;
        }
        case Switch::Step::AwaitCast:
            action = "validation_route_spec_switch_await";
            return true;
        case Switch::Step::EquipSet:
        {
            state.SpecSwitchPending = true;
            state.SpecSwitchLastAttemptMs = nowMs;
            bool equipped = false;
            bool const used = EquipTalentGroupSet(bot, row->TalentGroup, equipped, equipReason);
            record((equipped ? std::string("equipment_set_equipped:")
                : "equipment_set_pending:" + equipReason + ":") + transition);
            if (!used)
            {
                FailValidationAttemptOnce(state, bot, std::string(Switch::TimeoutPrefix)
                    + std::to_string(guid) + ":" + equipReason, generation);
                action = "validation_route_spec_switch_equipment_failed";
                return true;
            }
            action = "validation_route_spec_switch_equip";
            return true;
        }
        case Switch::Step::Refreeze:
        {
            std::string reason;
            if (!RefreezeAdmissionReceiptForSpecSwitch(state, bot, reason))
            {
                FailValidationAttemptOnce(state, bot, std::string(Switch::TimeoutPrefix)
                    + std::to_string(guid) + ":receipt:" + reason, generation);
                action = "validation_route_spec_switch_receipt_failed";
                return true;
            }
            state.SpecSwitchPending = false;
            record("spec_switch_receipted:" + transition);
            action = "validation_route_spec_switch_receipted";
            return true;
        }
        case Switch::Step::Timeout:
            FailValidationAttemptOnce(state, bot, std::string(Switch::TimeoutPrefix) + std::to_string(guid)
                + ":" + (in.ActiveGroup != in.WantedGroup ? "activate_spec" : "equipment_set"), generation);
            action = "validation_route_spec_switch_timeout";
            return true;
        case Switch::Step::Done:
            break;
    }
    return false;
}
