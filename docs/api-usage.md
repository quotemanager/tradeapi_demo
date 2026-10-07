# tradeApi 接口使用说明（通用版）

本文面向 `tradeApi.dll` 调用方，说明各券商共用的接口调用方式、参数及基本返回格式，不列举具体券商的适配清单。示例中的券商代码、账号、股东代码、证券及金额均为虚构或示意数据，使用时须替换为实际值，不能直接用于交易。

## 1. 接入约定

- 运行平台：Windows；调用程序须为 **32 位（x86）**。
- 使用发布包内的 `tradeApi.dll` 和 `tradeApi.h`，保留整个发布目录，不要只复制 DLL。
- 调用约定为 `__stdcall`；C/C++ 可按 `tradeApi.h` 声明动态加载 DLL，其他语言按下面声明绑定函数。
- `int` 为 32 位，`short` 为 16 位，`float` 为 32 位；不要把 `Price` 绑定为 `double`。
- 字符串使用以 `\0` 结尾的窄字符字符串。券商标识、地址、版本、数字账号及证券代码使用 ASCII；其他输入按所用券商要求编码。
- `ErrInfo` 是调用方分配的可写缓冲区，至少 **256 字节**；中文错误按 GB18030 兼容编码读取。
- `Result` 是调用方分配的可写缓冲区，至少 **1,048,577 字节（1 MiB + 1）**，返回以 `\0` 结尾的 JSON。实际中文可能以 `\uXXXX` 转义，使用 JSON 库解析即可。
- 每次调用前清空 `ErrInfo`，有 `Result` 时同时清空；不得传入只读字符串作为输出缓冲区。
- 同一 `ClientID` 的调用建议串行进行；多线程不得共用输出缓冲区。

推荐调用顺序：

`OpenTdx → Logon → QueryData / QueryShareholderCodes / SendOrder / CancelOrder → Logoff → CloseTdx`

各券商、账户类型、市场及交易品种的支持范围以提供的发布包为准；接口未支持的操作会报错。登录成功不表示所有市场和品种均有交易权限。

## 2. 函数声明

```c
void __stdcall OpenTdx(void);
void __stdcall CloseTdx(void);

int __stdcall Logon(
    char *BrokerCode,
    char *IP,
    short Port,
    char *Version,
    short YybID,
    char *AccountNo,
    char *TradeAccount,
    char *JyPassword,
    char *TxPassword,
    char *ErrInfo);

void __stdcall Logoff(int ClientID);

void __stdcall QueryData(
    int ClientID,
    int Category,
    char *Result,
    char *ErrInfo);

void __stdcall QueryShareholderCodes(
    int ClientID,
    char *Result,
    char *ErrInfo);

void __stdcall SendOrder(
    int ClientID,
    int Category,
    int PriceType,
    char *Gddm,
    char *Zqdm,
    float Price,
    int Quantity,
    char *Result,
    char *ErrInfo);

void __stdcall CancelOrder(
    int ClientID,
    char *ExchangeID,
    char *OrderID,
    char *Result,
    char *ErrInfo);
```

除 `Logon` 外，上述函数均返回 `void`，不能通过函数返回值判断查询或交易结果。

## 3. 初始化与退出

| 接口 | 使用方法 |
| --- | --- |
| `OpenTdx()` | 进程初始化时调用一次，在 `Logon` 之前调用 |
| `Logoff(ClientID)` | 退出指定登录；退出后不再使用该 `ClientID` |
| `CloseTdx()` | 进程结束前释放全部登录及资源；调用后所有 `ClientID` 失效 |

## 4. 登录 Logon

| 参数 | 说明 |
| --- | --- |
| `BrokerCode` | 券商及账户类型标识，格式为 `<券商代码>:<账户类型>`；实际标识以提供的接入配置为准 |
| `IP` | 交易服务器地址；可传 `NULL` 或空字符串，使用所提供配置自动选择 |
| `Port` | 交易端口；可传 `0` 自动选择。显式地址及端口须为券商有效交易线路 |
| `Version` | 协议版本；可传 `NULL` 或空字符串使用所提供配置。若包的接入要求指定版本，则按提供值填写 |
| `YybID` | 营业部标识；无特别要求传 `0` |
| `AccountNo` | 登录账号，必填；按字符串原样传入，保留前导零 |
| `TradeAccount` | 交易账号；与登录账号相同时可传相同值或空字符串 |
| `JyPassword` | 交易密码，必填 |
| `TxPassword` | 通讯密码；不使用时传空字符串 |
| `ErrInfo` | 错误说明输出缓冲区 |

标识示例：假设券商代码为 `BROKER_A`，普通账户使用 `BROKER_A:normal`，融资融券账户使用 `BROKER_A:margin`。其中 `normal` 表示普通账户，`margin` 表示融资融券账户；`BROKER_A` 仅为占位示例，不是可直接使用的券商代码，也不表示支持范围。

成功返回 **大于 0 的 `ClientID`**；失败返回 **`-1`**，原因见 `ErrInfo`。后续接口必须使用本次实际返回的值，不要固定传 `1`。重新登录后使用新返回值。

## 5. 数据查询 QueryData

`QueryData(ClientID, Category, Result, ErrInfo)`

`ClientID` 为登录返回值；`Category` 选择查询类别；`Result` 和 `ErrInfo` 为输出缓冲区。

| Category | 查询内容 | schema | 主要数据字段 |
| ---: | --- | --- | --- |
| 0 | 资金 | `tradeapi.funds.v1` | `balance`、`available`、`total_assets` 等 |
| 1 | 持仓 | `tradeapi.holdings.v1` | `positions` 数组 |
| 2 | 当日委托 | `tradeapi.orders.v1` | `orders` 数组 |
| 3 | 当日成交 | `tradeapi.trades.v1` | `trades` 数组 |
| 4 | 可撤单列表（仅查询，不撤单） | `tradeapi.cancelable_orders.v1` | `orders` 数组 |
| 5 | 信用综合查询 | `tradeapi.credit_summary.v1` | `funds`、`financing`、`short_selling` 数组 |
| 6 | 融资／融券标的证券 | `tradeapi.eligible_securities.v1` | `financing`、`short_selling` 对象 |

类别 `5`、`6` 用于融资融券业务，是否可调用取决于所提供版本的功能支持及账户权限。

通用规则：

- `ErrInfo` 为空时解析 `Result`；非空时本次查询失败，不使用本次数据。
- `schema` 标识 JSON 结构；`broker_code` 和 `account_variant` 标识券商及账户类型。
- 金额、价格、数量等数据一般为字符串，未提供的可选值可能为 `null`。不要把缺失值当成 `0`。
- `count: 0` 与空数组表示当前没有记录，不是错误；`count` 对应返回记录数。
- 字段可能随券商不同而缺省或扩展。按字段名解析，忽略不需要的字段，不依赖 JSON 字段顺序。

### 5.1 资金

```json
{
  "schema": "tradeapi.funds.v1",
  "broker_code": "BROKER_A",
  "account_variant": "margin",
  "category": 0,
  "currency_code": "0",
  "currency_name": "人民币",
  "balance": "10000.00",
  "available": "8000.00",
  "total_assets": "15000.00",
  "withdrawable": "7000.00",
  "frozen": "2000.00"
}
```

`balance` 为余额，`available` 为可用资金，`total_assets` 为总资产，`withdrawable` 为可取资金，`frozen` 为冻结资金。具体资金口径以券商为准。

### 5.2 持仓

```json
{
  "schema": "tradeapi.holdings.v1",
  "broker_code": "BROKER_A",
  "account_variant": "margin",
  "category": 1,
  "count": 1,
  "positions": [{
    "security_code": "600000",
    "security_name": "示例证券",
    "quantity": "1000",
    "sellable_quantity": "800",
    "cost_price": "10.00",
    "current_price": "10.50",
    "market_value": "10500.00",
    "profit_loss": "500.00",
    "shareholder_code": "E000000000"
  }]
}
```

`quantity` 为持仓数量，`sellable_quantity` 为可卖数量，`cost_price` 为成本价，`current_price` 为当前价，`market_value` 为市值，`profit_loss` 为盈亏。

### 5.3 当日委托、当日成交与可撤单

```json
{
  "schema": "tradeapi.orders.v1",
  "broker_code": "BROKER_A",
  "account_variant": "margin",
  "category": 2,
  "count": 1,
  "orders": [{
    "order_id": "123456",
    "security_code": "600000",
    "security_name": "示例证券",
    "exchange_code": "1",
    "order_price": "10.00",
    "order_quantity": "100",
    "executed_quantity": "0"
  }]
}
```

委托常用字段：`order_id`（合同号）、`order_time`（委托时间）、`exchange_code`（交易所代码）、`side_name`（方向）、`order_price`（委托价格）、`order_quantity`（委托数量）、`executed_quantity`（成交数量）、`canceled_quantity`（撤单数量）、`status`（委托状态）、`result_message`（提示）。状态表示及可选字段依券商而异。

可撤单返回相同类型的 `orders` 数组，`schema` 为 `tradeapi.cancelable_orders.v1`、`category` 为 `4`。撤单所需合同号、交易所代码应从查询结果取得，不要自行推算。

当日成交的空结果示例：

```json
{"schema":"tradeapi.trades.v1","broker_code":"BROKER_A","account_variant":"margin","category":3,"count":0,"trades":[]}
```

有成交时，每行常用字段为 `trade_id`（成交编号）、`trade_time`（成交时间）、`order_id`（原合同号）、`security_code`、`security_name`、`side_name`、`trade_price`（成交价格）、`trade_quantity`（成交数量）、`trade_amount`（成交金额）。

类别 `5` 的三组数组使用 `label`（项目名称）、`value`（值）等字段。类别 `6` 的两组对象包含 `count`、`columns` 和 `rows`：`columns` 给出列名，`rows` 中每行是按对应列顺序排列的数组，应按列名定位证券代码、名称等，不要固定列序。

## 6. 股东代码 QueryShareholderCodes

`QueryShareholderCodes(ClientID, Result, ErrInfo)`

参数含义与查询接口一致。返回当前登录账户的股东列表，例如：

```json
{
  "schema": "tradeapi.shareholder_codes.v1",
  "broker_code": "BROKER_A",
  "account_variant": "margin",
  "count": 2,
  "shareholders": [
    {"market":"SH","shareholder_code":"E000000000"},
    {"market":"SZ","shareholder_code":"0000000000"}
  ]
}
```

`market` 常见值为 `SH`（沪市）、`SZ`（深市）、`BJ`（北交所）；`UNKNOWN` 表示未确定市场。调用方根据市场和账户选择正确的 `shareholder_code`，作为委托的 `Gddm`。同一市场可能有多条记录，不能随意取第一条；股东代码存在也不代表已开通交易权限。

## 7. 委托 SendOrder

| 参数 | 说明 |
| --- | --- |
| `ClientID` | `Logon` 返回的登录标识 |
| `Category` | `0` 普通买入，`1` 卖出，`2` 融资买入；融资买入需融资融券账户、相应交易权限及接口功能支持 |
| `PriceType` | 当前通用用法为 `0`（限价）；不要自行传入其他报价方式 |
| `Gddm` | 与账户及交易市场匹配的股东代码，必填 |
| `Zqdm` | 证券代码，按字符串传入并保留前导零，必填 |
| `Price` | 限价价格，必须大于 0；类型为 `float`，按证券价格档位填写 |
| `Quantity` | 正整数数量；股票单位为股，基金为份，须满足对应品种委托规则 |
| `Result` | 委托结果 JSON 输出缓冲区 |
| `ErrInfo` | 调用错误输出缓冲区 |

**调用即可能提交真实委托。** 调用方应先确认账户、市场、方向、价格、数量及权限。

多语言命令及核心调用代码见 [委托与撤单调用示例](trading-examples.md)。该示例覆盖普通买入、卖出和融资买入；一次只选择一项，不应连续执行全部交易示例。

成功受理示例（不是成交结果）：

```json
{"schema":"tradeapi.order.v1","broker_code":"BROKER_A","account_variant":"margin","accepted":true,"order_id":"123456","message":null}
```

券商拒绝示例：

```json
{"schema":"tradeapi.order.v1","broker_code":"BROKER_A","account_variant":"margin","accepted":false,"order_id":"-1","message":"当前时间不允许委托"}
```

上例仅列调用方常用字段，实际结果可能包含其他字段。`order_id` 是券商返回的合同号，建议始终以字符串保存和传递；如调用方兼容旧版数字格式，应避免整数溢出或精度损失。

| accepted | 调用方处理 |
| --- | --- |
| `true` | 委托已受理；保存 `order_id`，查询当日委托／成交跟踪状态 |
| `false` | 委托被拒绝；查看 `message`，不可当成成功 |
| `null` 或缺失 | 结果未确定；先查询核对，不要直接重复下单 |

`ErrInfo` 为空也可能得到业务拒绝。受理不等于成交，`order_id` 非空也不等于受理成功。

## 8. 撤单 CancelOrder

| 参数 | 说明 |
| --- | --- |
| `ClientID` | `Logon` 返回的登录标识 |
| `ExchangeID` | 目标订单的交易所代码，优先传可撤单结果中的 `exchange_code`；支持自动补全的账户可传空字符串或 `NULL` |
| `OrderID` | 目标订单的合同号，传可撤单结果中的 `order_id`，必填；不是证券代码或本地序号 |
| `Result` | 撤单结果 JSON 输出缓冲区 |
| `ErrInfo` | 调用错误输出缓冲区 |

先用 `QueryData(ClientID, 4, Result, ErrInfo)` 获取可撤单目标，再调用撤单接口。是否可省略 `ExchangeID` 以对应发布包支持范围为准；省略时无法唯一定位目标会报错。

获取目标参数、显式传入交易所代码及省略交易所代码的两种调用方式，见 [撤单操作示例](trading-examples.md#3-撤单)。两种方式是替代用法，不要对同一目标连续尝试。

受理示例：

```json
{"schema":"tradeapi.cancel.v1","broker_code":"BROKER_A","account_variant":"normal","accepted":true,"order_id":"123","message":null}
```

结果待核对示例：

```json
{"schema":"tradeapi.cancel.v1","broker_code":"BROKER_A","account_variant":"normal","accepted":null,"order_id":null,"requested_order_id":"123456","requested_exchange_id":"1","reconciliation_required":true,"message":"请查询委托状态确认撤单结果"}
```

示例仅列常用字段及示意消息。`accepted:true` 表示撤单请求受理，**不等于已经撤销完成**。返回的 `order_id` 可能是撤单受理编号，不一定是原合同号；若提供 `requested_order_id`，它表示本次请求撤销的原合同号。

无论撤单受理还是结果待核对，都应通过当日委托及可撤单列表确认目标的最终状态；`accepted:false` 表示拒绝，可查看 `message`。不要仅凭可撤单列表中目标消失判断已撤销，订单也可能已经成交。

## 9. C 调用示例（只查询，不交易）

下例使用 Windows 动态加载，不需要额外导入库。替换 DLL 绝对路径、账号、密码和券商标识，使用 x86 编译；代码中的缓冲区大小不可缩小。示例只执行资金查询。

```c
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

/* 兼容缺少以下常量的旧编译器头文件；运行系统须支持此加载方式。 */
#ifndef LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR
#define LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR 0x00000100
#endif
#ifndef LOAD_LIBRARY_SEARCH_DEFAULT_DIRS
#define LOAD_LIBRARY_SEARCH_DEFAULT_DIRS 0x00001000
#endif

typedef void (__stdcall *OpenFn)(void);
typedef int (__stdcall *LogonFn)(char *, char *, short, char *, short,
                                 char *, char *, char *, char *, char *);
typedef void (__stdcall *LogoffFn)(int);
typedef void (__stdcall *QueryFn)(int, int, char *, char *);

int main(void) {
    char error[256] = {0};
    char *result = (char *)calloc(1048577, 1);
    HMODULE dll;
    OpenFn open_tdx, close_tdx;
    LogonFn logon;
    LogoffFn logoff;
    QueryFn query_data;
    int client;
    if (result == NULL) return 1;

    dll = LoadLibraryExW(L"C:\\TradeApi\\tradeApi.dll", NULL,
                         LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (dll == NULL) { free(result); return 1; }
    open_tdx = (OpenFn)GetProcAddress(dll, "OpenTdx");
    close_tdx = (OpenFn)GetProcAddress(dll, "CloseTdx");
    logon = (LogonFn)GetProcAddress(dll, "Logon");
    logoff = (LogoffFn)GetProcAddress(dll, "Logoff");
    query_data = (QueryFn)GetProcAddress(dll, "QueryData");
    if (!open_tdx || !close_tdx || !logon || !logoff || !query_data) {
        FreeLibrary(dll);
        free(result);
        return 1;
    }

    open_tdx();
    client = logon("BROKER_A:margin", "", 0, "", 0,
                   "YOUR_ACCOUNT", "", "YOUR_PASSWORD", "", error);
    if (client <= 0) {
        fprintf(stderr, "Logon failed: %s\n", error);
        close_tdx();
        FreeLibrary(dll);
        free(result);
        return 1;
    }

    result[0] = '\0';
    error[0] = '\0';
    query_data(client, 0, result, error);
    if (error[0] != '\0') fprintf(stderr, "QueryData failed: %s\n", error);
    else puts(result); /* 业务代码使用 JSON 库解析 */

    logoff(client);
    close_tdx();
    FreeLibrary(dll);
    free(result);
    return 0;
}
```

## 10. 调用错误处理

- `Logon` 失败时读取 `ErrInfo`，不继续调用该登录的查询或交易接口。
- 查询失败时记录错误，勿把旧缓冲区数据作为本次查询成功结果。
- 委托或撤单超时、断线、报错或结果未确定时，请先查询核对实际状态，**不要自动重复发送**；请求可能已被券商受理。
- 如当前登录明确失效，先 `Logoff`，再 `Logon`，使用新返回的 `ClientID`。重新登录不等于允许重发上一笔交易。
- 不要在日志、截图或问题反馈中附带密码及完整账户配置。问题反馈提供接口名称、发生时间和错误文字即可。
