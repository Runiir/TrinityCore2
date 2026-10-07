#include "stable_probe.hpp"
#include "protocol.hpp"
#include "stables.hpp"

namespace bridge
{
bool owned_stable_request_probe(std::filesystem::path const &root, std::string const &direction,
    std::string const &name, View body, std::string const &session, double now)
{
    bool request=name=="CMSG_REQUEST_STABLED_PETS" && direction=="from_client";
    bool catalog=name=="MSG_LIST_STABLED_PETS" && direction=="from_native";
    bool slot=name=="CMSG_SET_PET_SLOT" && (direction=="from_client" || direction=="to_native");
    bool update=name=="SMSG_PET_SLOT_UPDATED" && direction=="from_native";
    bool result=(name=="SMSG_STABLE_RESULT" && direction=="from_native") ||
        (name=="SMSG_PET_STABLE_RESULT" && direction=="to_client");
    if(!request && !catalog && !slot && !update && !result)return false;
    try
    {
        auto path=root/"run/owned_stable_request_probe.json";
        if(!std::filesystem::is_regular_file(path) || std::filesystem::file_size(path)>4096)return false;
        auto config=load_json(path);
        if(str(get(config,"schema"))!="client442_owned_stable_request_probe_v1" ||
           str(get(config,"session"))!=session || integer(get(config,"owner"))!=6)return false;
        auto created=number(get(config,"created_at")),expires=number(get(config,"expires_at"));
        if(created>now || expires<=now || expires<=created || expires-created>120)return false;
        auto native=integer(get(config,"native_master_guid"));
        if(native>>52!=0xf13 || ((native>>32)&0xfffff)!=6749 || !(native&0xffffffff) ||
           get(config,"modern_master_guid")!=Protocol::modern_guid(native,0))return false;
        if(catalog)return integer(get(native_stable_list(body),"native_master"))==native;
        Reader r(body);
        if(slot || update || result)
        {
            auto const &scope=get(config,"slot_roundtrip");
            auto const &swap_scope=get(config,"slot_swap");
            bool pair=swap_scope.is_object() && get(swap_scope,"pet_numbers")==Array{4,6} &&
                get(swap_scope,"slots")==Array{0,5} && !scope.is_object();
            bool single=scope.is_object() && integer(get(scope,"pet_number"))==4 &&
                get(scope,"slots")==Array{0,5} && !swap_scope.is_object();
            if(!pair && !single)return false;
            if(slot)
            {
                auto number=r.take<std::uint32_t>();if(number!=4 && !(pair && number==6))return false;
                auto destination=r.take<std::uint8_t>();if(destination!=0 && destination!=5)return false;
                if(direction=="from_client") {if(r.guid()!=get(config,"modern_master_guid"))return false;}
                else
                {
                    std::array<std::uint8_t,8> octets{};
                    for(auto i:{3,2,0,7,5,6,1,4})octets[i]=r.bits(1);
                    for(auto i:{5,3,1,7,4,0,6,2})if(octets[i])octets[i]=r.take<std::uint8_t>()^1;
                    std::uint64_t guid=0;std::memcpy(&guid,octets.data(),8);if(guid!=native)return false;
                }
            }
            else if(update)
            {
                auto number=r.take<std::uint32_t>(),destination=r.take<std::uint32_t>();
                auto swap=r.take<std::uint32_t>(),source=r.take<std::uint32_t>();
                if(!((source==0 && destination==5) || (source==5 && destination==0)))return false;
                if(pair ? !((number==4 && swap==6) || (number==6 && swap==4)) : (number!=4 || swap))return false;
            }
            else
            {
                auto code=r.take<std::uint8_t>();
                if(code!=1 && code!=3 && code!=8 && code!=9 && code!=11 && code!=12)return false;
            }
            r.end();return true;
        }
        if(r.guid()!=get(config,"modern_master_guid"))return false;
        r.end();return true;
    }
    catch(std::exception const &) {return false;}
}
}
