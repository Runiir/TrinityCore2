#include "fields.hpp"
#include <functional>
#include <regex>

namespace bridge
{
namespace
{
using Variables = std::unordered_map<std::string, Value>;
using Expression = std::function<Value(Value const &, Variables const &)>;
std::string trim(std::string s)
{
    auto begin = s.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos)
        return {};
    return s.substr(begin, s.find_last_not_of(" \t\r\n") - begin + 1);
}
Expression expression(std::string text)
{
    text = trim(text);
    if (text.starts_with('(') && text.ends_with(')'))
        return expression(text.substr(1, text.size() - 2));
    for (auto pos = text.find("->"); pos != std::string::npos; pos = text.find("->"))
        text.replace(pos, 2, ".");
    std::smatch match;
    if (std::regex_match(text, match,
                         std::regex(R"(ViewerDependentValue<(\w+)Tag>::GetValue\(this, owner, receiver\))")))
    {
        auto key = match[1].str();
        return [key](Value const &values, Variables const &) { return get(values, key); };
    }
    if (std::regex_match(text, match, std::regex(R"((.+)\.size\(\))")))
    {
        auto inner = expression(match[1]);
        return [inner](Value const &v, Variables const &vars) -> Value
        {
            auto value = inner(v, vars);
            return value.is_array()    ? value.as_array().size()
                   : value.is_string() ? value.as_string().size()
                                       : 0;
        };
    }
    if (std::regex_match(text, match, std::regex(R"((.+)\.has_value\(\))")))
    {
        auto inner = expression(match[1]);
        return [inner](Value const &v, Variables const &vars) -> Value { return truth(inner(v, vars)); };
    }
    if (text == "false" || text == "true")
        return [v = text == "true"](auto const &, auto const &) -> Value { return v; };
    if (std::regex_match(text, std::regex(R"(-?\d+(?:\.\d+)?f?)")))
    {
        Value literal =
            text.find('.') != std::string::npos ? Value(std::stod(text)) : Value(std::stoll(text));
        return [literal](auto const &, auto const &) { return literal; };
    }
    if (text.starts_with('*'))
        return expression(text.substr(1));
    if (std::regex_match(text, match, std::regex(R"((.+)\[(\w+)\])")))
    {
        auto array = expression(match[1]), index = expression(match[2]);
        return [array, index](Value const &v, Variables const &vars) -> Value
        {
            auto a = array(v, vars);
            auto i = integer(index(v, vars));
            return a.is_array() && i < a.as_array().size() ? a.as_array()[i] : Value(0);
        };
    }
    if (std::regex_match(text, match, std::regex(R"((\w+)\.(\w+))")))
    {
        auto base = expression(match[1]);
        auto field = match[2].str();
        return [base, field](Value const &v, Variables const &vars) { return get(base(v, vars), field); };
    }
    if (std::regex_match(text, std::regex(R"(\w+)")))
        return [text](Value const &v, Variables const &vars) -> Value
        {
            auto p = vars.find(text);
            return p != vars.end() ? p->second : get(v, text);
        };
    return [text](Value const &, Variables const &) -> Value
    { throw std::runtime_error("unsupported create-field expression: " + text); };
}
std::unordered_map<std::string, char> const scalar = {{"int8", 'b'},   {"uint8", 'B'},  {"int16", 'h'},
                                                      {"uint16", 'H'}, {"int32", 'i'},  {"uint32", 'I'},
                                                      {"int64", 'q'},  {"uint64", 'Q'}, {"float", 'f'}};
struct Node
{
    enum Kind
    {
        Loop,
        Condition,
        Flush,
        Bits,
        String,
        Scalar,
        Nested,
        Guid,
        Dungeon,
        Perks,
        Bonus,
        EmptyEffects,
        Unsupported
    } kind;
    Expression value;
    std::string name;
    unsigned width = 0, mask = 0;
    char format = 0;
    std::vector<Node> children;
};
std::vector<Node> compile(Array const &lines, Object const &types, std::size_t &pos, bool nested = false)
{
    std::vector<Node> result;
    while (pos < lines.size())
    {
        auto line = str(lines[pos++]);
        if (line == "}")
        {
            if (!nested)
                throw std::runtime_error("unmatched schema brace");
            return result;
        }
        if (line == "{")
        {
            auto group = compile(lines, types, pos, true);
            result.insert(result.end(), group.begin(), group.end());
            continue;
        }
        std::smatch m;
        Node n{};
        if (std::regex_match(line, m, std::regex(R"(for \(uint32 (\w+) = 0; \w+ < (.*); \+\+\w+\))")))
        {
            n.kind = Node::Loop;
            n.name = m[1];
            n.value = expression(m[2]);
        }
        else if (std::regex_match(line, m, std::regex(R"(if \((.*)\))")))
        {
            n.kind = Node::Condition;
            auto condition = m[1].str();
            if (condition.starts_with("fieldVisibilityFlags.HasFlag("))
            {
                std::regex flags(R"(UpdateFieldFlag::(\w+))");
                for (std::sregex_iterator i(condition.begin(), condition.end(), flags), end; i != end; ++i)
                {
                    std::unordered_map<std::string, unsigned> masks = {
                        {"Owner", 1}, {"PartyMember", 2}, {"UnitAll", 4}, {"Empath", 8}};
                    n.mask |= masks.at((*i)[1]);
                }
                if (!n.mask)
                    throw std::runtime_error("unknown visibility mask");
            }
            else
                n.value = expression(condition);
        }
        else if (line == "data.FlushBits();")
            n.kind = Node::Flush;
        else if (std::regex_match(line, m, std::regex(R"(data.WriteBits\((.*), (\d+)\);)")))
        {
            n.kind = Node::Bits;
            n.value = expression(m[1]);
            n.width = std::stoul(m[2]);
        }
        else if (std::regex_match(line, m, std::regex(R"(data.WriteBit\((.*)\);)")))
        {
            n.kind = Node::Bits;
            n.value = expression(m[1]);
            n.width = 1;
        }
        else if (std::regex_match(line, m, std::regex(R"(data.WriteString\((.+)\);)")))
        {
            n.kind = Node::String;
            n.value = expression(m[1]);
        }
        else if (std::regex_match(line, m, std::regex(R"(data << (\w+)\((.*)\);)")) && scalar.contains(m[1]))
        {
            n.kind = Node::Scalar;
            n.format = scalar.at(m[1]);
            n.value = expression(m[2]);
        }
        else if (std::regex_match(line, m,
                                  std::regex(R"((.+?)(?:\.|->)WriteCreate\(data, owner, receiver\);)")))
        {
            n.kind = Node::Nested;
            n.value = expression(m[1]);
            auto field = m[1].str();
            field = field.substr(0, field.find_first_of("[.-"));
            n.name = str(types.at(field));
            if (std::regex_match(n.name, m, std::regex(R"(DynamicUpdateFieldBase<UF::(\w+)>)")))
                n.name = m[1];
        }
        else if (std::regex_match(line, m, std::regex(R"(data << (.+);)")))
        {
            n.value = expression(m[1]);
            auto field = m[1].str();
            field = field.substr(0, field.find_first_of("[.-"));
            auto type = str(types.at(field));
            if (type == "ObjectGuid")
                n.kind = Node::Guid;
            else if (type.ends_with("DungeonScoreSummary"))
                n.kind = Node::Dungeon;
            else if (type.ends_with("PerksVendorItem"))
                n.kind = Node::Perks;
            else if (type.ends_with("ItemBonusKey"))
                n.kind = Node::Bonus;
            else if (scalar.contains(type))
            {
                n.kind = Node::Scalar;
                n.format = scalar.at(type);
            }
            else
            {
                n.kind = Node::Unsupported;
                n.name = "unsupported untyped create field: " + type;
            }
        }
        else if (line.find("stateWorldEffectIDs") != std::string::npos && line.find('=') != std::string::npos)
            n.kind = Node::EmptyEffects;
        else
        {
            n.kind = Node::Unsupported;
            n.name = "unsupported create-field statement: " + line;
        }
        if (n.kind == Node::Loop || n.kind == Node::Condition)
        {
            if (pos >= lines.size() || str(lines[pos++]) != "{")
                throw std::runtime_error("unbraced generated statement");
            n.children = compile(lines, types, pos, true);
        }
        result.push_back(std::move(n));
    }
    if (nested)
        throw std::runtime_error("missing schema closing brace");
    return result;
}
} // namespace
struct Fields::Program
{
    std::unordered_map<std::string, std::vector<Node>> kinds;
    void run(Writer &w, std::vector<Node> const &nodes, Value &values, Variables const &vars,
             unsigned visibility, unsigned depth) const
    {
        if (depth > 32)
            throw std::runtime_error("serializer recursion bound");
        for (auto const &n : nodes)
        {
            auto eval = [&]() { return n.value(values, vars); };
            switch (n.kind)
            {
            case Node::Loop:
            {
                auto count = integer(eval());
                if (count > 10000)
                    throw std::runtime_error("create array exceeds bound");
                for (std::uint64_t i = 0; i < count; ++i)
                {
                    auto next = vars;
                    next[n.name] = i;
                    run(w, n.children, values, next, visibility, depth + 1);
                }
                break;
            }
            case Node::Condition:
                if (n.mask ? (visibility & n.mask) != 0 : truth(eval()))
                    run(w, n.children, values, vars, visibility, depth + 1);
                break;
            case Node::Flush:
                w.flush();
                break;
            case Node::Bits:
                w.bits(integer(eval()), n.width);
                break;
            case Node::String:
            {
                auto v = eval();
                w.raw(v.is_string() ? str(v) : "");
                break;
            }
            case Node::Scalar:
                w.pack(std::string(1, n.format), {eval()});
                break;
            case Node::Nested:
            {
                auto v = eval();
                if (!truth(v))
                    v = Object{};
                run(w, kinds.at(n.name), v, {}, visibility, depth + 1);
                break;
            }
            case Node::Guid:
                w.guid(eval());
                break;
            case Node::Dungeon:
                w.pack("ffI", {0, 0, 0});
                break;
            case Node::Perks:
                w.zeros(40).bits(0, 2).flush();
                break;
            case Node::Bonus:
            {
                auto v = eval();
                auto bonuses = get(v, "BonusListIDs");
                if (!bonuses.is_array())
                    bonuses = Array{};
                w.pack("iI", {get(v, "ItemID"), bonuses.as_array().size()});
                w.pack(std::string(bonuses.as_array().size(), 'i'), bonuses.as_array());
                break;
            }
            case Node::EmptyEffects:
                values.as_object()["stateWorldEffectIDs"] = Array{};
                break;
            case Node::Unsupported:
                throw std::runtime_error(n.name);
            }
        }
    }
};
Fields::Fields(std::filesystem::path const &path)
{
    auto schema = load_json(path);
    auto program = std::make_shared<Program>();
    std::vector<std::string> required = {"ObjectData",     "UnitData", "PlayerData",   "ActivePlayerData",
                                         "GameObjectData", "ItemData", "ContainerData"};
    std::function<void(std::vector<Node> const &)> dependencies = [&](auto const &nodes)
    {
        for (auto const &node : nodes)
        {
            if (node.kind == Node::Nested)
                required.push_back(node.name);
            dependencies(node.children);
        }
    };
    for (std::size_t i = 0; i < required.size(); ++i)
    {
        auto kind = required[i];
        if (program->kinds.contains(kind))
            continue;
        if (!get(get(schema, "create"), kind).is_array() || !get(get(schema, "types"), kind).is_object())
        {
            Node unsupported{};
            unsupported.kind = Node::Unsupported;
            unsupported.name = "unknown generated create serializer: " + kind;
            program->kinds[kind] = {unsupported};
            continue;
        }
        std::size_t pos = 0;
        auto nodes = compile(get(get(schema, "create"), kind).as_array(),
                             get(get(schema, "types"), kind).as_object(), pos);
        dependencies(nodes);
        program->kinds[kind] = std::move(nodes);
    }
    program_ = std::move(program);
}
void Fields::serialize(Writer &w, std::string const &kind, Value values, unsigned visibility) const
{
    program_->run(w, program_->kinds.at(kind), values, {}, visibility, 0);
}
} // namespace bridge
