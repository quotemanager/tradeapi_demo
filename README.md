# tradeapi_demo

A 股程序化交易接口多语言调用示例。基于 tradeapi 通达信交易接口，演示登录、查询、买入、卖出、融资买入及撤单，配套通用接口使用说明。

> 本仓库提供调用示例，**不包含 tradeapi 运行包**，也不是交易策略或收益承诺。实际支持范围以获得的运行包及证券账户权限为准。

## 购买与接入咨询

**购买 tradeapi 接口、获取运行包及咨询接入，请扫描下方微信二维码联系。**

<p align="center">
  <img src="assets/wechat.png" width="280" alt="tradeapi 接口购买与接入咨询微信二维码">
</p>

二维码用于添加微信咨询，不是支付码。请勿在 GitHub Issue 中发送账号、密码、授权文件或账户日志。

## 快速开始

1. 准备 Windows 与完整的 tradeapi 发布目录，不要只复制 `tradeApi.dll`。
2. 选择一种语言，确保调用进程为 **32 位（x86）**。
3. 将 [配置模板](config/account.example.json) 复制为 `config/account.local.json`，填写运行目录、券商标识和账号。
4. 按对应语言说明启动；默认只查询资金，不下单、不撤单。

| 语言 | 接入方式 | 使用说明 |
| --- | --- | --- |
| Python | 标准库 `ctypes.WinDLL`，无第三方 Python 依赖 | [Python 示例](examples/python/README.md) |
| C++ | Windows 动态加载，CMake 构建；JSON 使用 nlohmann/json | [C++ 示例](examples/cpp/README.md) |
| C# | 动态加载与 StdCall 委托，.NET 8 / x86 | [C# 示例](examples/csharp/README.md) |

所有示例使用相同命令：

```text
--config <配置文件>                         默认：查询资金
--config <配置文件> query --category 1      查询持仓；类别范围 0–6
--config <配置文件> shareholders            查询股东代码
--config <配置文件> order --category 0 --shareholder <股东代码> --code <证券代码> --price <价格> --quantity <数量>
--config <配置文件> cancel --exchange <交易所代码> --order-id <合同号>
```

`order --category`：`0` 买入、`1` 卖出、`2` 融资买入。操作是否支持取决于运行包及账户权限。`cancel --exchange` 可省略，但仅适用于支持自动补全的账户。撤单参数应取自可撤单查询结果，不要自行推算。

## 委托与撤单示例

见 [完整委托与撤单示例](docs/trading-examples.md)：提供三种语言的操作入口、买入／卖出／融资买入命令、可撤单参数获取、撤单调用及返回结果解释。各语言 README 同时提供可集成的核心调用代码。

委托用 `order`（底层 `SendOrder`），撤单用 `cancel`（底层 `CancelOrder`）。默认入口仍只查询资金；交易必须另行选择，并手动确认 `SEND ORDER` 或 `CANCEL ORDER`，不自动重复发送。

## 功能与约定

- 覆盖 `OpenTdx`、`Logon`、`QueryData`、`QueryShareholderCodes`、`SendOrder`、`CancelOrder`、`Logoff`、`CloseTdx`。
- 查询类别：资金、持仓、当日委托、当日成交、可撤单、信用综合查询、融资／融券标的证券。
- `host`、`port`、`version` 可留空／0，使用运行包支持的自动配置。
- 使用实际登录返回的 `ClientID`；不固定传 `1`。
- 输出业务 JSON；另行提示 `accepted` 为 `true`、`false`、`null` 或缺失时的含义。
- 交易前展示参数，必须手动输入 `SEND ORDER` 或 `CANCEL ORDER`；**不支持跳过确认**。
- 无自动重发交易、无后台循环、无策略执行；每次运行建立会话，结束时释放。

**交易接口可能形成真实委托或撤单，即使非交易时间也不能保证不受理。** 受理不等于成交或撤销完成。超时、断线、未知结果时，先核对委托／成交状态，不要直接重复发送。

## 文档

- [环境与首次调用](docs/quick-start.md)
- [通用接口使用说明](docs/api-usage.md)
- [委托与撤单调用示例](docs/trading-examples.md)
- [常见问题](docs/troubleshooting.md)
- [测试说明](tests/README.md)
- [敏感信息与问题反馈](SECURITY.md)

示例用 `BROKER_A:normal` 等占位值，不枚举券商支持清单。请按取得的接入配置填写真实标识，示例数据不能直接用于交易。

## 开发与测试

```powershell
python -m unittest discover -s tests -v
```

纯解析测试可在没有 DLL 的环境运行。仓库另外提供无网络的模拟 DLL 和 Windows CI，检查三种语言的 ABI 与示例流程；模拟测试通过**不表示实盘验证通过**。CI 不使用任何真实证券账户。

## 使用范围

示例仅供开发参考，请遵守券商服务协议及适用规则，自行做好账户安全与风险控制。运行包、商标和微信二维码不因本仓库公开而获得再分发授权。示例源码许可证尚未指定；公开可见不等于已授予任意复制、修改和分发许可。
