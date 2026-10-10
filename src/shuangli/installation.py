from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .config import DATA, HOME, atomic_json

HOST = 'com.shuangli.conversation_bridge'
KEYS = [rf'Software\Google\Chrome\NativeMessagingHosts\{HOST}',
        rf'Software\Microsoft\Edge\NativeMessagingHosts\{HOST}']


def install_host(extension_id):
    if not re.fullmatch('[a-p]{32}',extension_id):
        raise ValueError('扩展编号应是浏览器扩展页显示的 32 个小写字母。')
    host=HOME/'ShuangliBridgeHost.exe'
    if not host.exists(): raise ValueError('请在打包后的程序中登记桥接，霜璃还需要本地 Host 程序。')
    manifest=DATA/'native-host.json'
    atomic_json(manifest,dict(name=HOST, description='Shuangli authorized conversation bridge',
                    path=str(host.resolve()),type='stdio',
                    allowed_origins=[f'chrome-extension://{extension_id}/']))
    import winreg
    for path in KEYS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key:
            winreg.SetValueEx(key,'',0,winreg.REG_SZ,str(manifest.resolve()))
    return manifest


def uninstall_host():
    import winreg
    for path in KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as key:
                current=winreg.QueryValue(key,'')
            if Path(current).resolve()==(DATA/'native-host.json').resolve():
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
        except FileNotFoundError: pass
    (DATA/'native-host.json').unlink(missing_ok=True)
