# 委托与撤单调用示例

本文将买入、卖出、融资买入、撤单单独展开。三种语言的程序均已实现对应调用，下面的命令可从仓库根目录执行；先完成各语言的环境准备与本地配置。

**可能形成真实委托或撤单，不因闭市而保证无效。** 每次只选择一项操作，不要把买入、卖出、融资买入命令整段连续执行。所有参数由使用者输入，不提供可原样提交的示例证券、价格、股东代码或合同号。

## 1. 选择示例程序

在 PowerShell 中只选择与自己环境相符的一组，后文用 `& $demo @demoArgs` 调用。数组展开是 PowerShell 的语法，不能照搬到 cmd 或 Bash。

Python（32 位）：

```powershell
$demo = 'py'
$demoArgs = @('-3-32', 'examples/python/demo.py', '--config', 'config/account.local.json')
```

C++（先按该目录 README 构建）：

```powershell
$demo = '.\build\cpp\Release\tradeapi_demo.exe'
$demoArgs = @('--config', 'config/account.local.json')
```

C#（先按该目录 README 发布 x86 可执行程序）：

```powershell
$demo = '.\build\csharp\TradeApiDemo.exe'
$demoArgs = @('--config', 'config/account.local.json')
```

示例每次命令都会登录并在结束时退出；委托和撤单不会因为结果未知而自动重发。业务集成可在同一登录会话内串行复用 API。

## 2. 买入、卖出和融资买入

先查询股东代码与资金／持仓：

```powershell
& $demo @demoArgs shareholders
& $demo @demoArgs query --category 0
& $demo @demoArgs query --category 1
```

从股东查询结果中选择与市场、账户相符的 `shareholder_code`，不要自动取第一项。卖出需核对可卖数量；融资买入需相应信用账户、权限与接口支持。价格档位、数量单位和最小申报数量按实际品种规则填写，下面不替使用者判断交易权限或可成交性。

输入**一笔**准备实际提交的参数：

```powershell
$shareholder = Read-Host '本笔委托对应的股东代码'
$code = Read-Host '证券代码（保留前导零）'
$price = Read-Host '限价价格（小数点用英文句点）'
$quantity = Read-Host '数量（股票为股，基金为份）'
```

普通买入（Category=0）：

```powershell
& $demo @demoArgs order --category 0 --shareholder $shareholder --code $code --price $price --quantity $quantity
```

卖出（Category=1），**与买入示例二选一**，核对参数后执行：

```powershell
& $demo @demoArgs order --category 1 --shareholder $shareholder --code $code --price $price --quantity $quantity
```

融资买入（Category=2），仅相应账户与接口支持时选择：

```powershell
& $demo @demoArgs order --category 2 --shareholder $shareholder --code $code --price $price --quantity $quantity
```

程序会展示券商、掩码账号、方向、股东代码、证券代码、价格及数量。再次核对后，手动输入 `SEND ORDER` 并回车才继续。其他输入会中止，不登录也不发送委托；不要用管道或脚本自动填入确认口令。

三种语言的调用均固定 `PriceType=0`（限价），价格绑定为 32 位 `float`。不要传其他报价方式，也不要将原生价格类型改成 `double`。

## 3. 撤单

先查询可撤单列表（这一步不撤单）：

```powershell
& $demo @demoArgs query --category 4
```

从目标行取得 `order_id` 和 `exchange_code`。合同号、交易所代码都按字符串原样保留；交易所代码不是股东查询里的 `SH`／`SZ`／`BJ`，也不是证券代码。

```powershell
$orderId = Read-Host '可撤单目标行的 order_id'
$exchange = Read-Host '同一目标行的 exchange_code'
& $demo @demoArgs cancel --exchange $exchange --order-id $orderId
```

程序展示目标合同号与交易所，再次核对后，手动输入 `CANCEL ORDER` 才继续。不确认则不登录、不撤单。可撤单查询到实际撤单之间，委托可能已经成交或状态变化，以券商最新结果为准。

仅当当前账户与运行包支持自动补全交易所时，才可省略 `--exchange`：

```powershell
& $demo @demoArgs cancel --order-id $orderId
```

显式传值和省略传值是两种替代用法，**不要针对同一笔目标连续执行两次撤单来试哪个有效**。不要用撤单响应中的受理编号替代原合同号再撤一次。

## 4. 如何判断结果

先判断调用是否报错，再解释业务 JSON。各语言封装已检查 `ErrInfo`；非空时抛出错误，不使用本次 `Result`。进程退出码 0 只表示示例流程完成，不代表券商一定受理。

委托受理示例（仅虚构返回数据）：

```json
{"schema":"tradeapi.order.v1","accepted":true,"order_id":"123456","message":null}
```

委托业务拒绝示例：

```json
{"schema":"tradeapi.order.v1","accepted":false,"order_id":"-1","message":"当前时间不允许委托"}
```

撤单受理示例：

```json
{"schema":"tradeapi.cancel.v1","accepted":true,"order_id":"789","requested_order_id":"123456","requested_exchange_id":"1","cancellation_completed":null}
```

上面的 `789` 是撤单受理编号，`123456` 才是请求撤销的原合同号。部分券商可能不返回所有示例字段，不依赖字段顺序。

结果未知示例：

```json
{"schema":"tradeapi.cancel.v1","accepted":null,"order_id":null,"requested_order_id":"123456","reconciliation_required":true}
```

| 返回情况 | 应如何处理 |
| --- | --- |
| `accepted:true` | 请求已受理；委托不等于成交，撤单不等于最终已撤 |
| `accepted:false` | 券商拒绝，查看 `message`，不要视作成功 |
| `accepted:null` 或字段缺失 | 结果未知，先查询核对，不直接重复发送 |
| 交易调用抛错、超时或断线 | 也可能已经发送并被受理，先核对状态，不直接重发 |

操作后按需查询：

```powershell
& $demo @demoArgs query --category 2
& $demo @demoArgs query --category 3
& $demo @demoArgs query --category 4
```

委托结果结合当日委托与当日成交核对。撤单结果要结合原合同号的最终委托状态核对，不能只凭可撤单列表中目标消失认定已撤，订单也可能已经成交。

## 5. 集成到自己的代码

各封装的撤单参数顺序有区别，推荐 Python 使用关键字传参：

| 语言 | 核心委托调用 | 核心撤单调用 |
| --- | --- | --- |
| Python | `api.order(category, shareholder, code, price, quantity)` | `api.cancel(order_id=orderId, exchange=exchangeId)` |
| C++ | `api.order(category, shareholder, code, price, quantity)` | `api.cancel(exchangeId, orderId)` |
| C# | `api.Order(category, shareholder, code, price, quantity)` | `api.Cancel(exchangeId, orderId)` |

三种语言的 README 都新增了委托／撤单的核心代码片段：

- [Python 调用代码](../examples/python/README.md#委托与撤单调用代码)
- [C++ 调用代码](../examples/cpp/README.md#委托与撤单调用代码)
- [C# 调用代码](../examples/csharp/README.md#委托与撤单调用代码)

片段复用各示例中的 API 封装和已成功登录的会话，不能与现有 CLI 交易分支重复执行。封装方法本身直接发送；人工确认只是一种示例防误操作措施，自己的程序还需实现权限、参数、风控与结果核对。
