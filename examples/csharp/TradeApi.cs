using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

namespace TradeApiDemo;

internal sealed record AccountConfig(string RuntimeDir, string BrokerCode, string AccountNo,
    string TradeAccount, string Host, int Port, string Version, short YybId)
{
    public static void Ascii(string value)
    {
        if (value.Any(c => c == '\0' || c > 127))
            throw new ArgumentException("Expected ASCII without NUL characters");
    }

    public static AccountConfig Load(string path)
    {
        JsonDocument document;
        try { document = JsonDocument.Parse(File.ReadAllText(path, Encoding.UTF8)); }
        catch (JsonException) { throw new ArgumentException("Invalid configuration JSON"); }
        using (document)
        {
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object) throw new ArgumentException("Configuration must be an object");
            string[] allowed = ["runtime_dir", "broker_code", "account_no", "trade_account", "host", "port", "version", "yyb_id"];
            foreach (var field in root.EnumerateObject())
                if (!allowed.Contains(field.Name)) throw new ArgumentException("Unknown configuration field; do not store passwords in JSON");
            string Text(string name, bool required = false)
            {
                string? value = root.TryGetProperty(name, out var item) ? item.GetString() : "";
                if (value is null || (required && string.IsNullOrWhiteSpace(value)))
                    throw new ArgumentException("Missing configuration string: " + name);
                return value;
            }
            int Number(string name, int maximum)
            {
                int value = root.TryGetProperty(name, out var item) ? item.GetInt32() : 0;
                if (value < 0 || value > maximum) throw new ArgumentException("Configuration integer out of range");
                return value;
            }
            var config = new AccountConfig(Text("runtime_dir", true), Text("broker_code", true), Text("account_no", true),
                Text("trade_account"), Text("host"), Number("port", 65535), Text("version"), (short)Number("yyb_id", 32767));
            if (!Path.IsPathFullyQualified(config.RuntimeDir)) throw new ArgumentException("runtime_dir must be absolute");
            if (config.BrokerCode.StartsWith("BROKER_", StringComparison.Ordinal) || config.AccountNo == "YOUR_ACCOUNT")
                throw new ArgumentException("Replace example broker/account placeholders");
            foreach (string text in new[] { config.BrokerCode, config.AccountNo, config.TradeAccount, config.Host, config.Version }) Ascii(text);
            return config;
        }
    }
}

internal sealed class TradeApi : IDisposable
{
    private const int ResultBytes = 1048577, ErrorBytes = 256;
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void VoidFn();
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Ansi)]
    private delegate int LogonFn(string broker, string host, short port, string version, short yyb,
        string account, string tradeAccount, string password, string txPassword, IntPtr error);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void LogoffFn(int client);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void QueryFn(int client, int category, IntPtr result, IntPtr error);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void ShareFn(int client, IntPtr result, IntPtr error);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Ansi)]
    private delegate void OrderFn(int client, int category, int priceType, string shareholder, string code,
        float price, int quantity, IntPtr result, IntPtr error);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Ansi)]
    private delegate void CancelFn(int client, string exchange, string orderId, IntPtr result, IntPtr error);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryExW(string path, IntPtr file, uint flags);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool FreeLibrary(IntPtr module);

    private IntPtr library;
    private int client = -1;
    private bool opened;
    private readonly VoidFn close;
    private readonly LogonFn logon;
    private readonly LogoffFn logoff;
    private readonly QueryFn query;
    private readonly ShareFn shareholders;
    private readonly OrderFn order;
    private readonly CancelFn cancel;
    private static readonly Encoding ErrorEncoding = CreateErrorEncoding();
    private static Encoding CreateErrorEncoding()
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        return Encoding.GetEncoding("GB18030");
    }

    public TradeApi(AccountConfig config)
    {
        if (!OperatingSystem.IsWindows() || IntPtr.Size != 4)
            throw new PlatformNotSupportedException("Windows x86 process required");
        string path = Path.Combine(config.RuntimeDir, "tradeApi.dll");
        if (!File.Exists(path)) throw new FileNotFoundException("tradeApi.dll is missing from runtime_dir");
        library = LoadLibraryExW(path, IntPtr.Zero, 0x100 | 0x1000);
        if (library == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "Cannot load tradeApi.dll");
        try
        {
            T Export<T>(string name) where T : Delegate => Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(library, name));
            var open = Export<VoidFn>("OpenTdx"); close = Export<VoidFn>("CloseTdx");
            logon = Export<LogonFn>("Logon"); logoff = Export<LogoffFn>("Logoff");
            query = Export<QueryFn>("QueryData"); shareholders = Export<ShareFn>("QueryShareholderCodes");
            order = Export<OrderFn>("SendOrder"); cancel = Export<CancelFn>("CancelOrder");
            open(); opened = true;
        }
        catch { FreeLibrary(library); library = IntPtr.Zero; throw; }
    }

    private sealed class Buffer : IDisposable
    {
        public IntPtr Pointer { get; private set; }
        private readonly int length;
        public Buffer(int size)
        {
            length = size; Pointer = Marshal.AllocHGlobal(size);
            Marshal.Copy(new byte[size], 0, Pointer, size);
        }
        public byte[] Bytes()
        {
            var bytes = new byte[length]; Marshal.Copy(Pointer, bytes, 0, length);
            int end = Array.IndexOf(bytes, (byte)0);
            if (end < 0) throw new InvalidDataException("Output buffer has no NUL terminator");
            return bytes[..end];
        }
        public void Dispose() { if (Pointer != IntPtr.Zero) Marshal.FreeHGlobal(Pointer); Pointer = IntPtr.Zero; }
    }

    public void Login(AccountConfig config, string password, string txPassword)
    {
        if (!opened || client > 0 || password.Length == 0) throw new InvalidOperationException("Initialize, then login once with nonempty password");
        AccountConfig.Ascii(password); AccountConfig.Ascii(txPassword);
        using var error = new Buffer(ErrorBytes);
        int value = logon(config.BrokerCode, config.Host, unchecked((short)config.Port), config.Version, config.YybId,
            config.AccountNo, config.TradeAccount, password, txPassword, error.Pointer);
        if (value <= 0) throw new InvalidOperationException(ErrorEncoding.GetString(error.Bytes()) is { Length: > 0 } message ? message : "Logon failed");
        client = value;
    }

    private JsonElement Result(Action<IntPtr, IntPtr> call)
    {
        if (client <= 0) throw new InvalidOperationException("Login first");
        using var result = new Buffer(ResultBytes); using var error = new Buffer(ErrorBytes);
        call(result.Pointer, error.Pointer);
        byte[] errorBytes = error.Bytes();
        if (errorBytes.Length != 0) throw new InvalidOperationException(ErrorEncoding.GetString(errorBytes));
        using var document = JsonDocument.Parse(result.Bytes());
        if (document.RootElement.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Expected a JSON object");
        return document.RootElement.Clone();
    }
    public JsonElement Query(int category)
    {
        if (category is < 0 or > 6) throw new ArgumentOutOfRangeException(nameof(category));
        return Result((r, e) => query(client, category, r, e));
    }
    public JsonElement Shareholders() => Result((r, e) => shareholders(client, r, e));
    // These methods send directly; human confirmation is implemented in Program.cs.
    public JsonElement Order(int category, string shareholder, string code, float price, int quantity)
    {
        AccountConfig.Ascii(shareholder); AccountConfig.Ascii(code);
        if (category is < 0 or > 2 || shareholder.Length == 0 || code.Length != 6 ||
            code.Any(c => c < '0' || c > '9') || !float.IsFinite(price) || price <= 0 || quantity <= 0)
            throw new ArgumentException("Invalid order parameters");
        return Result((r, e) => order(client, category, 0, shareholder, code, price, quantity, r, e));
    }
    public JsonElement Cancel(string exchange, string orderId)
    {
        AccountConfig.Ascii(exchange); AccountConfig.Ascii(orderId);
        if (orderId.Length == 0) throw new ArgumentException("OrderID is required");
        return Result((r, e) => cancel(client, exchange, orderId, r, e));
    }
    public void Dispose()
    {
        if (library == IntPtr.Zero) return;
        try { if (client > 0) logoff(client); }
        finally
        {
            client = -1;
            try { if (opened) close(); }
            finally { opened = false; FreeLibrary(library); library = IntPtr.Zero; }
        }
    }
}
