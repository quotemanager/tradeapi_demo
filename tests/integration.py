"""Run ONLY with the mock DLL built from tests/mock, never a live release."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, help='Directory of TEST mock DLL')
    parser.add_argument('--python', default=sys.executable, help='Windows x86 Python')
    parser.add_argument('--cpp')
    parser.add_argument('--csharp')
    args = parser.parse_args()
    runtime = Path(args.runtime).resolve(strict=True)
    if not (runtime / 'tradeApi.dll').is_file():
        parser.error('Build tests/mock first')
    # Never accept a real package as mock runtime: it contains a worker executable.
    if (runtime / 'tradeApiWorker.exe').exists() or (runtime / '_internal').exists():
        parser.error('Refusing a production runtime directory')
    if os.name != 'nt' or ctypes.sizeof(ctypes.c_void_p) != 4:
        parser.error('Run mock integration tests with Windows x86 Python')
    # Require a dedicated export available only in our test DLL before any login.
    mock = ctypes.WinDLL(str(runtime / 'tradeApi.dll'), winmode=0x100 | 0x1000)
    marker = mock.TradeApiDemoMockMarker
    marker.argtypes, marker.restype = [], ctypes.c_char_p
    if marker() != b'TRADEAPI_DEMO_MOCK_ONLY_V1':
        parser.error('Not the tests/mock DLL; refusing to run')
    clients = {'python': [args.python, str(ROOT / 'examples/python/demo.py')]}
    if args.cpp:
        clients['cpp'] = [str(Path(args.cpp).resolve(strict=True))]
    if args.csharp:
        clients['csharp'] = [str(Path(args.csharp).resolve(strict=True))]
    checks = 0
    with tempfile.TemporaryDirectory(prefix='tradeapi-demo-test-') as directory:
        config = Path(directory) / 'synthetic.json'
        config.write_text(json.dumps({'runtime_dir': str(runtime), 'broker_code': 'MOCK:normal',
                                     'account_no': '00000001'}), encoding='utf-8')
        audit = Path(directory) / 'audit.txt'
        env = {**os.environ, 'TRADEAPI_PASSWORD': 'TEST_PASSWORD', 'TRADEAPI_TX_PASSWORD': '',
               'TRADEAPI_MOCK_AUDIT': str(audit)}
        for name, command in clients.items():
            def run(arguments, token='', expected=0, extra_env=None):
                nonlocal checks
                audit.write_text('', encoding='ascii')
                result = subprocess.run([*command, '--config', str(config), *arguments],
                    input=token, text=True, encoding='utf-8', capture_output=True,
                    env={**env, **(extra_env or {})}, timeout=30)
                assert result.returncode == expected, (name, arguments, result.returncode, result.stderr)
                assert 'TEST_PASSWORD' not in result.stdout + result.stderr
                events = audit.read_text(encoding='ascii').splitlines()
                if expected == 0:
                    assert events[:2] == ['open', 'login'], (name, events)
                    assert events[-2:] == ['logoff', 'close'], (name, events)
                    assert events.count('login') == 1
                checks += 1
                return result, events

            result, events = run([])
            assert json.loads(result.stdout)['schema'] == 'tradeapi.funds.v1'
            for category in range(7):
                result, events = run(['query', '--category', str(category)])
                assert json.loads(result.stdout)['category'] == category
                assert events.count('query') == 1
            result, _ = run(['shareholders'])
            assert json.loads(result.stdout)['shareholders'][0]['shareholder_code'] == 'S000000001'
            result, events = run(['query'], expected=1, extra_env={'TRADEAPI_MOCK_QUERY_ERROR': '1'})
            assert '查询失败' in result.stderr
            assert not result.stdout.strip(), (name, 'used stale output after ErrInfo')
            assert events == ['open', 'login', 'query', 'logoff', 'close']
            result, events = run([], expected=1, extra_env={'TRADEAPI_PASSWORD': 'BAD_TEST_PASSWORD'})
            assert events == ['open', 'login', 'close']
            assert not result.stdout.strip()
            order = ['order', '--category', '0', '--shareholder', 'S000000001', '--code', '600000', '--price', '19.25', '--quantity', '100']
            result, events = run(order, 'NO\n', expected=2)
            assert events == [], (name, 'declined action loaded runtime', events)
            for side in range(3):
                modified = order.copy(); modified[2] = str(side)
                result, events = run(modified, 'SEND ORDER\n')
                assert json.loads(result.stdout)['accepted'] is True
                assert events.count('order') == 1
            for quantity, accepted in (('1', False), ('101', None)):
                result, events = run(order[:-1] + [quantity], 'SEND ORDER\n')
                assert json.loads(result.stdout)['accepted'] is accepted
                assert events.count('order') == 1
                assert ('UNKNOWN' if accepted is None else 'reject') in result.stderr
            modified = order.copy(); modified[8] = '20.25'
            result, events = run(modified, 'SEND ORDER\n', expected=1)
            assert events == ['open', 'login', 'order', 'logoff', 'close']
            assert not result.stdout.strip()
            cancel = ['cancel', '--exchange', '1', '--order-id', '123456']
            _, events = run(cancel, '\n', expected=2)
            assert events == []
            for arguments in (cancel, ['cancel', '--order-id', '123456']):
                result, events = run(arguments, 'CANCEL ORDER\n')
                value = json.loads(result.stdout)
                assert value['requested_order_id'] == '123456'
                assert value['order_id'] == '789'
                assert events.count('cancel') == 1
            print(f'PASS: {name} mock ABI, queries, one-shot actions, no retry, confirmation and cleanup')
    print(f'{checks} mock integration checks passed; NO brokerage network requests.')


if __name__ == '__main__':
    main()
