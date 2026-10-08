"""Offline checks for the public repository's docs/config boundary."""
import json
import contextlib
import io
import os
from pathlib import Path
import re
import subprocess
import struct
import unittest
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class RepositoryTests(unittest.TestCase):
    def test_homepage_covers_all_interfaces_and_query_categories(self):
        source = (ROOT / 'README.md').read_text(encoding='utf-8')
        for name in ('OpenTdx', 'Logon', 'QueryData', 'QueryShareholderCodes',
                     'SendOrder', 'CancelOrder', 'Logoff', 'CloseTdx'):
            self.assertIn(f'| `{name}` |', source)
        for category in range(7):
            self.assertIn(f'query --category {category}', source)
        for heading in ('初始化、登录与退出', '数据查询', '股东代码查询', '委托示例', '撤单示例'):
            self.assertIn('## ' + heading, source)
        for snippet in re.findall(r'```json\n(.*?)\n```', source, re.DOTALL):
            self.assertIsInstance(json.loads(snippet), dict)

    def test_homepage_login_and_readonly_example_cleans_up_on_success_and_error(self):
        import sys
        sys.path.insert(0, str(ROOT / 'examples/python'))
        import tradeapi
        source = (ROOT / 'README.md').read_text(encoding='utf-8')
        snippets = re.findall(r'```python\n(.*?)\n```', source, re.DOTALL)
        self.assertEqual(len(snippets), 1)
        compiled = compile(snippets[0], 'README lifecycle example', 'exec')
        for query_fails in (False, True):
            with self.subTest(query_fails=query_fails):
                session = MagicMock()
                api = session.__enter__.return_value
                api.login.return_value = 37
                api.query.return_value = {'schema': 'tradeapi.funds.v1'}
                api.shareholders.return_value = {'shareholders': []}
                if query_fails:
                    api.query.side_effect = RuntimeError('synthetic query error')
                with patch.object(tradeapi, 'TradeApi', return_value=session), \
                     patch.object(tradeapi, 'load_config', return_value={'broker_code': 'MOCK:normal'}), \
                     patch.dict(os.environ, {'TRADEAPI_PASSWORD': 'TEST_PASSWORD', 'TRADEAPI_TX_PASSWORD': ''}), \
                     patch.object(sys, 'path', sys.path.copy()), contextlib.redirect_stdout(io.StringIO()):
                    if query_fails:
                        with self.assertRaisesRegex(RuntimeError, 'synthetic query error'):
                            exec(compiled, {})
                    else:
                        exec(compiled, {})
                session.__enter__.assert_called_once()
                session.__exit__.assert_called_once()
                api.login.assert_called_once_with('TEST_PASSWORD', '')
                api.query.assert_called_once_with(0)
                if query_fails:
                    api.shareholders.assert_not_called()
                else:
                    api.shareholders.assert_called_once_with()
                api.order.assert_not_called()
                api.cancel.assert_not_called()

    def test_documented_python_actions_confirm_and_send_once(self):
        import sys
        sys.path.insert(0, str(ROOT / 'examples/python'))
        from tradeapi import action_summary
        source = (ROOT / 'examples/python/README.md').read_text(encoding='utf-8')
        snippets = re.findall(r'```python\n(.*?)\n```', source, re.DOTALL)
        self.assertEqual(len(snippets), 2)
        for index, (method, token) in enumerate((('order', 'SEND ORDER'), ('cancel', 'CANCEL ORDER'))):
            compiled = compile(snippets[index], 'README example', 'exec')
            for answer in ('NO', token):
                for accepted in (True, False, None):
                    api = Mock()
                    getattr(api, method).return_value = {'accepted': accepted, 'order_id': '123456'}
                    variables = dict(api=api, json=json, action_summary=action_summary,
                        shareholder='S000000001', code='600000', price='19.25', quantity='100',
                        target={'order_id': '123456', 'exchange_code': '1'})
                    with patch('builtins.input', return_value=answer), contextlib.redirect_stdout(io.StringIO()):
                        exec(compiled, variables)
                    if answer == token:
                        if method == 'order':
                            api.order.assert_called_once_with(0, 'S000000001', '600000', 19.25, 100)
                        else:
                            api.cancel.assert_called_once_with(order_id='123456', exchange='1')
                    else:
                        getattr(api, method).assert_not_called()

    def test_documented_cancel_rejects_missing_target_fields(self):
        source = (ROOT / 'examples/python/README.md').read_text(encoding='utf-8')
        snippet = re.findall(r'```python\n(.*?)\n```', source, re.DOTALL)[1]
        for target in ({}, {'order_id': None, 'exchange_code': '1'},
                       {'order_id': '123456', 'exchange_code': ''}):
            api = Mock()
            with self.assertRaises((KeyError, ValueError)):
                exec(compile(snippet, 'README cancel example', 'exec'), {'api': api, 'target': target})
            api.cancel.assert_not_called()

    def test_local_document_links_and_qr_exist(self):
        documents = [ROOT / 'README.md', ROOT / 'SECURITY.md',
                     *(ROOT / 'docs').glob('*.md'), *(ROOT / 'examples').glob('*/README.md'), ROOT / 'tests/README.md']
        for path in documents:
            source = path.read_text(encoding='utf-8')
            targets = re.findall(r'\]\(([^)]+)\)', source) + re.findall(r'<img\s+src="([^"]+)"', source)
            for target in targets:
                if '://' in target or target.startswith('#'):
                    continue
                destination = (path.parent / target.split('#')[0]).resolve()
                self.assertTrue(destination.is_relative_to(ROOT), (path, target))
                self.assertTrue(destination.exists(), (path, target))
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertNotIn('微信', readme)
        self.assertNotIn('wechat', readme.lower())
        self.assertIn('assets/telegram-qr.png', readme)
        self.assertIn('https://t.me/tradeapi8', readme)
        self.assertLess(readme.index('## 购买与接入咨询'), readme.index('## 快速开始'))

    def test_contact_qr_images_are_square(self):
        for name in ('wechat-qr.png', 'telegram-qr.png'):
            header = (ROOT / 'assets' / name).read_bytes()[:24]
            self.assertEqual(header[:8], b'\x89PNG\r\n\x1a\n')
            width, height = struct.unpack('>II', header[16:24])
            self.assertEqual(width, height, name)
            self.assertGreaterEqual(width, 280, name)

    def test_public_config_has_no_credentials(self):
        config = json.loads((ROOT / 'config/account.example.json').read_text(encoding='utf-8'))
        self.assertEqual(config['account_no'], 'YOUR_ACCOUNT')
        self.assertTrue(config['broker_code'].startswith('BROKER_'))
        self.assertFalse(any('password' in key or 'secret' in key for key in config))

    def test_sensitive_and_build_paths_are_ignored(self):
        paths = ['config/account.local.json', 'account-auth.json', 'runtime/anything.txt',
                 'captures/raw.txt', 'logs/session.txt', 'secret.pfx', 'session.dpapi',
                 'trade-api-session-metadata.jsonl', 'build/mock/tradeApi.dll',
                 'examples/csharp/bin/test.txt', 'examples/python/__pycache__/test.pyc']
        for path in paths:
            result = subprocess.run(['git', 'check-ignore', '--no-index', '-q', path], cwd=ROOT)
            self.assertEqual(result.returncode, 0, path)
        for path in ['config/account.example.json', 'assets/wechat.png', 'assets/telegram.jpg',
                     'assets/wechat-qr.png', 'assets/telegram-qr.png', 'tests/fixtures/responses.json']:
            result = subprocess.run(['git', 'check-ignore', '--no-index', '-q', path], cwd=ROOT)
            self.assertEqual(result.returncode, 1, path)


if __name__ == '__main__':
    unittest.main()
