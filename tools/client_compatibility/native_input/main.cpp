// Owned Gamescope libei sender. Never connects to the host input server.
#include "json.hpp"
#include <libei.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <poll.h>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>

using namespace bridge;
namespace
{
std::string start_ticks(pid_t pid)
{
    std::ifstream f("/proc/"+std::to_string(pid)+"/stat");std::string line,word;
    if(!std::getline(f,line))throw std::runtime_error("input owner is absent");
    auto pos=line.rfind(')');if(pos==std::string::npos)throw std::runtime_error("invalid owner stat");
    std::istringstream fields(line.substr(pos+2));
    for(unsigned i=0;i<=19;++i)if(!(fields>>word))throw std::runtime_error("invalid owner lifetime");
    return word;
}
struct Sender
{
    ei *context=nullptr;
    ei_device *device=nullptr;
    bool ready=false;
    unsigned sequence=0;
    std::set<unsigned> keys,buttons;
    Sender(char const *path,pid_t owner,std::string const &ticks)
    {
        if(start_ticks(owner)!=ticks)throw std::runtime_error("input owner lifetime changed");
        sockaddr_un address{};address.sun_family=AF_UNIX;
        if(path[0]!='/' || std::strlen(path)>=sizeof(address.sun_path))throw std::runtime_error("require a bounded absolute private socket");
        std::strcpy(address.sun_path,path);
        int fd=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0);
        if(fd<0)throw std::runtime_error("cannot create private input socket");
        if(connect(fd,reinterpret_cast<sockaddr*>(&address),sizeof(address))<0)
        {close(fd);throw std::runtime_error("cannot connect private input socket");}
        ucred peer{};socklen_t size=sizeof(peer);
        if(getsockopt(fd,SOL_SOCKET,SO_PEERCRED,&peer,&size)<0 || peer.pid!=owner ||
            peer.uid!=getuid() || start_ticks(owner)!=ticks)
        {close(fd);throw std::runtime_error("private input socket belongs to another process or lifetime");}
        context=ei_new_sender(nullptr);
        if(!context){close(fd);throw std::runtime_error("cannot allocate EI sender");}
        ei_configure_name(context,"Trinity isolated client harness");
        if(ei_setup_backend_fd(context,fd)<0)
        {ei_unref(context);context=nullptr;throw std::runtime_error("cannot initialize owned EI connection");}
    }
    ~Sender()
    {
        if(device)
        {
            if(ready)
            {
                for(auto key:keys)ei_device_keyboard_key(device,key,false);
                for(auto button:buttons)ei_device_button_button(device,button,false);
                ei_device_frame(device,ei_now(context));ei_device_stop_emulating(device);
                ei_dispatch(context);
            }
            ei_device_unref(device);
        }
        if(context)ei_unref(context);
    }
    void dispatch()
    {
        ei_dispatch(context);
        while(auto event=ei_get_event(context))
        {
            auto type=ei_event_get_type(event);
            if(type==EI_EVENT_DISCONNECT)
            {ei_event_unref(event);throw std::runtime_error("owned input server disconnected");}
            if(type==EI_EVENT_SEAT_ADDED)
                ei_seat_bind_capabilities(ei_event_get_seat(event),EI_DEVICE_CAP_POINTER_ABSOLUTE,
                    EI_DEVICE_CAP_KEYBOARD,EI_DEVICE_CAP_BUTTON,EI_DEVICE_CAP_SCROLL,nullptr);
            if(type==EI_EVENT_DEVICE_RESUMED)
            {
                auto candidate=ei_event_get_device(event);
                if(ei_device_has_capability(candidate,EI_DEVICE_CAP_POINTER_ABSOLUTE) &&
                    ei_device_has_capability(candidate,EI_DEVICE_CAP_KEYBOARD) &&
                    ei_device_has_capability(candidate,EI_DEVICE_CAP_BUTTON))
                {
                    if(device && device!=candidate)
                    {ei_event_unref(event);throw std::runtime_error("multiple input devices are unsupported");}
                    if(!device)device=ei_device_ref(candidate);
                    ei_device_start_emulating(device,++sequence);ready=true;
                }
            }
            if((type==EI_EVENT_DEVICE_PAUSED || type==EI_EVENT_DEVICE_REMOVED) &&
                ei_event_get_device(event)==device)
            {
                ready=false;keys.clear();buttons.clear();
                ei_event_unref(event);throw std::runtime_error("owned input device became unavailable");
            }
            ei_event_unref(event);
        }
    }
    void await_ready()
    {
        auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);
        while(!ready)
        {
            dispatch();if(ready)break;
            if(std::chrono::steady_clock::now()>deadline)throw std::runtime_error("owned input device readiness timed out");
            pollfd fd{ei_get_fd(context),POLLIN,0};poll(&fd,1,50);
        }
        ei_dispatch(context);
    }
    void send(Value const &request)
    {
        dispatch();if(!ready)throw std::runtime_error("owned input device is not ready");
        auto kind=str(get(request,"kind"));
        if(kind=="move")
        {
            auto x=signed_integer(get(request,"x")),y=signed_integer(get(request,"y"));
            if(x<0 || x>=1280 || y<0 || y>=720)throw std::runtime_error("pointer is outside the owned client");
            ei_device_pointer_motion_absolute(device,x,y);
        }
        else if(kind=="key")
        {
            auto code=integer(get(request,"code"));bool pressed=truth(get(request,"pressed"));
            if(code<8 || code>255)throw std::runtime_error("invalid XKB keycode");
            unsigned key=code-8;
            if(pressed){if(keys.insert(key).second)ei_device_keyboard_key(device,key,true);}
            else if(keys.erase(key))ei_device_keyboard_key(device,key,false);
        }
        else if(kind=="button")
        {
            auto code=integer(get(request,"code"));bool pressed=truth(get(request,"pressed"));
            if(code<1 || code>5)throw std::runtime_error("unsupported mouse button");
            if(code>=4)
            {
                if(pressed)
                {
                    if(!ei_device_has_capability(device,EI_DEVICE_CAP_SCROLL))throw std::runtime_error("scroll capability is unavailable");
                    ei_device_scroll_discrete(device,0,code==4?-120:120);
                }
            }
            else
            {
                unsigned button=code==1?272:code==2?274:273;
                if(pressed){if(buttons.insert(button).second)ei_device_button_button(device,button,true);}
                else if(buttons.erase(button))ei_device_button_button(device,button,false);
            }
        }
        else throw std::runtime_error("unsupported native input operation");
        ei_device_frame(device,ei_now(context));ei_dispatch(context);
    }
};
}
int main(int argc,char **argv)
{
    try
    {
        if(argc!=4)throw std::runtime_error("require private socket, owned PID and start ticks");
        auto pid=std::stoll(argv[2]);if(pid<=1 || pid>INT32_MAX)throw std::runtime_error("invalid owned PID");
        Sender sender(argv[1],pid,argv[3]);sender.await_ready();
        std::cout<<json::serialize(Object{{"ready",true},{"engine","cpp_libei"},{"peer_pid",pid}})<<std::endl;
        while(true)
        {
            pollfd fds[]={{ei_get_fd(sender.context),POLLIN,0},{STDIN_FILENO,POLLIN,0}};
            if(poll(fds,2,-1)<0)throw std::runtime_error("native input poll failed");
            if(fds[0].revents)sender.dispatch();
            if(fds[1].revents&(POLLIN|POLLHUP))
            {
                std::string line;if(!std::getline(std::cin,line))break;
                if(line.size()>1024)throw std::runtime_error("input request exceeds bound");
                sender.send(json::parse(line));std::cout<<"{\"ok\":true}"<<std::endl;
            }
        }
        return 0;
    }
    catch(std::exception const &error)
    {std::cout<<json::serialize(Object{{"error",error.what()}})<<std::endl;return 1;}
}
