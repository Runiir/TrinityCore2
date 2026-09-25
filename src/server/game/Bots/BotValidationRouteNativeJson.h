#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_JSON_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_JSON_H

// Strict, bounded JSON reader for route contract objects.
//
// The legacy manifest reader extracts fields with regular expressions over a
// whole route row. That is unsafe for nested contracts: route rows are written
// with sorted keys, so "completion_contract" (and its "kind") precedes the
// row's own "kind". Native route contracts are therefore parsed structurally
// here. The reader is header-only and free of server dependencies so the
// contract parser can be tested with a plain g++ build.

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace BotValidationRouteNativeJson
{
struct Value
{
    enum class Type : std::uint8_t { Null, Bool, Number, String, Array, Object };

    Type Kind = Type::Null;
    bool Boolean = false;
    double Number = 0.0;
    // True when the number literal had no fraction or exponent.
    bool Integral = false;
    bool Negative = false;
    std::string Text;
    std::vector<Value> Items;
    std::vector<std::pair<std::string, Value>> Members;

    bool IsObject() const { return Kind == Type::Object; }
    bool IsArray() const { return Kind == Type::Array; }
    bool IsString() const { return Kind == Type::String; }
    bool IsNumber() const { return Kind == Type::Number; }
    bool IsBool() const { return Kind == Type::Bool; }

    Value const* Find(std::string_view key) const
    {
        if (Kind != Type::Object)
            return nullptr;
        for (auto const& [name, value] : Members)
            if (name == key)
                return &value;
        return nullptr;
    }
};

class Reader
{
public:
    explicit Reader(std::string_view text) : _text(text) { }

    bool Parse(Value& out, std::string& error)
    {
        _pos = 0;
        _error.clear();
        SkipWhitespace();
        if (!ParseValue(out, 0))
        {
            error = _error.empty() ? "json_invalid" : _error;
            return false;
        }
        SkipWhitespace();
        if (_pos != _text.size())
        {
            error = "json_trailing_data";
            return false;
        }
        error.clear();
        return true;
    }

private:
    static constexpr std::size_t MaxDepth = 32;

    bool Fail(char const* reason)
    {
        if (_error.empty())
            _error = reason;
        return false;
    }

    void SkipWhitespace()
    {
        while (_pos < _text.size()
            && (_text[_pos] == ' ' || _text[_pos] == '\t'
                || _text[_pos] == '\n' || _text[_pos] == '\r'))
            ++_pos;
    }

    bool Consume(char expected)
    {
        if (_pos < _text.size() && _text[_pos] == expected)
        {
            ++_pos;
            return true;
        }
        return false;
    }

    bool ParseLiteral(std::string_view literal)
    {
        if (_text.substr(_pos, literal.size()) != literal)
            return false;
        _pos += literal.size();
        return true;
    }

    bool ParseString(std::string& out)
    {
        if (!Consume('"'))
            return Fail("json_string_expected");
        out.clear();
        while (_pos < _text.size())
        {
            char const c = _text[_pos++];
            if (c == '"')
                return true;
            if (static_cast<unsigned char>(c) < 0x20)
                return Fail("json_string_control_character");
            if (c != '\\')
            {
                out.push_back(c);
                continue;
            }
            if (_pos >= _text.size())
                return Fail("json_string_escape_truncated");
            char const escaped = _text[_pos++];
            switch (escaped)
            {
                case '"': out.push_back('"'); break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/'); break;
                case 'b': out.push_back('\b'); break;
                case 'f': out.push_back('\f'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                case 'u':
                {
                    // Contract strings are ASCII identifiers; keep escaped
                    // code points only when they are plain ASCII.
                    if (_pos + 4 > _text.size())
                        return Fail("json_string_escape_truncated");
                    unsigned value = 0;
                    for (int i = 0; i < 4; ++i)
                    {
                        char const h = _text[_pos++];
                        value <<= 4;
                        if (h >= '0' && h <= '9')
                            value |= unsigned(h - '0');
                        else if (h >= 'a' && h <= 'f')
                            value |= unsigned(h - 'a' + 10);
                        else if (h >= 'A' && h <= 'F')
                            value |= unsigned(h - 'A' + 10);
                        else
                            return Fail("json_string_escape_invalid");
                    }
                    if (value >= 0x80)
                        return Fail("json_string_non_ascii_escape");
                    out.push_back(char(value));
                    break;
                }
                default:
                    return Fail("json_string_escape_invalid");
            }
        }
        return Fail("json_string_unterminated");
    }

    bool ParseNumber(Value& out)
    {
        std::size_t const start = _pos;
        bool integral = true;
        bool negative = false;
        if (_pos < _text.size() && _text[_pos] == '-')
        {
            negative = true;
            ++_pos;
        }
        std::size_t const digitsStart = _pos;
        while (_pos < _text.size() && _text[_pos] >= '0' && _text[_pos] <= '9')
            ++_pos;
        if (_pos == digitsStart)
            return Fail("json_number_invalid");
        if (_text[digitsStart] == '0' && _pos - digitsStart > 1)
            return Fail("json_number_leading_zero");
        if (_pos < _text.size() && _text[_pos] == '.')
        {
            integral = false;
            ++_pos;
            std::size_t const fractionStart = _pos;
            while (_pos < _text.size() && _text[_pos] >= '0' && _text[_pos] <= '9')
                ++_pos;
            if (_pos == fractionStart)
                return Fail("json_number_invalid");
        }
        if (_pos < _text.size() && (_text[_pos] == 'e' || _text[_pos] == 'E'))
        {
            integral = false;
            ++_pos;
            if (_pos < _text.size() && (_text[_pos] == '+' || _text[_pos] == '-'))
                ++_pos;
            std::size_t const exponentStart = _pos;
            while (_pos < _text.size() && _text[_pos] >= '0' && _text[_pos] <= '9')
                ++_pos;
            if (_pos == exponentStart)
                return Fail("json_number_invalid");
        }
        std::string const literal(_text.substr(start, _pos - start));
        out.Kind = Value::Type::Number;
        out.Number = std::strtod(literal.c_str(), nullptr);
        out.Integral = integral;
        out.Negative = negative;
        return true;
    }

    bool ParseValue(Value& out, std::size_t depth)
    {
        if (depth > MaxDepth)
            return Fail("json_too_deep");
        SkipWhitespace();
        if (_pos >= _text.size())
            return Fail("json_truncated");
        out = Value();
        char const c = _text[_pos];
        if (c == '{')
        {
            ++_pos;
            out.Kind = Value::Type::Object;
            SkipWhitespace();
            if (Consume('}'))
                return true;
            while (true)
            {
                SkipWhitespace();
                std::string key;
                if (!ParseString(key))
                    return false;
                for (auto const& member : out.Members)
                    if (member.first == key)
                        return Fail("json_duplicate_key");
                SkipWhitespace();
                if (!Consume(':'))
                    return Fail("json_colon_expected");
                Value member;
                if (!ParseValue(member, depth + 1))
                    return false;
                out.Members.emplace_back(std::move(key), std::move(member));
                SkipWhitespace();
                if (Consume('}'))
                    return true;
                if (!Consume(','))
                    return Fail("json_object_separator_expected");
            }
        }
        if (c == '[')
        {
            ++_pos;
            out.Kind = Value::Type::Array;
            SkipWhitespace();
            if (Consume(']'))
                return true;
            while (true)
            {
                Value item;
                if (!ParseValue(item, depth + 1))
                    return false;
                out.Items.push_back(std::move(item));
                SkipWhitespace();
                if (Consume(']'))
                    return true;
                if (!Consume(','))
                    return Fail("json_array_separator_expected");
            }
        }
        if (c == '"')
        {
            out.Kind = Value::Type::String;
            return ParseString(out.Text);
        }
        if (c == 't' || c == 'f')
        {
            out.Kind = Value::Type::Bool;
            out.Boolean = c == 't';
            return ParseLiteral(c == 't' ? "true" : "false")
                || Fail("json_literal_invalid");
        }
        if (c == 'n')
        {
            out.Kind = Value::Type::Null;
            return ParseLiteral("null") || Fail("json_literal_invalid");
        }
        return ParseNumber(out);
    }

    std::string_view _text;
    std::size_t _pos = 0;
    std::string _error;
};

inline bool Parse(std::string_view text, Value& out, std::string& error)
{
    return Reader(text).Parse(out, error);
}

// Read an unsigned integral field. Absent fields keep the default and succeed;
// a present field of the wrong shape fails.
inline bool ReadUnsigned(Value const& object, std::string_view key,
    std::uint64_t& out, std::uint64_t maximum)
{
    Value const* value = object.Find(key);
    if (!value)
        return true;
    if (!value->IsNumber() || !value->Integral || value->Negative
        || value->Number > double(maximum))
        return false;
    out = std::uint64_t(value->Number);
    return true;
}

inline bool ReadSigned(Value const& object, std::string_view key,
    std::int64_t& out, std::int64_t minimum, std::int64_t maximum)
{
    Value const* value = object.Find(key);
    if (!value)
        return true;
    if (!value->IsNumber() || !value->Integral
        || value->Number < double(minimum) || value->Number > double(maximum))
        return false;
    out = std::int64_t(value->Number);
    return true;
}

inline bool ReadFloat(Value const& object, std::string_view key, float& out)
{
    Value const* value = object.Find(key);
    if (!value)
        return true;
    if (!value->IsNumber())
        return false;
    out = float(value->Number);
    return true;
}

inline bool ReadBool(Value const& object, std::string_view key, bool& out)
{
    Value const* value = object.Find(key);
    if (!value)
        return true;
    if (!value->IsBool())
        return false;
    out = value->Boolean;
    return true;
}

inline bool ReadString(Value const& object, std::string_view key, std::string& out)
{
    Value const* value = object.Find(key);
    if (!value)
        return true;
    if (!value->IsString())
        return false;
    out = value->Text;
    return true;
}

// Top-level string field of a JSON object text, or `fallback` when the text is
// not a parseable object or the field is absent/not a string.
inline std::string TopLevelString(std::string_view objectText,
    std::string_view key, std::string const& fallback)
{
    Value root;
    std::string error;
    if (!Parse(objectText, root, error) || !root.IsObject())
        return fallback;
    Value const* value = root.Find(key);
    return value && value->IsString() ? value->Text : fallback;
}
}

#endif
