// Mail action layouts from pinned 60895 MailPackets; native handlers own outcomes.
#include "mail_actions.hpp"
#include "mail.hpp"
#include <limits>

namespace bridge
{
namespace
{
unsigned owned_mail(State const &owner,std::uint64_t id)
{
    if(!id || id>0xffffffff || !owner.mail_ids.contains(static_cast<unsigned>(id)))
        throw std::runtime_error("mail action requires an owned native catalog ID");
    return static_cast<unsigned>(id);
}
std::uint64_t active_mailbox(Protocol const &protocol,State const &owner)
{
    if(!owner.mail_target)throw std::runtime_error("mail action without a native mailbox catalog");
    return visible_mailbox(protocol,owner,Protocol::modern_guid(owner.mail_target,owner.map()));
}
}
Reply mail_action(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_MAIL_MARK_AS_READ" && name!="CMSG_MAIL_DELETE")return {};
    Reader r(body);auto target=active_mailbox(protocol,owner);Writer w;
    if(name=="CMSG_MAIL_MARK_AS_READ")
    {
        auto supplied=visible_mailbox(protocol,owner,r.guid());auto id=owned_mail(owner,r.take<std::uint64_t>());r.end();
        if(supplied!=target)throw std::runtime_error("mail read uses a different active mailbox");
        return Packet{name,w.pack("QI",{target,id}).finish()};
    }
    auto id=owned_mail(owner,r.take<std::uint64_t>());auto reason=r.take<std::int32_t>();r.end();
    // Native reads and ignores the final mailTemplateId; preserve the modern
    // reason there without inventing a gameplay outcome or bypassing its checks.
    return Packet{name,w.pack("QIi",{target,id,reason}).finish()};
}
Reply mail_command_result(Protocol const &protocol,State &owner,View body)
{
    Reader r(body);auto id=r.take<std::uint32_t>(),command=r.take<std::uint32_t>(),error=r.take<std::uint32_t>();
    if(command>5 || !(error<=6 || (error>=14 && error<=19) || error==21))
        throw std::runtime_error("unsupported native mail command result");
    Value bag=0;std::uint32_t attachment=0,quantity=0;
    if(error==1)
    {
        auto native=r.take<std::uint32_t>();auto mapped=protocol.inventory_results.as_object().if_contains(std::to_string(native));
        if(!mapped)throw std::runtime_error("unmapped native mail inventory result");
        bag=*mapped;
    }
    else if(command==2)
    {
        attachment=r.take<std::uint32_t>();quantity=r.take<std::uint32_t>();
        if(quantity>static_cast<unsigned>(std::numeric_limits<int>::max()))
            throw std::runtime_error("native mail attachment quantity exceeds modern bound");
    }
    r.end();
    if(command==4 && !error)owner.mail_ids.erase(id);
    return Packet{"SMSG_MAIL_COMMAND_RESULT",Writer().pack("QiiiQi",{id,command,error,bag,attachment,quantity}).finish()};
}
}
