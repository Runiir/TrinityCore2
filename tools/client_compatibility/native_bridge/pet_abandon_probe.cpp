#include "pet_abandon_probe.hpp"
#include "protocol.hpp"
#include "crypto.hpp"
#include <algorithm>
#include <fstream>

namespace bridge
{
namespace
{
bool tamed_source(std::filesystem::path const &root,Value const &config,double created)
{
    auto ref=get(config,"tame_source");std::filesystem::path relative=str(get(ref,"path"));
    if(relative.is_absolute())return false;
    auto path=root/relative;auto base=std::filesystem::weakly_canonical(root/"evidence");
    auto inside=std::filesystem::weakly_canonical(path).lexically_relative(base);
    if(inside.empty() || *inside.begin()==".." || path.filename()!="episode.json" ||
        std::filesystem::is_symlink(path) || !std::filesystem::is_regular_file(path) ||
        std::filesystem::file_size(path)>1024*1024)return false;
    std::ifstream file(path,std::ios::binary);Bytes data((std::istreambuf_iterator<char>(file)),{});
    if(!file || hex(hash(data,"SHA256"))!=str(get(ref,"sha256")))return false;
    auto e=json::parse(std::string_view(reinterpret_cast<char const *>(data.data()),data.size()));
    for(auto key:{"completed","input_sent","capture_disarmed"})
        if(!get(e,key).is_bool() || !get(e,key).as_bool())return false;
    if(!get(e,"qualification_added").is_bool() || get(e,"qualification_added").as_bool())return false;
    auto checks=get(e,"capture_checks");auto pet_number=integer(get(config,"pet_number"));
    if(pet_number<=4 || pet_number>=0x80000000u || !truth(get(e,"completed")) || !get(e,"failure").is_null() ||
        str(get(e,"phase"))!="owned_tame_native_outcome_captured" || !truth(get(e,"input_sent")) ||
        !truth(get(e,"capture_disarmed")) || truth(get(e,"qualification_added")) ||
        !get(e,"model").is_null() || integer(get(get(e,"actor"),"guid"))!=6 ||
        integer(get(get(e,"actor"),"class"))!=3 || integer(get(get(e,"actor"),"account_id"))!=2 ||
        integer(get(get(e,"actor"),"level"))!=10 ||
        number(get(e,"finished_at"))<=0 || number(get(e,"finished_at"))>=created ||
        !checks.is_object() || checks.as_object().size()!=14)return false;
    for(auto const &check:checks.as_object())if(!check.value().is_bool() || !check.value().as_bool())return false;
    auto fields=get(get(e,"native_pet_after"),"fields");
    if(integer(get(fields,"69"))!=pet_number || integer(get(fields,"5"))!=299 || integer(get(fields,"18"))!=6)return false;
    auto rows=get(e,"retained_pet_after");if(!rows.is_array() || rows.as_array().size()!=2)return false;
    bool wolf=false,named=false;
    for(auto const &row:rows.as_array())
    {
        if(integer(get(row,"id"))==4 && integer(get(row,"owner"))==6 && integer(get(row,"entry"))==42717 &&
            str(get(row,"name"))=="Harnesswolf" && integer(get(row,"slot"))==5 && !truth(get(row,"active")))named=true;
        if(integer(get(row,"id"))==pet_number && integer(get(row,"owner"))==6 && integer(get(row,"entry"))==299 &&
            str(get(row,"name"))=="Wolf" && integer(get(row,"slot"))==0 && integer(get(row,"active"))==1 &&
            integer(get(row,"CreatedBySpell"))==13481)wolf=true;
    }
    return named && wolf;
}
}
bool owned_pet_abandon_probe(std::filesystem::path const &root,std::string const &direction,
    std::string const &name,View body,std::string const &session,double now)
{
    if(name!="CMSG_PET_ABANDON" || (direction!="from_client" && direction!="to_native"))return false;
    try
    {
        auto path=root/"run/owned_pet_abandon_probe.json";
        if(!std::filesystem::is_regular_file(path) || std::filesystem::file_size(path)>4096)return false;
        auto c=load_json(path);auto created=number(get(c,"created_at")),expires=number(get(c,"expires_at"));
        auto schema=str(get(c,"schema"));
        if(integer(get(c,"owner"))!=6 || str(get(c,"session"))!=session ||
           created>now || expires<=now || expires<=created || expires-created>90)return false;
        if(schema=="client442_owned_pet_abandon_probe_v1")
        {if(integer(get(c,"pet_number"))!=6)return false;}
        else if(schema=="client442_owned_pet_abandon_probe_v2")
        {if(!tamed_source(root,c,created))return false;}
        else return false;
        auto guid=integer(get(c,"native_pet_guid"));
        if(guid>>52!=0xf14 || ((guid>>32)&0xfffff)!=299 ||
           get(c,"modern_pet_guid")!=Protocol::modern_guid(guid,0))return false;
        auto canonical=direction=="from_client" ? Writer().guid(Protocol::modern_guid(guid,0)).finish() :
            Writer().put<std::uint64_t>(guid).finish();
        return body.size()==canonical.size() && std::equal(body.begin(),body.end(),canonical.begin());
    }
    catch(std::exception const &) {return false;}
}
}
