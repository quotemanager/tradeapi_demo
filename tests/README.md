# 测试

全部测试使用虚构账户与返回数据，不需要真实账户，不连接券商。

## 纯解析测试

仓库根目录执行：

```powershell
python -m unittest discover -s tests -v
```

可在 64 位 Python 或非 Windows 环境运行；该步骤不加载实际 DLL。

## Windows x86 模拟集成测试

先按各语言 README 构建示例，再构建本目录的模拟 DLL：

```powershell
cmake -S tests/mock -B build/mock -G "Visual Studio 17 2022" -A Win32
cmake --build build/mock --config Release
py -3-32 tests/integration.py --runtime build/mock/Release --cpp build/cpp/Release/tradeapi_demo.exe --csharp build/csharp/TradeApiDemo.exe
```

不传 `--cpp`／`--csharp` 时只测试 Python。**runtime 必须是 tests/mock 构建目录，绝不能传真实发布包。** 模拟 DLL 不包含任何网络调用，并返回 ClientID 37 以检测把 1 写死的错误。

覆盖：全部查询类别、股东、买卖与融资买入、float32／short ABI、撤单合同号、受理／拒绝／未知结果、不自动重发、人工拒绝后零调用、资源清理。所有交易动作只是模拟记录，不发生真实委托或撤单。Windows CI 会编译并检查三种语言；GitHub Actions 尚未运行前，不应把工作流定义当成测试通过证明。
