// Observe the two fixed-width requests from the attributable offline reentry stall.
// Their contents are unknown. This module neither interprets nor forwards them.
#include "entry_probe.hpp"
#include "crypto.hpp"
#include <cmath>
#include <fstream>

namespace bridge
{
namespace
{
bool owned_entry_source(std::filesystem::path const &root,Value const &c,double created)
{
    auto ref=get(c,"entry_source");std::filesystem::path relative=str(get(ref,"path"));
    if(relative.is_absolute())return false;
    auto path=root/relative;auto base=std::filesystem::weakly_canonical(root/"evidence");
    auto inside=std::filesystem::weakly_canonical(path).lexically_relative(base);
    if(inside.empty() || *inside.begin()==".." || path.filename()!="episode.json" ||
        std::filesystem::is_symlink(path) || !std::filesystem::is_regular_file(path) ||
        std::filesystem::file_size(path)>1024*1024)return false;
    std::ifstream file(path,std::ios::binary);Bytes data((std::istreambuf_iterator<char>(file)),{});
    if(!file || hex(hash(data,"SHA256"))!=str(get(ref,"sha256")))return false;
    auto e=json::parse(std::string_view(reinterpret_cast<char const *>(data.data()),data.size()));
    auto checks=get(e,"checks"),a=get(e,"actor");
    if(!get(e,"completed").is_bool() || !get(e,"completed").as_bool() || !get(e,"failure").is_null() ||
        str(get(e,"phase"))!="owned_class_entered" || !get(e,"model").is_null() ||
        integer(get(a,"guid"))!=6 || integer(get(a,"account_id"))!=2 || integer(get(a,"class"))!=3 ||
        integer(get(a,"level"))!=10 || str(get(e,"native_session"))!=str(get(c,"session")) ||
        get(e,"runtime")!=get(c,"runtime") || number(get(e,"finished_at"))<=0 ||
        number(get(e,"finished_at"))>=created || !checks.is_object() || checks.as_object().size()!=9)return false;
    for(auto const &check:checks.as_object())if(!check.value().is_bool() || !check.value().as_bool())return false;
    return true;
}
}
bool owned_entry_probe(std::filesystem::path const &root,std::string const &direction,
    std::string const &name,View body,std::string const &session,double now)
{
    if(direction!="from_client" || body.size()!=5 ||
        (name!="CMSG_LOADING_SCREEN_NOTIFY" && name!="CMSG_GET_ACCOUNT_CHARACTER_LIST"))return false;
    try
    {
        auto path=root/"run/owned_entry_request_probe.json";
        if(std::filesystem::is_symlink(path) || !std::filesystem::is_regular_file(path) ||
            std::filesystem::file_size(path)>4096)return false;
        auto c=load_json(path);auto created=number(get(c,"created_at")),expires=number(get(c,"expires_at"));
        if(!std::isfinite(now) || !std::isfinite(created) || !std::isfinite(expires) ||
            str(get(c,"schema"))!="client442_owned_entry_request_probe_v1" ||
            integer(get(c,"owner"))!=6 || integer(get(c,"account_id"))!=2 ||
            str(get(c,"session"))!=session || created>now || expires<=now ||
            expires<=created || expires-created>120 || !owned_entry_source(root,c,created))return false;
        return true;
    }
    catch(std::exception const &){return false;}
}
}
