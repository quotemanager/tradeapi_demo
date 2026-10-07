/* TEST ONLY. No sockets, brokerage endpoints, credentials or real orders. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int opened = 0, logged_in = 0;
const char *__stdcall TradeApiDemoMockMarker(void) { return "TRADEAPI_DEMO_MOCK_ONLY_V1"; }
static void audit(const char *event) {
    const char *path = getenv("TRADEAPI_MOCK_AUDIT");
    FILE *file;
    if (!path || !*path) return;
    file = fopen(path, "ab");
    if (file) { fprintf(file, "%s\n", event); fclose(file); }
}
static int valid(int client, char *error) {
    if (!logged_in || client != 37) { strcpy(error, "Wrong ClientID; use actual Logon result"); return 0; }
    return 1;
}
void __stdcall OpenTdx(void) { opened = 1; audit("open"); }
void __stdcall CloseTdx(void) { opened = 0; logged_in = 0; audit("close"); }
int __stdcall Logon(const char *broker, const char *host, short port, const char *version, short yyb,
    const char *account, const char *trade_account, const char *password, const char *tx, char *error) {
    audit("login");
    if (!opened || strcmp(broker, "MOCK:normal") || strcmp(account, "00000001") ||
        strcmp(password, "TEST_PASSWORD") || strcmp(host, "") || port != 0 || strcmp(version, "") ||
        yyb != 0 || strcmp(trade_account, "") || strcmp(tx, "")) {
        strcpy(error, "Synthetic login parameter mismatch"); return -1;
    }
    logged_in = 1;
    return 37;
}
void __stdcall Logoff(int client) { (void)client; logged_in = 0; audit("logoff"); }
void __stdcall QueryData(int client, int category, char *result, char *error) {
    static const char *schemas[] = {"funds", "holdings", "orders", "trades", "cancelable_orders", "credit_summary", "eligible_securities"};
    static const char *data[] = {"\"balance\":\"10000.00\",\"available\":\"8000.00\"", "\"count\":0,\"positions\":[]",
        "\"count\":0,\"orders\":[]", "\"count\":0,\"trades\":[]", "\"count\":0,\"orders\":[]",
        "\"funds\":[],\"financing\":[],\"short_selling\":[]", "\"financing\":{\"count\":0,\"columns\":[],\"rows\":[]},\"short_selling\":{\"count\":0,\"columns\":[],\"rows\":[]}"};
    audit("query");
    if (!valid(client, error)) return;
    if (getenv("TRADEAPI_MOCK_QUERY_ERROR")) {
        strcpy(result, "{\"available\":\"999999\"}"); /* Stale-looking data must not be used. */
        strcpy(error, "\xB2\xE9\xD1\xAF\xCA\xA7\xB0\xDC"); /* GB18030: query failed */
        return;
    }
    if (category < 0 || category > 6) { strcpy(error, "Invalid query category"); return; }
    sprintf(result, "{\"schema\":\"tradeapi.%s.v1\",\"broker_code\":\"MOCK\",\"category\":%d,%s}", schemas[category], category, data[category]);
}
void __stdcall QueryShareholderCodes(int client, char *result, char *error) {
    audit("shareholders");
    if (!valid(client, error)) return;
    strcpy(result, "{\"schema\":\"tradeapi.shareholder_codes.v1\",\"count\":1,\"shareholders\":[{\"market\":\"SH\",\"shareholder_code\":\"S000000001\"}]}");
}
void __stdcall SendOrder(int client, int category, int price_type, const char *shareholder, const char *code,
    float price, int quantity, char *result, char *error) {
    audit("order");
    if (!valid(client, error)) return;
    if (category < 0 || category > 2 || price_type != 0 || strcmp(shareholder, "S000000001") || strcmp(code, "600000") || price != 19.25f) {
        strcpy(error, "Synthetic order ABI or parameter mismatch"); return;
    }
    if (quantity == 100) strcpy(result, "{\"schema\":\"tradeapi.order.v1\",\"accepted\":true,\"order_id\":\"123456\",\"message\":null}");
    else if (quantity == 101) strcpy(result, "{\"schema\":\"tradeapi.order.v1\",\"accepted\":null,\"order_id\":null}");
    else strcpy(result, "{\"schema\":\"tradeapi.order.v1\",\"accepted\":false,\"order_id\":\"-1\",\"message\":\"Synthetic broker rejection\"}");
}
void __stdcall CancelOrder(int client, const char *exchange, const char *id, char *result, char *error) {
    audit("cancel");
    if (!valid(client, error)) return;
    if (strcmp(id, "123456") || (strcmp(exchange, "1") && strcmp(exchange, ""))) { strcpy(error, "Synthetic cancel parameter mismatch"); return; }
    strcpy(result, "{\"schema\":\"tradeapi.cancel.v1\",\"accepted\":true,\"order_id\":\"789\",\"requested_order_id\":\"123456\",\"requested_exchange_id\":\"1\",\"cancellation_completed\":null}");
}
