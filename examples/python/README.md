# Python 示例

要求 Windows、Python 3.9+ **32 位**。只使用标准库，不需要 pip 安装包。`py -3-32` 是 Windows Python Launcher 的选择方式；如果没有 launcher，使用实际的 32 位 `python.exe` 绝对路径。

从仓库根目录运行：

```powershell
py -3-32 -c "import struct; print(struct.calcsize('P') * 8)"
py -3-32 examples/python/demo.py --config config/account.local.json
py -3-32 examples/python/demo.py --config config/account.local.json query --category 1
py -3-32 examples/python/demo.py --config config/account.local.json shareholders
py -3-32 examples/python/demo.py --help
```

首次输出应为 32。配置与密码输入方式见 [快速开始](../../docs/quick-start.md)。

交易命令模板（所有尖括号值必须手动替换，不能原样执行）：

```text
py -3-32 examples/python/demo.py --config config/account.local.json order --category 0 --shareholder <股东代码> --code <证券代码> --price <价格> --quantity <数量>
py -3-32 examples/python/demo.py --config config/account.local.json cancel --exchange <交易所代码> --order-id <合同号>
```

买入／卖出／融资买入分别为类别 0／1／2。程序必须收到人工输入的 `SEND ORDER` 或 `CANCEL ORDER` 才继续；未确认前不登录、不发送交易。没有自动重试。

`tradeapi.py` 是可阅读的薄封装。集成到自身程序时，可在一个 `with TradeApi(config) as api` 会话内先登录，再串行调用各查询方法，结束自动 Logoff／CloseTdx。`order` 与 `cancel` 封装方法本身直接发送，**人工确认属于 demo.py，业务集成需要自行设置风控**。

## 委托与撤单调用代码

命令行的完整买入／卖出／融资买入与撤单步骤见 [交易示例](../../docs/trading-examples.md)。以下是集成时的核心片段，不是额外自动执行的脚本。假定 `api` 已在 `with TradeApi(config)` 中成功登录；`shareholder`、`code`、`price`、`quantity` 是你已核对的实际参数。**一次只执行一个片段，不要叠加到现有 CLI 交易分支后再次发送。**

委托（内部调用 `SendOrder`，固定 `PriceType=0`）：

```python
# category: 0 买入，1 卖出，2 融资买入；只选择其中一种。
category = 0
print(f"category={category}, shareholder={shareholder}, code={code}, price={price}, quantity={quantity}")
if input("核对账户及全部参数；输入 SEND ORDER 才发送: ") == "SEND ORDER":
    try:
        result = api.order(category, shareholder, code, float(price), int(quantity))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(action_summary(result))
    except Exception:
        print("调用失败，交易结果可能未知；查询委托和成交核对，不自动重发。")
        raise
```

撤单（内部调用 `CancelOrder`）：

```python
# 先调用 api.query(4)，从核对后的目标行读取参数，不自动选第一笔。
# 此片段要求目标字段为非空字符串；旧版数字合同号需先无损转换。
order_id = target["order_id"]
exchange_id = target["exchange_code"]
if not isinstance(order_id, str) or not order_id or not isinstance(exchange_id, str) or not exchange_id:
    raise ValueError("目标合同号和交易所代码必须是非空字符串")
print(f"requested_order_id={order_id}, requested_exchange_id={exchange_id}")
if input("核对目标委托；输入 CANCEL ORDER 才撤单: ") == "CANCEL ORDER":
    try:
        result = api.cancel(order_id=order_id, exchange=exchange_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(action_summary(result, cancel=True))
    except Exception:
        print("撤单结果可能未知；查询原合同号状态核对，不自动重发。")
        raise
```

片段需 `import json` 及 `from tradeapi import action_summary`。`target` 必须是当前账户查询返回、人工或业务规则唯一选定的目标行，且其合同号与交易所代码非空；不要把缺失值／`None` 转成字符串发送。Python 的撤单封装参数顺序为 **order_id 在前、exchange 在后**，上面用关键字传参避免混淆。

封装检查 `ErrInfo` 并抛错，返回字典时仍要判断 `accepted`：`True` 是受理、`False` 是拒绝、`None` 或缺失是未知。无论委托还是撤单，都需按原合同号继续核对最终状态；结果字段不能用普通真假判断代替三态处理。
