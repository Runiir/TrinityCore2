// Native-authoritative mail reads, using pinned 60895 MailPackets schemas.
#include "mail.hpp"
#include "mail_actions.hpp"
#include <cmath>
#include <unordered_set>

namespace bridge
{
std::uint64_t visible_mailbox(Protocol const &protocol,State const &owner,Array const &identity)
{
    for(auto const &[guid,record]:owner.visible_gameobjects)
        if(identity==Protocol::modern_guid(guid,integer(get(record,"map"))) &&
           integer(get(record,"kind"))==5 && ((protocol.field(record,"GAMEOBJECT_BYTES_1")>>8)&255)==19)return guid;
    for(auto const &[guid,record]:owner.visible_units)
        if(identity==Protocol::modern_guid(guid,integer(get(record,"map"))) &&
           integer(get(record,"kind"))==3 && (protocol.field(record,"UNIT_NPC_FLAGS")&0x04000000))return guid;
    throw std::runtime_error("mail read requires a native visible mailbox");
}
namespace
{
Bytes text(Reader &r,unsigned maximum)
{
    Bytes output;
    for(unsigned i=0;i<=maximum;++i)
    {
        auto byte=r.take<std::uint8_t>();if(!byte)return output;
        output.push_back(byte);
    }
    throw std::runtime_error("native mail string exceeds modern bound");
}
bool sender_type(unsigned type)
{
    return type==0 || (type>=2 && type<=5);
}
Bytes attachment(Reader &r,unsigned expected_position)
{
    auto position=r.take<std::uint8_t>();auto guid=r.take<std::uint32_t>(),entry=r.take<std::uint32_t>();
    std::vector<Array> enchants;
    for(unsigned slot=0;slot<10;++slot)
    {
        auto values=r.unpack("3I");
        if(truth(values[0]))enchants.push_back(Array{values[0],values[1],values[2],slot});
        else if(truth(values[1]) || truth(values[2]))throw std::runtime_error("native mail enchant metadata without enchant");
    }
    auto property=r.take<std::int32_t>();auto seed=r.take<std::uint32_t>(),count=r.take<std::uint32_t>();
    auto charges=r.take<std::int32_t>();auto maximum=r.take<std::uint32_t>(),durability=r.take<std::uint32_t>();
    auto unlocked=r.take<std::uint8_t>();
    if(position!=expected_position || !guid || !entry || entry>0x7fffffff || !count || count>0x7fffffff ||
       maximum>0x7fffffff || durability>maximum || unlocked>1)
        throw std::runtime_error("invalid native mail attachment");
    Writer w;w.pack("BQiiIi",{position,guid,count,charges,maximum,durability});
    // Native socket enchant IDs do not identify the underlying gem items. The
    // native enchant metadata is preserved; modern gem instances remain empty.
    w.pack("iIi",{entry,seed,property}).bits(0,1).flush().bits(0,6).flush();
    w.bits(enchants.size(),4).bits(0,2).bits(unlocked,1).flush();
    for(auto const &enchant:enchants)w.pack("3IB",enchant);
    return w.finish();
}
Bytes list(State &owner,View body)
{
    if(body.size()>32767)throw std::runtime_error("native mailbox packet exceeds bound");
    Reader r(body);auto total=r.take<std::uint32_t>();auto count=r.take<std::uint8_t>();
    if(count>50 || total<count || total>0x7fffffff)throw std::runtime_error("invalid native mailbox count");
    Writer w;w.pack("Ii",{count,total});std::unordered_set<unsigned> seen,senders;
    for(unsigned index=0;index<count;++index)
    {
        auto before=r.remaining();auto declared=r.take<std::uint16_t>();
        auto id=r.take<std::uint32_t>();auto type=r.take<std::uint8_t>();
        if(!id || !seen.insert(id).second || !sender_type(type))throw std::runtime_error("invalid native mail identity");
        std::uint64_t sender=type==0?r.take<std::uint64_t>():r.take<std::uint32_t>();
        if(type==0 && sender>>32)throw std::runtime_error("invalid native mail player sender");
        if(type==3 && sender && sender<=0x7fffffff)senders.insert(sender);
        auto cod=r.take<std::uint64_t>();auto package=r.take<std::uint32_t>(),stationery=r.take<std::uint32_t>();
        auto money=r.take<std::uint64_t>();auto flags=r.take<std::uint32_t>();auto days=r.take<float>();
        auto template_id=r.take<std::uint32_t>();auto subject=text(r,255),message=text(r,8191);
        auto items=r.take<std::uint8_t>();
        if(package || !std::isfinite(days) || items>12)throw std::runtime_error("unsupported native mail metadata");
        std::vector<Bytes> attachments;
        for(unsigned item=0;item<items;++item)attachments.push_back(attachment(r,item));
        auto actual=before-r.remaining();
        // This checkout's size formula predates the two 64-bit money fields
        // and undercounts each entry by four bytes. Parse fields independently.
        if(declared!=actual && static_cast<unsigned>(declared)+4!=actual)
            throw std::runtime_error("native mail entry size disagrees with parsed fields");
        w.pack("QIQIQIfII",{id,type,cod,stationery,money,flags,days,template_id,items});
        if(type==0)w.guid(sender,sender?player_high():0);else w.put<std::uint32_t>(sender);
        w.bits(subject.size(),8).bits(message.size(),13).flush();
        for(auto const &item:attachments)w.raw(item);
        w.raw(subject).raw(message);
    }
    r.end();owner.mail_creatures=std::move(senders);owner.mail_ids=std::move(seen);
    if(owner.pending_mailbox)
    {
        owner.mail_target=owner.pending_mailbox;owner.pending_mailbox=0;
    }
    return w.finish();
}
}
Reply mail_request(Protocol const &protocol,State &owner,std::string const &name,View body)
{
    if(name=="CMSG_QUERY_NEXT_MAIL_TIME")
    {Reader r(body);r.end();return Packet{"MSG_QUERY_NEXT_MAIL_TIME",{}};}
    if(auto action=mail_action(protocol,owner,name,body))return action;
    if(name!="CMSG_MAIL_GET_LIST")return {};
    Reader r(body);auto guid=visible_mailbox(protocol,owner,r.guid());r.end();owner.pending_mailbox=guid;
    return Packet{"CMSG_GET_MAIL_LIST",Writer().put(guid).finish()};
}
Reply mail_response(Protocol const &protocol,State &owner,std::string const &name,View body)
{
    if(name=="SMSG_MAIL_LIST_RESULT")return Packet{name,list(owner,body)};
    if(name=="SMSG_SEND_MAIL_RESULT")return mail_command_result(protocol,owner,body);
    Reader r(body);
    if(name=="SMSG_SHOW_MAILBOX")
    {
        auto guid=r.take<std::uint64_t>();r.end();auto identity=Protocol::modern_guid(guid,owner.map());
        visible_mailbox(protocol,owner,identity);
        return Packet{"SMSG_NPC_INTERACTION_OPEN_RESULT",Writer().guid(identity).put<std::int32_t>(17).bits(1,1).finish()};
    }
    if(name=="SMSG_RECEIVED_MAIL")
    {
        if(r.take<std::uint32_t>()!=0)throw std::runtime_error("unsupported native received-mail delay");r.end();
        return Packet{"SMSG_NOTIFY_RECEIVED_MAIL",Writer().put<float>(0).finish()};
    }
    if(name!="MSG_QUERY_NEXT_MAIL_TIME")return {};
    auto next=r.take<float>();auto count=r.take<std::uint32_t>();
    if(!std::isfinite(next) || count>2)throw std::runtime_error("invalid native next-mail count or time");
    Writer w;w.pack("fI",{next,count});
    for(unsigned index=0;index<count;++index)
    {
        auto guid=r.take<std::uint64_t>();auto alt=r.take<std::uint32_t>(),type=r.take<std::uint32_t>(),stationery=r.take<std::uint32_t>();
        auto delay=r.take<float>();
        if(!sender_type(type) || !std::isfinite(delay) || (type==0?(guid>>32)!=0:guid!=0))
            throw std::runtime_error("invalid native next-mail sender");
        w.guid(guid,guid?player_high():0).pack("fIBI",{delay,alt,type,stationery});
    }
    r.end();return Packet{"SMSG_MAIL_QUERY_NEXT_TIME_RESULT",w.finish()};
}
}
