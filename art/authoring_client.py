"""Local PSD2Live authoring client. Never logs its locally generated editor credential."""
from __future__ import annotations
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('psd2live_proxy', ROOT/'tools/psd2live/mcp_proxy.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)

class Editor:
    def __init__(self):
        self.token = proxy.get_token()
        if not self.token:
            raise RuntimeError('Start the local PSD2Live editor first.')
        self.session = None
        self.counter = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.rpc('initialize', {'protocolVersion':'2025-03-26', 'capabilities':{},
                 'clientInfo':{'name':'Shuangli-authoring','version':'1.0'}})
        self.rpc('notifications/initialized', {}, notification=True)

    def rpc(self, method, params, notification=False):
        self.counter += 1
        body = {'jsonrpc':'2.0','method':method,'params':params}
        if not notification: body['id'] = self.counter
        headers = proxy._build_headers(self.token, self.session, '2025-03-26')
        req = urllib.request.Request(proxy.get_endpoint(), json.dumps(body).encode(), headers, method='POST')
        with self.opener.open(req, timeout=60) as res:
            self.session = res.headers.get('Mcp-Session-Id') or self.session
            payload = res.read().decode()
        if not payload.strip(): return {}
        if payload.startswith('event:') or payload.startswith('data:'):
            payload = '\n'.join(line[5:].strip() for line in payload.splitlines() if line.startswith('data:'))
        result = json.loads(payload)
        if 'error' in result: raise RuntimeError(result['error'])
        return result.get('result', {})

    def call(self, name, args):
        return self.rpc('tools/call', {'name':name,'arguments':args})

def compact(value):
    if isinstance(value,dict):
        return {k: ('<image>' if k=='data' and value.get('type')=='image' else compact(v)) for k,v in value.items()}
    if isinstance(value,list): return [compact(v) for v in value]
    return value

if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    result = Editor().call(request['name'], request.get('arguments',{}))
    print(json.dumps(compact(result), ensure_ascii=False, indent=2))
