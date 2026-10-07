using System.Globalization;
using System.Text;
using System.Text.Json;

namespace TradeApiDemo;

internal static class Program
{
    private static string Password()
    {
        string? value = Environment.GetEnvironmentVariable("TRADEAPI_PASSWORD");
        if (value is not null) return value;
        if (Console.IsInputRedirected) throw new InvalidOperationException("Use an interactive console or TRADEAPI_PASSWORD");
        Console.Error.Write("Trading password: ");
        var text = new StringBuilder();
        while (true)
        {
            var key = Console.ReadKey(intercept: true);
            if (key.Key == ConsoleKey.Enter) break;
            if (key.Key == ConsoleKey.Backspace) { if (text.Length > 0) text.Length--; }
            else if (!char.IsControl(key.KeyChar)) text.Append(key.KeyChar);
        }
        Console.Error.WriteLine();
        return text.ToString();
    }
    private static int Number(string text, int min, int max)
    {
        if (!int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out int value) || value < min || value > max)
            throw new ArgumentException("Integer parameter out of range");
        return value;
    }
    public static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        try
        {
            var options = new Dictionary<string, string>();
            string operation = "query";
            bool commandSeen = false;
            for (int i = 0; i < args.Length; i++)
            {
                string key = args[i];
                if (key == "--help")
                {
                    Console.WriteLine("--config FILE [query --category 0..6 | shareholders | order --category 0..2 --shareholder CODE --code CODE --price PRICE --quantity QTY | cancel --order-id ID [--exchange CODE]]");
                    return 0;
                }
                if (!key.StartsWith("--", StringComparison.Ordinal))
                {
                    if (commandSeen || key is not ("query" or "shareholders" or "order" or "cancel")) throw new ArgumentException("Unknown or duplicate command");
                    operation = key; commandSeen = true;
                }
                else
                {
                    if (++i >= args.Length || !options.TryAdd(key, args[i])) throw new ArgumentException("Missing or duplicate option");
                }
            }
            var allowed = new List<string> { "--config" };
            if (operation == "query") allowed.Add("--category");
            if (operation == "order") allowed.AddRange(["--category", "--shareholder", "--code", "--price", "--quantity"]);
            if (operation == "cancel") allowed.AddRange(["--exchange", "--order-id"]);
            if (options.Keys.Any(k => !allowed.Contains(k))) throw new ArgumentException("Unknown option for command");
            string Required(string key) => options.TryGetValue(key, out string? value) && value.Length > 0
                ? value : throw new ArgumentException("Required option: " + key);
            AccountConfig config = AccountConfig.Load(Required("--config"));
            int category = operation == "order" ? Number(Required("--category"), 0, 2) : Number(options.GetValueOrDefault("--category", "0"), 0, 6);
            float price = 0; int quantity = 0;
            string shareholder = "", code = "", exchange = "", orderId = "";
            if (operation == "order")
            {
                shareholder = Required("--shareholder"); code = Required("--code");
                if (!float.TryParse(Required("--price"), NumberStyles.Float, CultureInfo.InvariantCulture, out price) || !float.IsFinite(price) || price <= 0)
                    throw new ArgumentException("Invalid price");
                quantity = Number(Required("--quantity"), 1, int.MaxValue);
                Console.Error.WriteLine(FormattableString.Invariant($"REAL ORDER category={category} shareholder={shareholder} code={code} price={price} quantity={quantity}"));
            }
            if (operation == "cancel")
            {
                exchange = options.GetValueOrDefault("--exchange", ""); orderId = Required("--order-id");
                Console.Error.WriteLine($"REAL CANCEL order_id={orderId} exchange={exchange}");
            }
            if (operation is "order" or "cancel")
            {
                string maskedAccount = "****" + config.AccountNo[Math.Max(0, config.AccountNo.Length - 4)..];
                Console.Error.WriteLine($"Broker={config.BrokerCode} Account={maskedAccount}");
                string token = operation == "order" ? "SEND ORDER" : "CANCEL ORDER";
                Console.Error.WriteLine($"Verify account in local config. Type {token} exactly; anything else aborts:");
                if (Console.ReadLine() != token) { Console.Error.WriteLine("Aborted; no login or action sent."); return 2; }
            }
            using var api = new TradeApi(config);
            api.Login(config, Password(), Environment.GetEnvironmentVariable("TRADEAPI_TX_PASSWORD") ?? "");
            JsonElement result = operation switch
            {
                "order" => api.Order(category, shareholder, code, price, quantity),
                "cancel" => api.Cancel(exchange, orderId),
                "shareholders" => api.Shareholders(),
                _ => api.Query(category)
            };
            Console.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
            if (operation is "order" or "cancel")
            {
                string summary = !result.TryGetProperty("accepted", out var accepted) ? "Outcome UNKNOWN; reconcile before any retry." : accepted.ValueKind switch
                {
                    JsonValueKind.True => "Request accepted; NOT final execution/cancellation. Query final status.",
                    JsonValueKind.False => "Broker rejected request; check message.",
                    _ => "Outcome UNKNOWN; reconcile before any retry."
                };
                Console.Error.WriteLine(summary);
            }
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine("FAILED: " + error.Message); return 1; }
    }
}
