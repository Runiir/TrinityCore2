#ifndef TRINITY_BOT_EXPERIENCE_LEARNING_POLICY_FLAG_H
#define TRINITY_BOT_EXPERIENCE_LEARNING_POLICY_FLAG_H

#include <atomic>
#include <string>

// A boolean config value read once per config load. Hot paths (every learned
// score, every semantic event) call Get(), which reads the source only while
// the flag is still unloaded; Refresh() re-reads it on config load/reload.
// ConfigMgr logs a warning on every lookup of an absent key, so a per-call
// lookup would flood the console of any run whose config omits the key.
class BotCachedConfigFlag final
{
public:
    template <class Read>
    bool Get(Read&& read)
    {
        int state = _state.load(std::memory_order_acquire);
        if (state < 0)
        {
            Refresh(read);
            state = _state.load(std::memory_order_acquire);
        }
        return state == 1;
    }

    template <class Read>
    void Refresh(Read&& read)
    {
        _state.store(read() ? 1 : 0, std::memory_order_release);
    }

private:
    std::atomic<int> _state{ -1 };
};

// Reads an optional boolean key. ConfigMgr warns on every lookup of an absent
// key, so presence is checked first: an absent key is false and silent.
template <class Config>
bool ReadOptionalConfigBool(Config& config, std::string const& key)
{
    for (std::string const& present : config.GetKeysByString(key))
        if (present == key)
            return config.GetBoolDefault(key, false);
    return false;
}

#endif
