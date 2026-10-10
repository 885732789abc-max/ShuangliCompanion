"""Chrome / Edge Native Messaging host. Stdout is exclusively framed JSON."""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from shuangli.transport import encode, read_message, unprotect


def main():
    if sys.platform == 'win32':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(),os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(),os.O_BINARY)
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    session=json.loads((root/'data/bridge-session.json').read_text(encoding='utf-8'))
    origin=next((arg for arg in sys.argv[1:] if arg.startswith('chrome-extension://')),'')
    if origin != session['origin']: return
    port=int(session['port'])
    if not 1024 <= port <= 65535: return
    client=socket.create_connection(('127.0.0.1',port),timeout=5)
    client.settimeout(None)
    client.sendall(encode(dict(type='hello',origin=origin,key=unprotect(session['pairing_key']))))
    def from_browser():
        try:
            while True: client.sendall(encode(read_message(sys.stdin.buffer)))
        except (EOFError,OSError,ValueError):
            try: client.shutdown(socket.SHUT_RDWR)
            except OSError: pass
    threading.Thread(target=from_browser,daemon=True).start()
    try:
        with client.makefile('rb') as stream:
            while True:
                value=read_message(stream)
                sys.stdout.buffer.write(encode(value)); sys.stdout.buffer.flush()
    except (EOFError,OSError,ValueError): pass
    finally: client.close()


if __name__ == '__main__':
    try: main()
    except Exception: sys.exit(1)
