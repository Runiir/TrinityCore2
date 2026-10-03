// Pinned BankPackets/NPCInteractionOpenResult; native NPCHandler remains authoritative.
#include "protocol.hpp"

namespace bridge
{
Reply Protocol::bank_request(State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_BANKER_ACTIVATE")return {};
    Reader r(body);auto identity=r.guid();auto interaction=r.take<std::int32_t>();r.end();
    if(interaction!=8)throw std::runtime_error("bank interaction has no native equivalent");
    auto guid=owned_unit(owner,identity);
    if(integer(get(owner.visible_units.at(guid),"kind"))!=3)
        throw std::runtime_error("bank activation requires a visible creature");
    return Packet{name,Writer().put(guid).finish()};
}
Reply Protocol::bank_response(State &owner,std::string const &name,View body) const
{
    if(name!="SMSG_SHOW_BANK")return {};
    Reader r(body);auto guid=r.take<std::uint64_t>();r.end();
    auto found=owner.visible_units.find(guid);
    if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(field(found->second,"UNIT_NPC_FLAGS")&0x20000))return {};
    owner.bank_target=guid;
    return Packet{"SMSG_NPC_INTERACTION_OPEN_RESULT",Writer()
        .guid(modern_guid(guid,integer(get(found->second,"map")))).put<std::int32_t>(8).bits(1,1).finish()};
}
bool Protocol::bank_close(State &owner,std::string const &name,View body)
{
    if(name!="CMSG_CLOSE_INTERACTION")return false;
    Reader r(body);auto identity=r.guid();r.end();
    if(owner.bank_target && identity==modern_guid(owner.bank_target,owner.map()))owner.bank_target=0;
    if(owner.mail_target && identity==modern_guid(owner.mail_target,owner.map()))owner.mail_target=0;
    if(owner.pending_mailbox && identity==modern_guid(owner.pending_mailbox,owner.map()))owner.pending_mailbox=0;
    // The legacy server has no matching close message. This modern notification
    // grants no authority and may arrive after logout or an NPC leaves visibility.
    return true;
}
} // namespace bridge
