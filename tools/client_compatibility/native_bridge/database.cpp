#include "database.hpp"
#include <ctime>
#include <memory>
#include <mutex>

namespace bridge
{
namespace
{
std::once_flag library;
struct ThreadState
{
    ThreadState()
    {
        if (mysql_thread_init())
            throw std::runtime_error("database thread initialization failed");
    }
    ~ThreadState()
    {
        mysql_thread_end();
    }
};
} // namespace
Database::Database(std::filesystem::path const &root)
{
    std::call_once(library,
                   []
                   {
                       if (mysql_library_init(0, nullptr, nullptr))
                           throw std::runtime_error("database library initialization failed");
                   });
    thread_local ThreadState thread;
    auto credentials = load_json(root / "secrets/runtime.json");
    if (str(get(credentials, "host")) != "127.0.0.1" || integer(get(credentials, "port")) != 13306 ||
        str(get(credentials, "user")) != "client442_runtime")
        throw std::runtime_error("database credentials do not target the lab");
    connection_ = mysql_init(nullptr);
    if (!connection_)
        throw std::runtime_error("database initialization failed");
    unsigned timeout = 5;
    mysql_options(connection_, MYSQL_OPT_CONNECT_TIMEOUT, &timeout);
    mysql_options(connection_, MYSQL_OPT_READ_TIMEOUT, &timeout);
    mysql_options(connection_, MYSQL_OPT_WRITE_TIMEOUT, &timeout);
    auto password = str(get(credentials, "password"));
    if (!mysql_real_connect(connection_, "127.0.0.1", "client442_runtime", password.c_str(), nullptr, 13306,
                            nullptr, 0))
    {
        mysql_close(connection_);
        connection_ = nullptr;
        throw std::runtime_error("lab database connection failed");
    }
    try
    {
        if (mysql_set_character_set(connection_, "utf8mb4"))
            throw std::runtime_error("database character set failed");
        auto rows = query("SELECT @@hostname AS hostname");
        if (rows.size() != 1 || str(get(rows[0], "hostname")) != "trinity-client442-db")
            throw std::runtime_error("wrong database instance");
    }
    catch (...)
    {
        mysql_close(connection_);
        connection_ = nullptr;
        throw;
    }
}
Database::~Database()
{
    if (connection_)
        mysql_close(connection_);
}
void Database::execute(std::string const &sql)
{
    if (mysql_real_query(connection_, sql.data(), sql.size()))
        throw std::runtime_error("lab database operation failed");
}
Array Database::query(std::string const &sql)
{
    execute(sql);
    std::unique_ptr<MYSQL_RES, decltype(&mysql_free_result)> result(mysql_store_result(connection_),
                                                                    mysql_free_result);
    if (!result)
    {
        if (mysql_field_count(connection_))
            throw std::runtime_error("database result failed");
        return {};
    }
    auto count = mysql_num_fields(result.get());
    auto fields = mysql_fetch_fields(result.get());
    Array rows;
    while (auto row = mysql_fetch_row(result.get()))
    {
        auto lengths = mysql_fetch_lengths(result.get());
        Object record;
        for (unsigned i = 0; i < count; ++i)
        {
            Value value;
            if (row[i])
            {
                std::string text(row[i], lengths[i]);
                switch (fields[i].type)
                {
                case MYSQL_TYPE_TINY:
                case MYSQL_TYPE_SHORT:
                case MYSQL_TYPE_LONG:
                case MYSQL_TYPE_INT24:
                case MYSQL_TYPE_LONGLONG:
                    value =
                        fields[i].flags & UNSIGNED_FLAG ? Value(std::stoull(text)) : Value(std::stoll(text));
                    break;
                case MYSQL_TYPE_FLOAT:
                case MYSQL_TYPE_DOUBLE:
                case MYSQL_TYPE_DECIMAL:
                case MYSQL_TYPE_NEWDECIMAL:
                    value = std::stod(text);
                    break;
                default:
                    value = text;
                }
            }
            record[fields[i].name] = value;
        }
        rows.push_back(record);
        if (rows.size() > 1000000)
            throw std::runtime_error("database result exceeds bound");
    }
    return rows;
}
std::string Database::quote(std::string const &value)
{
    std::string escaped(value.size() * 2 + 1, '\0');
    escaped.resize(
        mysql_real_escape_string_quote(connection_, escaped.data(), value.data(), value.size(), '\''));
    return "'" + escaped + "'";
}
Login Database::consume(View body, View challenge)
{
    Reader r(body);
    r.take<std::uint64_t>();
    auto region = r.take<std::uint32_t>(), group = r.take<std::uint32_t>(), realm = r.take<std::uint32_t>();
    auto local = r.raw(32), proof = r.raw(24);
    r.bits(1);
    auto size = r.take<std::uint32_t>();
    if (size > 4096 || region != 1 || group != 1 || realm != 1)
        throw std::runtime_error("invalid realm authentication identity");
    auto ticket = r.raw(size);
    r.end();
    auto data = json::parse(std::string(ticket.begin(), ticket.end()));
    auto type = integer(get(data, "type"));
    auto variant = type == 0x576f57     ? "WoW"
                   : type == 0x576f5743 ? "WoWC"
                                        : throw std::runtime_error("unsupported world build variant");
    auto ticket_hash = "X'" + hex(hash(ticket, "SHA256")) + "'";
    execute("START TRANSACTION");
    try
    {
        auto rows = query("SELECT native_id,key_data,expires,consumed FROM client442_auth.lab_world_joins "
                          "WHERE ticket_hash=" +
                          ticket_hash + " FOR UPDATE");
        auto now = std::time(nullptr);
        if (rows.size() != 1 || integer(get(rows[0], "expires")) <= static_cast<std::uint64_t>(now) ||
            truth(get(rows[0], "consumed")))
            throw std::runtime_error("expired, unknown or consumed world ticket");
        auto material = bytes(str(get(rows[0], "key_data")));
        auto [session, key] = derive(material, local, challenge, proof, variant);
        auto account = integer(get(rows[0], "native_id"));
        auto accounts = query(
            "SELECT a.username,a.locked,a.last_ip,EXISTS(SELECT 1 FROM client442_auth.account_banned b WHERE "
            "b.id=a.id AND b.active=1 AND ((b.unbandate>b.bandate AND b.unbandate>UNIX_TIMESTAMP()) OR "
            "b.unbandate=b.bandate)) AS banned FROM client442_auth.account a JOIN "
            "client442_auth.lab_login_accounts l ON l.native_id=a.id WHERE a.id=" +
            std::to_string(account));
        if (accounts.size() != 1 || truth(get(accounts[0], "banned")) ||
            (truth(get(accounts[0], "locked")) && str(get(accounts[0], "last_ip")) != "127.0.0.1") ||
            get(data, "gameAccount") != get(accounts[0], "username"))
            throw std::runtime_error("world ticket account mismatch, banned, locked or absent");
        Login login{static_cast<unsigned>(account), str(get(accounts[0], "username")), session, key,
                    random_bytes(40)};
        execute("UPDATE client442_auth.lab_world_joins SET consumed=TRUE WHERE ticket_hash=" + ticket_hash);
        execute("COMMIT");
        return login;
    }
    catch (...)
    {
        execute("ROLLBACK");
        throw;
    }
}
void Database::native_key(Database &db, Login const &login)
{
    db.execute("UPDATE client442_auth.account SET session_key_auth=X'" + hex(login.native_key) +
               "',os='Win',last_ip='127.0.0.1' WHERE id=" + std::to_string(login.account) +
               " AND username=" + db.quote(login.username));
    if (mysql_affected_rows(db.connection_) != 1)
        throw std::runtime_error("native account is absent");
}
Array Database::characters(unsigned account)
{
    return query(
        "SELECT "
        "guid,name,race,class,gender,level,map,zone,position_x,position_y,position_z,orientation,"
        "characterFlags,at_login,slot,logout_time FROM client442_characters.characters WHERE account=" +
        std::to_string(account) + " ORDER BY slot,guid");
}
Array Database::equipment(unsigned account)
{
    return query(
        "SELECT c.guid,ci.slot,ii.itemEntry FROM client442_characters.characters c JOIN "
        "client442_characters.character_inventory ci ON ci.guid=c.guid AND ci.bag=0 AND ci.slot<19 JOIN "
        "client442_characters.item_instance ii ON ii.guid=ci.item AND ii.owner_guid=c.guid WHERE c.account=" +
        std::to_string(account));
}
} // namespace bridge
