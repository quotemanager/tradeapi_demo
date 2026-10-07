import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'examples' / 'python'))
import tradeapi


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = json.loads((ROOT / 'tests/fixtures/responses.json').read_text(encoding='utf-8'))

    def test_all_examples_parse(self):
        for value in self.fixtures.values():
            self.assertEqual(tradeapi.decode_result(json.dumps(value).encode(), b''), value)

    def test_error_wins_over_stale_result(self):
        with self.assertRaisesRegex(RuntimeError, '查询失败'):
            tradeapi.decode_result(b'{"available":"999"}', '查询失败'.encode('gb18030'))

    def test_empty_and_invalid_result_fail(self):
        for value in (b'', b'not json', b'[]', b'null'):
            with self.assertRaises((ValueError, UnicodeError)):
                tradeapi.decode_result(value, b'')

    def test_accepted_false_and_unknown_are_distinct(self):
        self.assertIn('NOT execution', tradeapi.action_summary(self.fixtures['order_accepted']))
        self.assertIn('rejected', tradeapi.action_summary(self.fixtures['order_rejected']))
        for name in ('order_unknown', 'order_missing'):
            self.assertIn('UNKNOWN', tradeapi.action_summary(self.fixtures[name]))
        for invalid in (1, 0, 'true', 'false'):
            self.assertIn('UNKNOWN', tradeapi.action_summary({'accepted': invalid}))

    def test_cancel_acceptance_is_not_final_state(self):
        self.assertIn('query final order status', tradeapi.action_summary(self.fixtures['cancel_accepted'], cancel=True))

    def test_ascii_preserves_leading_zero_and_rejects_nul(self):
        self.assertEqual(tradeapi.ascii_bytes('000123'), b'000123')
        for value in ('abc\0def', '中文', 123):
            with self.assertRaises((ValueError, UnicodeError)):
                tradeapi.ascii_bytes(value)

    def test_placeholder_config_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'placeholders'):
            tradeapi.load_config(ROOT / 'config/account.example.json')

    def test_config_validation(self):
        # No real account or password; runtime is just the current temporary directory.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'
            config = {'runtime_dir': directory, 'broker_code': 'MOCK:normal', 'account_no': '00000001'}
            path.write_text(json.dumps(config), encoding='utf-8')
            self.assertEqual(tradeapi.load_config(path)['account_no'], '00000001')
            for key, value in (('port', True), ('port', 65536), ('yyb_id', -1),
                               ('password', 'NOT_A_REAL_PASSWORD'), ('account_no', 123), ('runtime_dir', 'relative')):
                path.write_text(json.dumps({**config, key: value}), encoding='utf-8')
                with self.assertRaises((ValueError, UnicodeError)):
                    tradeapi.load_config(path)

    def test_default_cli_does_not_select_trading(self):
        import demo
        args = demo.parser().parse_args(['--config', 'local.json'])
        self.assertIsNone(args.operation)

    def test_cli_decline_never_constructs_api_or_prompts_password(self):
        import demo
        synthetic = {'broker_code': 'MOCK:normal', 'account_no': '00000001'}
        for command, args in (
            ('order', ['--category', '0', '--shareholder', 'S000000001', '--code', '600000', '--price', '19.25', '--quantity', '100']),
            ('cancel', ['--order-id', '123456'])
        ):
            with patch.object(sys, 'argv', ['demo', '--config', 'unused', command, *args]), \
                 patch.object(demo, 'load_config', return_value=synthetic), \
                 patch('builtins.input', return_value='NO'), patch.object(demo, 'TradeApi') as factory, \
                 patch.object(demo.getpass, 'getpass') as password:
                self.assertEqual(demo.main(), 2)
                factory.assert_not_called()
                password.assert_not_called()

    def test_non_x86_process_fails_before_loading(self):
        if os.name == 'nt' and ctypes.sizeof(ctypes.c_void_p) == 4:
            self.skipTest('Already a supported Windows x86 process')
        with self.assertRaisesRegex(RuntimeError, '32-bit'):
            tradeapi.TradeApi({})

    def test_help_does_not_load_runtime(self):
        result = subprocess.run([sys.executable, str(ROOT / 'examples/python/demo.py'), '--help'], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'--config', result.stdout)


if __name__ == '__main__':
    unittest.main()
