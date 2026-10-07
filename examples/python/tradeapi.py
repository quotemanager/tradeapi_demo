"""Public ABI wrapper; Windows x86 only. No network/protocol implementation."""
from __future__ import annotations

import ctypes
import json
import math
import os
from pathlib import Path
import struct
from typing import Any

RESULT_BYTES = 1048577
ERROR_BYTES = 256


def ascii_bytes(value: str) -> bytes:
    if not isinstance(value, str) or "\0" in value:
        raise ValueError("Expected a string without NUL characters")
    return value.encode("ascii", errors="strict")


def decode_result(raw: bytes, error: bytes) -> dict[str, Any]:
    if error:
        raise RuntimeError(error.decode("gb18030", errors="replace"))
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def action_summary(result: dict[str, Any], *, cancel: bool = False) -> str:
    accepted = result.get("accepted")
    if accepted is True:
        return ("Cancellation request accepted; query final order status." if cancel else
                "Order accepted; acceptance is NOT execution. Query order/trade status.")
    if accepted is False:
        return "Broker rejected the request. Check message; do not treat it as success."
    return "Outcome UNKNOWN. Reconcile order/trade status before any retry."


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8-sig") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    allowed = {"runtime_dir", "broker_code", "account_no", "trade_account", "host", "port", "version", "yyb_id"}
    if set(config) - allowed:
        raise ValueError("Unknown configuration fields; passwords must not be stored in JSON")
    for name in ("runtime_dir", "broker_code", "account_no"):
        if not isinstance(config.get(name), str) or not config[name].strip():
            raise ValueError(f"Missing {name}")
    if config["broker_code"].startswith("BROKER_") or config["account_no"] == "YOUR_ACCOUNT":
        raise ValueError("Replace the example broker/account placeholders")
    runtime = Path(config["runtime_dir"])
    if not runtime.is_absolute():
        raise ValueError("runtime_dir must be an absolute path")
    for name in ("broker_code", "account_no", "trade_account", "host", "version"):
        ascii_bytes(config.get(name, ""))
    for name, maximum in (("port", 65535), ("yyb_id", 32767)):
        value = config.get(name, 0)
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"Invalid {name}")
    return config


class TradeApi:
    """One owned login, serialized calls, fresh buffers, deterministic cleanup."""

    def __init__(self, config: dict[str, Any]):
        if os.name != "nt" or struct.calcsize("P") != 4:
            raise RuntimeError("Use Windows and a 32-bit (x86) Python interpreter")
        self.config = config
        self.client_id = -1
        self._opened = False
        runtime = Path(config["runtime_dir"]).resolve(strict=True)
        dll = runtime / "tradeApi.dll"
        if not dll.is_file():
            raise FileNotFoundError("tradeApi.dll is missing from runtime_dir")
        self._dll_directory = os.add_dll_directory(str(runtime))
        try:
            self.dll = ctypes.WinDLL(str(dll), winmode=0x100 | 0x1000)
            text, output = ctypes.c_char_p, ctypes.POINTER(ctypes.c_char)
            declarations = {
                "OpenTdx": (None, []), "CloseTdx": (None, []),
                "Logon": (ctypes.c_int, [text, text, ctypes.c_short, text, ctypes.c_short,
                                        text, text, text, text, output]),
                "Logoff": (None, [ctypes.c_int]),
                "QueryData": (None, [ctypes.c_int, ctypes.c_int, output, output]),
                "QueryShareholderCodes": (None, [ctypes.c_int, output, output]),
                "SendOrder": (None, [ctypes.c_int, ctypes.c_int, ctypes.c_int, text, text,
                                      ctypes.c_float, ctypes.c_int, output, output]),
                "CancelOrder": (None, [ctypes.c_int, text, text, output, output]),
            }
            for name, (result, args) in declarations.items():
                function = getattr(self.dll, name)
                function.restype, function.argtypes = result, args
        except BaseException:
            self._dll_directory.close()
            raise

    def __enter__(self):
        self.dll.OpenTdx()
        self._opened = True
        return self

    def login(self, password: str, tx_password: str = "") -> int:
        if not self._opened or self.client_id > 0:
            raise RuntimeError("Initialize once and login only once per demo instance")
        if not password:
            raise ValueError("Trading password is required")
        c = self.config
        error = ctypes.create_string_buffer(ERROR_BYTES)
        client = self.dll.Logon(ascii_bytes(c["broker_code"]), ascii_bytes(c.get("host", "")),
            ctypes.c_short(c.get("port", 0)), ascii_bytes(c.get("version", "")), c.get("yyb_id", 0),
            ascii_bytes(c["account_no"]), ascii_bytes(c.get("trade_account", "")),
            ascii_bytes(password), ascii_bytes(tx_password), error)
        if client <= 0:
            raise RuntimeError(error.value.decode("gb18030", errors="replace") or "Logon failed")
        self.client_id = client
        return client

    def _result(self, name: str, *args) -> dict[str, Any]:
        if self.client_id <= 0:
            raise RuntimeError("Login first")
        result, error = ctypes.create_string_buffer(RESULT_BYTES), ctypes.create_string_buffer(ERROR_BYTES)
        getattr(self.dll, name)(self.client_id, *args, result, error)
        return decode_result(result.value, error.value)

    def query(self, category: int = 0) -> dict[str, Any]:
        if type(category) is not int or not 0 <= category <= 6:
            raise ValueError("Query category must be 0..6")
        return self._result("QueryData", category)

    def shareholders(self) -> dict[str, Any]:
        return self._result("QueryShareholderCodes")

    def order(self, category: int, shareholder: str, code: str, price: float, quantity: int) -> dict[str, Any]:
        if type(category) is not int or category not in (0, 1, 2):
            raise ValueError("Order category must be 0, 1 or 2")
        if not shareholder or len(code) != 6 or not code.isascii() or not code.isdigit():
            raise ValueError("Shareholder and a six-digit security code are required")
        converted = ctypes.c_float(price).value
        if not math.isfinite(converted) or converted <= 0:
            raise ValueError("Price must be positive and representable as float32")
        if type(quantity) is not int or not 0 < quantity <= 2147483647:
            raise ValueError("Quantity must be a positive int32")
        return self._result("SendOrder", category, 0, ascii_bytes(shareholder), ascii_bytes(code),
                            ctypes.c_float(price), quantity)

    def cancel(self, order_id: str, exchange: str = "") -> dict[str, Any]:
        if not order_id:
            raise ValueError("OrderID is required")
        return self._result("CancelOrder", ascii_bytes(exchange), ascii_bytes(order_id))

    def __exit__(self, *_):
        try:
            if self.client_id > 0:
                self.dll.Logoff(self.client_id)
        finally:
            self.client_id = -1
            try:
                if self._opened:
                    self.dll.CloseTdx()
            finally:
                self._opened = False
                self._dll_directory.close()
