# tradeapi_demo

A 股程序化交易接口多语言调用示例。基于 tradeapi 通达信交易接口，演示登录、查询、买入、卖出、融资买入及撤单，配套通用接口使用说明。

> 本仓库提供调用示例，**不包含 tradeapi 运行包**，也不是交易策略或收益承诺。实际支持范围以获得的运行包及证券账户权限为准。

## 购买与接入咨询

**购买 tradeapi 接口、获取运行包及咨询接入，可通过微信或 Telegram 联系。**

| 微信 | Telegram |
| :---: | :---: |
| <img src="assets/wechat.png" width="280" alt="tradeapi 接口购买与接入咨询微信二维码"> | <img src="assets/telegram.jpg" width="280" alt="tradeapi Telegram 联系二维码 @tradeapi8"> |
| 扫码添加微信 | [@tradeapi8 · 点击联系](https://t.me/tradeapi8) |

二维码用于添加联系人咨询，不是支付码。请勿在 GitHub Issue 中发送账号、密码、授权文件或账户日志。

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

## 接口与示例导航

推荐调用流程：

`OpenTdx → Logon → 查询／股东代码／委托／撤单 → Logoff → CloseTdx`

| 接口 | 用途 | 首页示例 |
| --- | --- | --- |
| `OpenTdx` | 初始化接口资源 | [初始化、登录与退出](#初始化登录与退出) |
| `Logon` | 登录并取得实际 `ClientID` | [初始化、登录与退出](#初始化登录与退出) |
| `QueryData` | 资金、持仓、委托、成交、可撤单及信用类查询 | [数据查询](#数据查询) |
| `QueryShareholderCodes` | 查询当前账户股东代码 | [股东代码查询](#股东代码查询) |
| `SendOrder` | 买入、卖出、融资买入 | [委托示例](#委托示例) |
| `CancelOrder` | 撤销指定合同号的委托 | [撤单示例](#撤单示例) |
| `Logoff` | 退出指定登录 | [初始化、登录与退出](#初始化登录与退出) |
| `CloseTdx` | 释放接口资源 | [初始化、登录与退出](#初始化登录与退出) |

完整的函数声明、参数及 JSON 字段说明见 [通用接口文档](docs/api-usage.md)。所有命令示例默认在**仓库根目录的 PowerShell** 中运行。

## 选择示例程序

先选择下面的一组配置，后续各节统一使用 `& $demo @demoArgs`。`@demoArgs` 是 PowerShell 数组展开语法，不能原样用于 cmd 或 Bash。

Python，使用 32 位解释器：

```powershell
$demo = 'py'
$demoArgs = @('-3-32', 'examples/python/demo.py', '--config', 'config/account.local.json')
```

C++，先按 [构建说明](examples/cpp/README.md) 编译：

```powershell
$demo = '.\build\cpp\Release\tradeapi_demo.exe'
$demoArgs = @('--config', 'config/account.local.json')
```

C#，先按 [发布说明](examples/csharp/README.md) 生成 x86 可执行程序：

```powershell
$demo = '.\build\csharp\TradeApiDemo.exe'
$demoArgs = @('--config', 'config/account.local.json')
```

## 初始化、登录与退出

配置中的 `broker_code` 为接入配置提供的券商及账户类型标识，`account_no` 为登录账号；示例占位值不能直接使用。`host`、`port`、`version` 可分别留空、0、空字符串，使用运行包支持的自动配置。交易密码启动时隐藏输入，或使用 `TRADEAPI_PASSWORD` 环境变量；配置文件不存密码。详见 [配置与密码说明](docs/quick-start.md#配置)。

首次只读验证：

```powershell
& $demo @demoArgs
```

此命令不是“仅登录”，而是自动执行 **初始化 → 登录 → 资金查询 → 退出登录 → 释放资源**。所有查询与交易子命令都会管理相同的生命周期；没有独立的 `login`、`logoff` 命令，命令结束也不保留可供下一次进程使用的 `ClientID`。

在自己的程序中复用会话时，可参考下面的 Python 只读代码。它可以从仓库根目录保存为脚本运行，仍要求 32 位 Python；C++ 使用 RAII、C# 使用 `using` 管理相同生命周期，见各语言源码。

```python
import getpass
import json
import os
import sys

sys.path.insert(0, "examples/python")
from tradeapi import TradeApi, load_config

config = load_config("config/account.local.json")
password = os.environ.get("TRADEAPI_PASSWORD") or getpass.getpass("Trading password: ")

with TradeApi(config) as api:  # 加载 DLL，进入上下文时调用 OpenTdx
    client_id = api.login(password, os.environ.get("TRADEAPI_TX_PASSWORD", ""))
    # 封装保存本次 ClientID，后续调用自动使用它，不要固定传 1。
    print(json.dumps(api.query(0), ensure_ascii=False, indent=2))
    print(json.dumps(api.shareholders(), ensure_ascii=False, indent=2))
# 离开上下文时自动 Logoff、CloseTdx；查询抛错也会执行清理。
```

登录失败不能继续查询或交易。重新登录后必须使用新返回的 `ClientID`；不要把示例的多次命令调用当成同一登录会话。

## 数据查询

`QueryData` 通过 `Category` 选择查询内容。三种语言均使用 `query --category`，各项是否可用取决于账户权限和运行包支持范围。

| Category | 查询内容 | 返回结构的主要字段 |
| ---: | --- | --- |
| 0 | 资金 | `balance`、`available`、`total_assets` 等 |
| 1 | 持仓 | `positions` 数组 |
| 2 | 当日委托 | `orders` 数组 |
| 3 | 当日成交 | `trades` 数组 |
| 4 | 可撤单列表，仅查询不撤单 | `orders` 数组 |
| 5 | 信用综合查询 | `funds`、`financing`、`short_selling` 数组 |
| 6 | 融资／融券标的证券 | `financing`、`short_selling` 对象 |

以下命令按需单独执行，每条都会登录、查询并退出。类别 5、6 仅用于适用的信用账户与功能：

```powershell
& $demo @demoArgs query --category 0  # 资金
& $demo @demoArgs query --category 1  # 持仓
& $demo @demoArgs query --category 2  # 当日委托
& $demo @demoArgs query --category 3  # 当日成交
& $demo @demoArgs query --category 4  # 可撤单列表，不发送撤单
& $demo @demoArgs query --category 5  # 信用综合查询
& $demo @demoArgs query --category 6  # 融资／融券标的证券
```

资金返回示例（虚构数据，仅列常用字段）：

```json
{"schema":"tradeapi.funds.v1","balance":"10000.00","available":"8000.00","total_assets":"15000.00"}
```

持仓为空的示例：

```json
{"schema":"tradeapi.holdings.v1","count":0,"positions":[]}
```

金额、价格、数量一般按字符串返回；缺失字段或 `null` 不等于 0，空数组不是查询失败。调用报错时不使用本次数据；各语言封装会检查 `ErrInfo` 并抛错。完整返回示例见 [查询接口说明](docs/api-usage.md#5-数据查询-querydata)。

## 股东代码查询

`QueryShareholderCodes` 返回当前账户的股东列表：

```powershell
& $demo @demoArgs shareholders
```

返回示例（虚构数据）：

```json
{"schema":"tradeapi.shareholder_codes.v1","count":1,"shareholders":[{"market":"SH","shareholder_code":"E000000000"}]}
```

按证券所属市场及账户选择对应 `shareholder_code`，委托时传给 `--shareholder`（底层 `Gddm`）。同一市场可能有多项记录，不能随意取第一项；有股东代码也不代表已开通相应交易权限。

## 委托示例

`SendOrder` 支持示例中的买入、卖出、融资买入：类别分别为 0、1、2。**一次只选择一个方向；可能形成真实交易。** 先查询股东代码、资金／持仓，核对证券、价格、数量和权限，再输入本笔参数：

```powershell
$category = Read-Host '本笔方向：0 买入 / 1 卖出 / 2 融资买入'
$shareholder = Read-Host '本笔对应的股东代码'
$code = Read-Host '证券代码（保留前导零）'
$price = Read-Host '限价价格（使用英文小数点）'
$quantity = Read-Host '数量（股票为股，基金为份）'
& $demo @demoArgs order --category $category --shareholder $shareholder --code $code --price $price --quantity $quantity
```

核对程序展示的信息后，必须手动输入 `SEND ORDER` 才继续；其他输入中止，不登录、不发送委托。当前示例固定 `PriceType=0`（限价），原生价格类型为 32 位 `float`。

`accepted:true` 表示受理而非成交，`false` 表示券商拒绝，`null` 或缺失表示未知。交易调用抛错也可能已经发出，先查询当日委托／成交核对，不自动重发。完整步骤和各语言调用代码见 [委托与撤单示例](docs/trading-examples.md)。

## 撤单示例

`CancelOrder` 需要原合同号，交易所代码优先使用同一条可撤单记录中的值。先查询，再选择唯一目标：

```powershell
& $demo @demoArgs query --category 4
$orderId = Read-Host '目标可撤单记录的 order_id'
$exchange = Read-Host '同一条记录的 exchange_code'
& $demo @demoArgs cancel --exchange $exchange --order-id $orderId
```

核对目标后，必须手动输入 `CANCEL ORDER` 才继续。合同号不是证券代码，`exchange_code` 也不是股东查询里的 `SH`／`SZ`／`BJ`；不要自行推算。

仅当运行包与账户支持自动补全交易所代码时，才可改为 `cancel --order-id $orderId`，不要针对同一目标连续执行两种用法。撤单受理不等于最终已撤，返回的 `order_id` 可能是新受理编号；请用原合同号核对当日委托状态，不只凭可撤单列表中目标消失作判断。更多示例见 [撤单调用说明](docs/trading-examples.md#3-撤单)。

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

示例仅供开发参考，请遵守券商服务协议及适用规则，自行做好账户安全与风险控制。运行包、商标和联系方式二维码不因本仓库公开而获得再分发授权。示例源码许可证尚未指定；公开可见不等于已授予任意复制、修改和分发许可。
