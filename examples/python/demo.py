"""Read-only by default; one explicitly confirmed trading action at most."""
import argparse
import getpass
import json
import os
import sys

from tradeapi import TradeApi, action_summary, load_config


def parser():
    result = argparse.ArgumentParser(description="tradeapi x86 demo; default operation: funds query")
    result.add_argument("--config", required=True)
    commands = result.add_subparsers(dest="operation")
    query = commands.add_parser("query")
    query.add_argument("--category", type=int, choices=range(7), default=0)
    commands.add_parser("shareholders")
    order = commands.add_parser("order", help="REAL order; confirmation required")
    order.add_argument("--category", type=int, choices=(0, 1, 2), required=True)
    order.add_argument("--shareholder", required=True)
    order.add_argument("--code", required=True)
    order.add_argument("--price", type=float, required=True)
    order.add_argument("--quantity", type=int, required=True)
    cancel = commands.add_parser("cancel", help="REAL cancellation; confirmation required")
    cancel.add_argument("--exchange", default="")
    cancel.add_argument("--order-id", required=True)
    return result


def main():
    # Windows redirected stdout/stderr otherwise may use the local ANSI code
    # page. Keep JSON and diagnostics consistently UTF-8, including pipes.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    try:
        config = load_config(args.config)
        if args.operation in ("order", "cancel"):
            print(f"Broker={config['broker_code']} Account=****{config['account_no'][-4:]}", file=sys.stderr)
            # Review only explicit operation parameters; never print passwords/account config.
            review = {k: v for k, v in vars(args).items() if k not in ("config",)}
            print("REAL trading action:", json.dumps(review, ensure_ascii=True), file=sys.stderr)
            token = "SEND ORDER" if args.operation == "order" else "CANCEL ORDER"
            print(f"Verify account in local config. Type {token} exactly; anything else aborts:", file=sys.stderr)
            if input() != token:
                print("Aborted; no login or action sent.", file=sys.stderr)
                return 2
        password = os.environ.get("TRADEAPI_PASSWORD")
        if password is None:
            password = getpass.getpass("Trading password: ")
        with TradeApi(config) as api:
            api.login(password, os.environ.get("TRADEAPI_TX_PASSWORD", ""))
            if args.operation == "shareholders":
                result = api.shareholders()
            elif args.operation == "order":
                result = api.order(args.category, args.shareholder, args.code, args.price, args.quantity)
            elif args.operation == "cancel":
                result = api.cancel(args.order_id, args.exchange)
            else:
                result = api.query(getattr(args, "category", 0))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if args.operation in ("order", "cancel"):
                print(action_summary(result, cancel=args.operation == "cancel"), file=sys.stderr)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        # No config or passwords are added to diagnostics.
        print(f"FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
