# 环境准备与首次调用

## 准备运行包

通过 [首页购买与接入咨询](../README.md#购买与接入咨询) 获取适用的 tradeapi 发布包和接入配置，解压到例如 `C:\TradeApi`。保留完整目录及提供的文件，不将其提交到示例仓库。

本项目不模拟实际授权、不修改运行包配置，不要求调用方理解内部认证流程。按运行包提供方的接入要求准备即可。

## 配置

在仓库根目录运行：

```powershell
Copy-Item config/account.example.json config/account.local.json
```

编辑本地配置：

| 字段 | 含义 |
| --- | --- |
| `runtime_dir` | 完整发布目录的绝对路径，其中包含 `tradeApi.dll` |
| `broker_code` | 接入配置中的券商及账户类型标识；模板是不可直接使用的占位符 |
| `account_no` | 登录账号字符串，保留前导零 |
| `trade_account` | 交易账号，与登录账号相同时可留空 |
| `host` / `port` | 交易地址／端口，默认空字符串／0，使用运行包支持的自动选择 |
| `version` | 默认空字符串，使用运行包提供的配置 |
| `yyb_id` | 营业部标识，无特别要求填 0 |

不要增加明文密码字段。启动时会隐藏输入交易密码；需要通讯密码时可设置 `TRADEAPI_TX_PASSWORD`，不使用则留空。交易密码也可由 `TRADEAPI_PASSWORD` 环境变量提供；示例不会打印密码。示例输入参数为 ASCII 窄字符串；若账户要求其他编码，请按实际接入要求调整封装。

## 第一次运行

按 [Python](../examples/python/README.md)、[C++](../examples/cpp/README.md) 或 [C#](../examples/csharp/README.md) 的说明配置 **x86** 环境。下面是 Python 的默认只读调用：

```powershell
py -3-32 examples/python/demo.py --config config/account.local.json
```

默认执行初始化、登录、资金查询、退出。JSON 输出在标准输出，诊断提示在标准错误；请不要把完整输出贴到公开 Issue。程序退出码 0 表示本次演示流程完成，不保证委托受理或最终交易成功；非 0 表示异常、拒绝确认或参数错误。交易业务状态以返回 JSON 及后续查询为准。

各命令支持 `--help`。只读查询示例：

```powershell
py -3-32 examples/python/demo.py --config config/account.local.json query --category 1
py -3-32 examples/python/demo.py --config config/account.local.json query --category 4
py -3-32 examples/python/demo.py --config config/account.local.json shareholders
```

每次命令启动会重新登录；这些是简洁的教学示例，不是高频调用服务。实际集成应在自身程序内复用登录会话、串行调用同一 ClientID，并在退出时释放资源。重新登录必须更新 ClientID。

## 交易前检查

买入、卖出、融资买入、撤单的完整操作步骤和各语言代码入口，见 [委托与撤单调用示例](trading-examples.md)。首次接入建议先完成只读查询，再单独选择交易操作。

先查询股东代码，按交易市场选择对应账户，不能随意取第一项。先核对股票代码、价格、数量与权限，再主动执行 `order` 命令。融资买入使用类别 2，不等于普通买入。

撤单前查询类别 4，从目标行取得 `order_id` 与 `exchange_code`。撤单返回的 `order_id` 可能是撤单受理编号；原合同号以调用参数或 `requested_order_id` 为准。最终是否撤销应查询当日委托，不能仅凭可撤单列表中目标消失判断。

所有示例均要求最终人工确认，不支持 `--yes`。**非交易时间也不能假定请求绝不会生效。**
