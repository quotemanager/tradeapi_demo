# C# 示例

要求 Windows、.NET 8 SDK，调用进程为 **x86**，不使用 AnyCPU。代码使用动态加载和 StdCall 委托，不需要额外 NuGet 包。

建议发布为自包含的 x86 可执行程序，避免误用机器上的 64 位 `dotnet.exe`：

```powershell
dotnet publish examples/csharp/TradeApiDemo.csproj -c Release -r win-x86 --self-contained true -o build/csharp
build/csharp/TradeApiDemo.exe --config config/account.local.json
build/csharp/TradeApiDemo.exe --config config/account.local.json query --category 1
build/csharp/TradeApiDemo.exe --config config/account.local.json shareholders
build/csharp/TradeApiDemo.exe --help
```

自包含发布仅打包 .NET 示例自身，不包含 tradeapi 运行包。配置与密码方式见 [快速开始](../../docs/quick-start.md)。

交易命令模板：

```text
TradeApiDemo.exe --config <本地配置> order --category 0 --shareholder <股东代码> --code <证券代码> --price <价格> --quantity <数量>
TradeApiDemo.exe --config <本地配置> cancel --exchange <交易所代码> --order-id <合同号>
```

替换所有占位值。买入／卖出／融资买入类别为 0／1／2。人工确认前不登录、不发送交易。`float` 精确绑定原生 32 位浮点参数，不得换成 `double`。输出指针指向独立可写缓冲区；每次调用重新分配，结束释放。

`TradeApi` 是薄封装，使用 `using` 释放登录和 DLL。它的 Order／Cancel 方法直接发送，人工确认只在 Program.cs 中实现，集成时必须自行落实风控和状态核对。

## 委托与撤单调用代码

完整命令行步骤见 [交易示例](../../docs/trading-examples.md)。以下片段在同一示例项目内复用 `TradeApi` 与已成功登录的 `api`；`shareholder`、`code`、`price`、`quantity` 是已核对的业务输入。**作为现有交易分支的替代示例，不应再追加到已发送交易的分支后面。**

委托（内部调用 `SendOrder`，固定 `PriceType=0`）：

```csharp
// category: 0 买入，1 卖出，2 融资买入；只选择一种。
int category = 0;
// price 的类型为 float，而不是 double。
Console.Error.WriteLine($"category={category} shareholder={shareholder} code={code} price={price} quantity={quantity}");
Console.Error.WriteLine("核对账户和全部参数，输入 SEND ORDER 才发送：");
if (Console.ReadLine() == "SEND ORDER")
{
    JsonElement result = api.Order(category, shareholder, code, price, quantity);
    Console.WriteLine(JsonSerializer.Serialize(result));
    string message = !result.TryGetProperty("accepted", out var accepted)
        ? "结果未知，先查询核对，不重发。"
        : accepted.ValueKind switch
        {
            JsonValueKind.True => "委托已受理，不等于成交；继续查询委托和成交。",
            JsonValueKind.False => "券商拒绝，查看 message。",
            _ => "结果未知，先查询核对，不重发。"
        };
    Console.Error.WriteLine(message);
}
```

撤单（内部调用 `CancelOrder`）：

```csharp
// 先调用 api.Query(4)，从核对后唯一选定的目标行 target 读取参数。
// 这里假定字段为字符串；旧版数字合同号应先无损转换，不能用浮点转换。
string orderId = target.GetProperty("order_id").GetString() ?? "";
string exchangeId = target.GetProperty("exchange_code").GetString() ?? "";
if (orderId.Length == 0 || exchangeId.Length == 0)
    throw new ArgumentException("目标合同号和交易所代码不能为空");
Console.Error.WriteLine($"requested_order_id={orderId} exchange={exchangeId}");
Console.Error.WriteLine("核对目标委托，输入 CANCEL ORDER 才撤单：");
if (Console.ReadLine() == "CANCEL ORDER")
{
    JsonElement result = api.Cancel(exchangeId, orderId);
    Console.WriteLine(JsonSerializer.Serialize(result));
    string message = !result.TryGetProperty("accepted", out var accepted)
        ? "撤单结果未知，先查询原合同号状态，不重发。"
        : accepted.ValueKind switch
        {
            JsonValueKind.True => "撤单请求已受理，不等于最终已撤；查询原合同号状态。",
            JsonValueKind.False => "券商拒绝撤单，查看 message。",
            _ => "撤单结果未知，先查询原合同号状态，不重发。"
        };
    Console.Error.WriteLine(message);
}
```

需引入 `System.Text.Json`，并在现有 `try/catch` 与 `using` 生命周期内使用。封装遇到 `ErrInfo` 会抛错，交易调用抛错时先核对状态，不自动重发。C# 撤单参数顺序为 **交易所代码、原合同号**；返回的撤单受理编号不要当成原合同号再次发送。
