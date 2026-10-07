# C++ 示例

要求 Windows、C++17 编译器、CMake 3.20+，目标 **x86**。动态加载 DLL，不需要 `.lib`。构建时获取固定版本的 [nlohmann/json 3.11.3](https://github.com/nlohmann/json/tree/v3.11.3)（MIT 许可证），首次配置需要访问 GitHub；不提交其下载缓存。

以安装 C++ 工作负载的 Visual Studio 2022 为例，从仓库根目录执行：

```powershell
cmake -S examples/cpp -B build/cpp -G "Visual Studio 17 2022" -A Win32
cmake --build build/cpp --config Release
build/cpp/Release/tradeapi_demo.exe --config config/account.local.json
build/cpp/Release/tradeapi_demo.exe --config config/account.local.json query --category 1
build/cpp/Release/tradeapi_demo.exe --config config/account.local.json shareholders
build/cpp/Release/tradeapi_demo.exe --help
```

构建工具未加入 PATH 时，使用 Visual Studio Developer PowerShell。不得改为 x64 或 AnyCPU。配置说明见 [快速开始](../../docs/quick-start.md)。

交易命令模板：

```text
tradeapi_demo.exe --config <本地配置> order --category 0 --shareholder <股东代码> --code <证券代码> --price <价格> --quantity <数量>
tradeapi_demo.exe --config <本地配置> cancel --exchange <交易所代码> --order-id <合同号>
```

将所有占位值替换为实际值。买入／卖出／融资买入类别为 0／1／2。最终人工确认之前不登录、不发送交易；超时、未知结果不自动重发。

示例将 API 输出解析成 JSON，不根据字段顺序或非空合同号猜测成功。`TradeApi` 使用 RAII 释放资源；它的 `order`／`cancel` 方法直接发送，CLI 才包含人工确认，集成时需要自行保留风险检查。路径命令行建议使用 ASCII，配置文件内的运行目录支持 UTF-8 中文路径。

## 委托与撤单调用代码

完整命令和参数来源见 [交易示例](../../docs/trading-examples.md)。以下片段复用 `main.cpp` 中的 `TradeApi`、`Json` 和已成功登录的 `api`，用于替换相应业务分支，**不要与现有 CLI 分支连续执行造成重复提交**。

委托（内部调用 `SendOrder`，固定 `PriceType=0`）：

```cpp
// category: 0 买入，1 卖出，2 融资买入；只选择一种。
int category = 0;
// shareholder、code、price、quantity 为已核对的输入；price 必须是 float。
std::cerr << "category=" << category << " shareholder=" << shareholder
          << " code=" << code << " price=" << price << " quantity=" << quantity << '\n';
std::string confirmation;
std::cerr << "Verify account and parameters. Type SEND ORDER exactly:\n";
if (std::getline(std::cin, confirmation) && confirmation == "SEND ORDER") {
    Json result = api.order(category, shareholder, code, price, quantity);
    std::cout << result.dump(2) << '\n';
    if (!result.contains("accepted") || !result["accepted"].is_boolean())
        std::cerr << "Outcome UNKNOWN; reconcile before retry.\n";
    else if (result["accepted"].get<bool>())
        std::cerr << "Order accepted, NOT executed. Query order/trade status.\n";
    else
        std::cerr << "Broker rejected the order; check message.\n";
}
```

撤单（内部调用 `CancelOrder`）：

```cpp
// 先用 api.query(4) 获取列表，再由使用者/业务规则唯一选定 target。
// 此片段假定目标字段是非空字符串；若接入旧版数字合同号，应先无损转为字符串。
std::string orderId = target.at("order_id").get<std::string>();
std::string exchangeId = target.at("exchange_code").get<std::string>();
if (orderId.empty() || exchangeId.empty())
    throw std::runtime_error("Missing cancellation target fields");
std::cerr << "requested_order_id=" << orderId << " exchange=" << exchangeId << '\n';
std::string confirmation;
std::cerr << "Type CANCEL ORDER exactly:\n";
if (std::getline(std::cin, confirmation) && confirmation == "CANCEL ORDER") {
    Json result = api.cancel(exchangeId, orderId);
    std::cout << result.dump(2) << '\n';
    if (!result.contains("accepted") || !result["accepted"].is_boolean())
        std::cerr << "Outcome UNKNOWN; reconcile original order status.\n";
    else if (result["accepted"].get<bool>())
        std::cerr << "Cancellation accepted, NOT final. Query original order status.\n";
    else
        std::cerr << "Broker rejected cancellation; check message.\n";
}
```

上述调用需放在现有 `try/catch` 范围内。封装遇到 `ErrInfo` 或解析异常会抛错；交易调用抛错也不能直接再次调用。C++ 撤单参数顺序为 **交易所代码、原合同号**。撤单返回的 `order_id` 可能是新受理编号，不应覆盖原合同号。
