// Pinned modern SendMail and native 15595 MailHandler bit/octet order.
#include "mail_send.hpp"
#include "mail.hpp"
#include <algorithm>

namespace bridge
{
Reply mail_send(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_SEND_MAIL")return {};
    Reader r(body);auto target=visible_mailbox(protocol,owner,r.guid());
    if(!owner.mail_target || target!=owner.mail_target)
        throw std::runtime_error("sending mail requires a native mailbox catalog");
    auto stationery=r.take<std::int32_t>();auto money=r.take<std::int64_t>(),cod=r.take<std::int64_t>();
    auto target_length=r.bits(9),subject_length=r.bits(9),body_length=r.bits(11),count=r.bits(5);r.align();
    if(stationery<0 || money<0 || cod<0 || !target_length || target_length>127 || count>16)
        throw std::runtime_error("mail send metadata exceeds native bounds");
    auto receiver=r.raw(target_length),subject=r.raw(subject_length),message=r.raw(body_length);
    for(auto text:{receiver,subject,message})
        if(std::find(text.begin(),text.end(),0)!=text.end())throw std::runtime_error("mail send string contains NUL");
    struct Attached {std::uint8_t position;Bytes guid;};std::vector<Attached> items;
    std::unordered_set<std::uint64_t> seen;
    for(unsigned index=0;index<count;++index)
    {
        auto position=r.take<std::uint8_t>();auto identity=r.guid();auto low=integer(identity[0]);
        auto native=(0x4000ull<<48)|low;
        if(!low || low>0xffffffff || integer(identity[1])!=((3ull<<58)|(1ull<<42)) ||
           !owner.inventory_items.contains(native) || !seen.insert(native).second)
            throw std::runtime_error("mail attachment is outside owned inventory or duplicated");
        items.push_back({position,Writer().put(native).finish()});
    }
    r.end();auto mailbox=Writer().put(target).finish();Writer w;
    auto mask=[&](Bytes const &guid,std::initializer_list<unsigned> order)
    {for(auto index:order)w.bits(guid[index]!=0,1);};
    auto octets=[&](Bytes const &guid,std::initializer_list<unsigned> order)
    {for(auto index:order)if(guid[index])w.put<std::uint8_t>(guid[index]^1);};
    w.pack("2I2Q",{0,stationery,cod,money}).bits(body_length,12).bits(subject_length,9).bits(count,5);
    mask(mailbox,{0});
    for(auto const &item:items)mask(item.guid,{2,6,3,7,1,0,4,5});
    mask(mailbox,{3,4});w.bits(target_length,7);mask(mailbox,{2,6,1,7,5});w.flush();
    octets(mailbox,{4});
    for(auto const &item:items)
    {
        octets(item.guid,{6,1,7,2});w.put(item.position);octets(item.guid,{3,0,4,5});
    }
    octets(mailbox,{7,3,6,5});w.raw(subject).raw(receiver);octets(mailbox,{2,0});
    w.raw(message);octets(mailbox,{1});
    // The modern UI offers 16 slots. Native's 12-attachment limit is a native
    // gameplay error, not a reason to disconnect an otherwise valid client.
    // Native owns name resolution, self/team/level checks, postage, delivery,
    // capacity, inventory eligibility, balances and COD semantics.
    return Packet{name,w.finish()};
}
}
