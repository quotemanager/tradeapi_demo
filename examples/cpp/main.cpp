#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

using Json = nlohmann::json;
constexpr size_t ResultBytes = 1048577, ErrorBytes = 256;

static std::wstring wide(const std::string& value, UINT page = CP_UTF8) {
    if (value.empty()) return {};
    int n = MultiByteToWideChar(page, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), nullptr, 0);
    if (!n) throw std::runtime_error("Invalid string encoding");
    std::wstring result(n, L'\0');
    MultiByteToWideChar(page, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), result.data(), n);
    return result;
}
static std::string utf8(const std::wstring& value) {
    if (value.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    std::string result(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), result.data(), n, nullptr, nullptr);
    return result;
}
static void ascii(const std::string& value) {
    for (unsigned char c : value) if (!c || c > 127) throw std::runtime_error("Expected ASCII without NUL characters");
}
static int integer(const std::string& value, int minimum, int maximum) {
    size_t used = 0;
    long long n = std::stoll(value, &used);
    if (used != value.size() || n < minimum || n > maximum) throw std::runtime_error("Integer parameter out of range");
    return static_cast<int>(n);
}
static std::string environment(const wchar_t* name, bool* found = nullptr) {
    DWORD n = GetEnvironmentVariableW(name, nullptr, 0);
    if (found) *found = n != 0;
    if (n <= 1) return {}; // Empty environment variables need no second read.
    std::wstring value(n, L'\0');
    DWORD written = GetEnvironmentVariableW(name, value.data(), n);
    if (!written || written >= n) throw std::runtime_error("Environment changed while reading");
    value.resize(written);
    return utf8(value);
}
static std::string password() {
    bool found;
    std::string value = environment(L"TRADEAPI_PASSWORD", &found);
    if (found) return value;
    HANDLE input = GetStdHandle(STD_INPUT_HANDLE);
    DWORD mode;
    if (!GetConsoleMode(input, &mode)) throw std::runtime_error("Use an interactive console or TRADEAPI_PASSWORD");
    std::cerr << "Trading password: ";
    if (!SetConsoleMode(input, mode & ~ENABLE_ECHO_INPUT)) throw std::runtime_error("Cannot hide password input");
    wchar_t buffer[512] = {};
    DWORD count = 0;
    BOOL ok = ReadConsoleW(input, buffer, 511, &count, nullptr);
    SetConsoleMode(input, mode);
    std::cerr << '\n';
    if (!ok) throw std::runtime_error("Cannot read password");
    std::wstring text(buffer, count);
    SecureZeroMemory(buffer, sizeof(buffer));
    while (!text.empty() && (text.back() == L'\r' || text.back() == L'\n')) text.pop_back();
    return utf8(text);
}
static Json load_config(const std::string& path) {
    std::ifstream file(std::filesystem::u8path(path), std::ios::binary);
    if (!file) throw std::runtime_error("Cannot read configuration file");
    Json c;
    try { file >> c; } catch (...) { throw std::runtime_error("Invalid configuration JSON"); }
    if (!c.is_object()) throw std::runtime_error("Configuration must be an object");
    const std::vector<std::string> allowed = {"runtime_dir", "broker_code", "account_no", "trade_account", "host", "port", "version", "yyb_id"};
    for (auto it = c.begin(); it != c.end(); ++it)
        if (std::find(allowed.begin(), allowed.end(), it.key()) == allowed.end())
            throw std::runtime_error("Unknown configuration field; do not store passwords in JSON");
    for (const auto* name : {"runtime_dir", "broker_code", "account_no"})
        if (!c.contains(name) || !c[name].is_string() || c[name].get<std::string>().empty())
            throw std::runtime_error("Missing required configuration string");
    for (const auto* name : {"broker_code", "account_no", "trade_account", "host", "version"}) {
        if (c.contains(name) && !c[name].is_string()) throw std::runtime_error("Expected configuration string");
        ascii(c.value(name, ""));
    }
    if (c["broker_code"].get<std::string>().rfind("BROKER_", 0) == 0 || c["account_no"] == "YOUR_ACCOUNT")
        throw std::runtime_error("Replace example broker/account placeholders");
    if (!std::filesystem::u8path(c["runtime_dir"].get<std::string>()).is_absolute())
        throw std::runtime_error("runtime_dir must be absolute");
    for (const auto* name : {"port", "yyb_id"}) {
        if (c.contains(name) && !c[name].is_number_integer()) throw std::runtime_error("Expected configuration integer");
        auto n = c.value(name, 0LL);
        if (n < 0 || n > (std::string(name) == "port" ? 65535 : 32767)) throw std::runtime_error("Configuration integer out of range");
    }
    return c;
}

class TradeApi {
    using VoidFn = void (__stdcall*)();
    using LogonFn = int (__stdcall*)(const char*, const char*, short, const char*, short,
        const char*, const char*, const char*, const char*, char*);
    using LogoffFn = void (__stdcall*)(int);
    using QueryFn = void (__stdcall*)(int, int, char*, char*);
    using ShareFn = void (__stdcall*)(int, char*, char*);
    using OrderFn = void (__stdcall*)(int, int, int, const char*, const char*, float, int, char*, char*);
    using CancelFn = void (__stdcall*)(int, const char*, const char*, char*, char*);
    HMODULE dll_ = nullptr;
    bool opened_ = false;
    int client_ = -1;
    VoidFn open_, close_;
    LogonFn logon_;
    LogoffFn logoff_;
    QueryFn query_;
    ShareFn shareholders_;
    OrderFn order_;
    CancelFn cancel_;
    template<class T> T symbol(const char* name) {
        FARPROC p = GetProcAddress(dll_, name);
        if (!p) throw std::runtime_error(std::string("Missing DLL export: ") + name);
        return reinterpret_cast<T>(p);
    }
    template<class Call> Json result(Call call) {
        if (client_ <= 0) throw std::runtime_error("Login first");
        std::vector<char> body(ResultBytes, 0), error(ErrorBytes, 0);
        call(body.data(), error.data());
        body.back() = error.back() = '\0';
        if (error[0]) throw std::runtime_error(utf8(wide(error.data(), 54936))); // GB18030
        Json value = Json::parse(body.data());
        if (!value.is_object()) throw std::runtime_error("Expected a JSON object");
        return value;
    }
public:
    explicit TradeApi(const Json& c) {
        static_assert(sizeof(void*) == 4, "Windows x86 is required");
        auto path = std::filesystem::u8path(c["runtime_dir"].get<std::string>()) / L"tradeApi.dll";
        dll_ = LoadLibraryExW(path.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        if (!dll_) throw std::runtime_error("DLL load failed; Windows error=" + std::to_string(GetLastError()));
        try {
            open_ = symbol<VoidFn>("OpenTdx"); close_ = symbol<VoidFn>("CloseTdx");
            logon_ = symbol<LogonFn>("Logon"); logoff_ = symbol<LogoffFn>("Logoff");
            query_ = symbol<QueryFn>("QueryData"); shareholders_ = symbol<ShareFn>("QueryShareholderCodes");
            order_ = symbol<OrderFn>("SendOrder"); cancel_ = symbol<CancelFn>("CancelOrder");
            open_(); opened_ = true;
        } catch (...) { FreeLibrary(dll_); dll_ = nullptr; throw; }
    }
    TradeApi(const TradeApi&) = delete;
    TradeApi& operator=(const TradeApi&) = delete;
    ~TradeApi() {
        if (client_ > 0) logoff_(client_);
        if (opened_) close_();
        if (dll_) FreeLibrary(dll_);
    }
    void login(const Json& c, const std::string& pass, const std::string& tx) {
        if (client_ > 0 || pass.empty()) throw std::runtime_error("Login once with a nonempty password");
        ascii(pass); ascii(tx);
        char error[ErrorBytes] = {};
        // The ABI has a 16-bit short. Preserve all unsigned port bits (0..65535).
        short port = static_cast<short>(static_cast<uint16_t>(c.value("port", 0)));
        client_ = logon_(c["broker_code"].get<std::string>().c_str(), c.value("host", "").c_str(), port,
            c.value("version", "").c_str(), static_cast<short>(c.value("yyb_id", 0)),
            c["account_no"].get<std::string>().c_str(), c.value("trade_account", "").c_str(), pass.c_str(), tx.c_str(), error);
        error[ErrorBytes - 1] = '\0';
        if (client_ <= 0) throw std::runtime_error(error[0] ? utf8(wide(error, 54936)) : "Logon failed");
    }
    Json query(int category) { return result([&](char* r, char* e) { query_(client_, category, r, e); }); }
    Json shareholders() { return result([&](char* r, char* e) { shareholders_(client_, r, e); }); }
    // These low-level methods SEND directly; the CLI below owns human confirmation.
    Json order(int side, const std::string& shareholder, const std::string& code, float price, int quantity) {
        ascii(shareholder); ascii(code);
        if (side < 0 || side > 2 || shareholder.empty() || code.size() != 6 ||
            code.find_first_not_of("0123456789") != std::string::npos || !std::isfinite(price) || price <= 0 || quantity <= 0)
            throw std::runtime_error("Invalid order parameters");
        return result([&](char* r, char* e) { order_(client_, side, 0, shareholder.c_str(), code.c_str(), price, quantity, r, e); });
    }
    Json cancel(const std::string& exchange, const std::string& id) {
        ascii(exchange); ascii(id);
        if (id.empty()) throw std::runtime_error("OrderID is required");
        return result([&](char* r, char* e) { cancel_(client_, exchange.c_str(), id.c_str(), r, e); });
    }
};

int main(int argc, char** argv) {
    SetConsoleOutputCP(CP_UTF8);
    try {
        std::map<std::string, std::string> options;
        std::string operation = "query";
        bool operation_seen = false;
        for (int i = 1; i < argc; ++i) {
            std::string key = argv[i];
            if (key == "--help") {
                std::cout << "--config FILE [query --category 0..6 | shareholders | order --category 0..2 --shareholder CODE --code CODE --price PRICE --quantity QTY | cancel --order-id ID [--exchange CODE]]\n";
                return 0;
            }
            if (key.rfind("--", 0) != 0) {
                if (operation_seen || (key != "query" && key != "shareholders" && key != "order" && key != "cancel"))
                    throw std::runtime_error("Unknown or duplicate command");
                operation = key; operation_seen = true;
            } else {
                if (++i >= argc || options.count(key)) throw std::runtime_error("Missing or duplicate option");
                options[key] = argv[i];
            }
        }
        std::vector<std::string> allowed = {"--config"};
        if (operation == "query") allowed.push_back("--category");
        if (operation == "order") allowed.insert(allowed.end(), {"--category", "--shareholder", "--code", "--price", "--quantity"});
        if (operation == "cancel") allowed.insert(allowed.end(), {"--exchange", "--order-id"});
        for (const auto& item : options)
            if (std::find(allowed.begin(), allowed.end(), item.first) == allowed.end()) throw std::runtime_error("Unknown option for command");
        auto required = [&](const std::string& key) -> std::string {
            if (!options.count(key) || options.at(key).empty()) throw std::runtime_error("Required option: " + key);
            return options.at(key);
        };
        Json config = load_config(required("--config"));
        int category = operation == "order" ? integer(required("--category"), 0, 2) :
            integer(options.count("--category") ? options.at("--category") : "0", 0, 6);
        float price = 0; int quantity = 0;
        std::string shareholder, code, id, exchange;
        if (operation == "order") {
            shareholder = required("--shareholder"); code = required("--code");
            size_t used; auto value = required("--price"); price = std::stof(value, &used);
            if (used != value.size() || !std::isfinite(price) || price <= 0) throw std::runtime_error("Invalid price");
            quantity = integer(required("--quantity"), 1, std::numeric_limits<int>::max());
            std::cerr << "REAL ORDER category=" << category << " shareholder=" << shareholder << " code=" << code
                << " price=" << price << " quantity=" << quantity << '\n';
        }
        if (operation == "cancel") {
            id = required("--order-id"); exchange = options.count("--exchange") ? options.at("--exchange") : "";
            std::cerr << "REAL CANCEL order_id=" << id << " exchange=" << exchange << '\n';
        }
        if (operation == "order" || operation == "cancel") {
            auto account = config["account_no"].get<std::string>();
            std::cerr << "Broker=" << config["broker_code"].get<std::string>() << " Account=****"
                << account.substr(account.size() > 4 ? account.size() - 4 : 0) << '\n';
            std::string token = operation == "order" ? "SEND ORDER" : "CANCEL ORDER", input;
            std::cerr << "Verify account in local config. Type " << token << " exactly; anything else aborts:\n";
            if (!std::getline(std::cin, input) || input != token) { std::cerr << "Aborted; no login or action sent.\n"; return 2; }
        }
        TradeApi api(config);
        api.login(config, password(), environment(L"TRADEAPI_TX_PASSWORD"));
        Json result = operation == "order" ? api.order(category, shareholder, code, price, quantity) :
            operation == "cancel" ? api.cancel(exchange, id) : operation == "shareholders" ? api.shareholders() : api.query(category);
        std::cout << result.dump(2) << '\n';
        if (operation == "order" || operation == "cancel") {
            if (result.contains("accepted") && result["accepted"].is_boolean()) {
                if (result["accepted"].get<bool>()) std::cerr << "Request accepted; NOT final execution/cancellation. Query final status.\n";
                else std::cerr << "Broker rejected request; check message.\n";
            } else std::cerr << "Outcome UNKNOWN; reconcile before any retry.\n";
        }
        return 0;
    } catch (const std::exception& error) { std::cerr << "FAILED: " << error.what() << '\n'; return 1; }
}
