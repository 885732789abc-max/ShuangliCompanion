from __future__ import annotations

from pathlib import Path

from .config import DATA

HOST = 'com.shuangli.conversation_bridge'
KEYS = [rf'Software\Google\Chrome\NativeMessagingHosts\{HOST}',
        rf'Software\Microsoft\Edge\NativeMessagingHosts\{HOST}']


def uninstall_host():
    """Remove only this installation's legacy browser host registration."""
    import winreg
    for path in KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as key:
                current=winreg.QueryValue(key,'')
            if Path(current).resolve()==(DATA/'native-host.json').resolve():
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
        except FileNotFoundError: pass
    (DATA/'native-host.json').unlink(missing_ok=True)
