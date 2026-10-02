#pragma once
#include "crypto.hpp"
#include <mysql/mysql.h>

namespace bridge
{
struct Login
{
    unsigned account = 0;
    std::string username;
    Bytes session, encryption, native_key;
};
class Database
{
    MYSQL *connection_ = nullptr;

  public:
    explicit Database(std::filesystem::path const &root);
    ~Database();
    Database(Database const &) = delete;
    Database &operator=(Database const &) = delete;
    Array query(std::string const &sql);
    void execute(std::string const &sql);
    std::string quote(std::string const &value);
    Login consume(View body, View challenge);
    Array characters(unsigned account);
    Array equipment(unsigned account);
    static void native_key(Database &db, Login const &login);
};
} // namespace bridge
