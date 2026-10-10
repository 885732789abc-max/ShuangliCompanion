from __future__ import annotations

import ctypes
import logging
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QPoint, QRect
from PySide6.QtGui import QGuiApplication

IS_WIN = sys.platform == 'win32'
class _MemoryStatus(ctypes.Structure):
    _fields_ = [('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(key,ctypes.c_ulonglong) for key in
        ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]

def available_memory_mb():
    if not IS_WIN:return 99999
    status=_MemoryStatus();status.length=ctypes.sizeof(status)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return status.available//1048576
    return 99999


def input_idle_seconds():
    if not IS_WIN:
        return None
    class LastInput(ctypes.Structure):
        _fields_ = [('size', wintypes.UINT), ('tick', wintypes.DWORD)]
    info = LastInput();info.size = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    # Both counters are DWORDs. Unsigned subtraction survives tick rollover.
    return ((ctypes.windll.kernel32.GetTickCount() - info.tick) & 0xffffffff) / 1000.0

if IS_WIN:
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    dwm = ctypes.WinDLL('dwmapi')
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


def click_through(widget, enabled):
    if not IS_WIN: return
    hwnd = int(widget.winId())
    ex = user32.GetWindowLongW(hwnd, -20)
    user32.SetWindowLongW(hwnd, -20, ex | 0x20 if enabled else ex & ~0x20)


def native_to_logical(rect):
    # Windows coordinates are physical. Qt's per-monitor windows use logical pixels.
    for screen in QGuiApplication.screens():
        g, ratio = screen.geometry(), screen.devicePixelRatio()
        # Match via Windows monitor geometry, rather than scaling the virtual origin.
        name = screen.name()
        info = monitor_rects().get(name)
        if info and info[0] <= rect.left < info[2] and info[1] <= rect.top < info[3]:
            return QRect(round(g.x() + (rect.left-info[0])/ratio),
                         round(g.y() + (rect.top-info[1])/ratio),
                         round((rect.right-rect.left)/ratio),
                         round((rect.bottom-rect.top)/ratio))
    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen else 1
    return QRect(round(rect.left/ratio), round(rect.top/ratio),
                 round((rect.right-rect.left)/ratio), round((rect.bottom-rect.top)/ratio))


_monitor_cache={}
_monitor_until=0.0

def monitor_rects():
    global _monitor_cache,_monitor_until
    if not IS_WIN: return {}
    now=time.monotonic()
    if now<_monitor_until:return _monitor_cache
    class INFO(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                    ('work', wintypes.RECT), ('flags', wintypes.DWORD),
                    ('device', wintypes.WCHAR * 32)]
    result = {}
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                 ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def visit(handle, _dc, _rect, _data):
        info = INFO(); info.size = ctypes.sizeof(INFO)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.monitor
            result[info.device] = (r.left, r.top, r.right, r.bottom)
        return True
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.EnumDisplayMonitors(None, None, callback(visit), 0)
    _monitor_cache=result;_monitor_until=now+2.0
    return result


def window_rect(hwnd, own_pid):
    if not IS_WIN or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == own_pid: return None
    cloaked = wintypes.DWORD()
    if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 and cloaked.value:
        return None
    # Tool and popup windows are unsuitable platforms. No titles are read.
    if user32.GetWindowLongW(hwnd, -20) & 0x80: return None
    class_name = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, class_name, 128)
    if class_name.value in ('Shell_TrayWnd', 'Shell_SecondaryTrayWnd', 'Progman', 'WorkerW'):
        return None
    rect = wintypes.RECT()
    if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)): return None
    logical = native_to_logical(rect)
    return logical if logical.width() > 180 and logical.height() > 80 else None


def platforms(own_pid):
    if not IS_WIN: return []
    result = []
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        rect = window_rect(hwnd, own_pid)
        if rect: result.append((hwnd, rect))
        return len(result) < 64
    user32.EnumWindows(callback(visit), 0)
    return result


def startup(enabled, executable):
    if not IS_WIN: return
    import winreg
    path = r'Software\Microsoft\Windows\CurrentVersion\Run'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        if enabled:
            winreg.SetValueEx(key, 'ShuangliCompanion', 0, winreg.REG_SZ,
                             f'"{Path(executable).resolve()}"')
        else:
            try: winreg.DeleteValue(key, 'ShuangliCompanion')
            except FileNotFoundError: pass


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, callbacks):
        super().__init__()
        self.callbacks = callbacks
        self.registered = []

    def configure(self, show, chat):
        self.close()
        errors = []
        for i, text in enumerate((show, chat), 4101):
            parts = text.upper().replace(' ', '').split('+')
            mods = 0x4000
            codes = {'ALT':1, 'CTRL':2, 'SHIFT':4, 'WIN':8}
            for part in parts[:-1]: mods |= codes.get(part, 0)
            last = parts[-1]
            vk = ord(last) if len(last) == 1 and last.isalnum() else (111+int(last[1:]) if re.fullmatch(r'F([1-9]|1[0-2])',last) else 0)
            if not vk or (IS_WIN and not user32.RegisterHotKey(None, i, mods, vk)):
                errors.append(text)
            else: self.registered.append(i)
        return errors

    def nativeEventFilter(self, _type, message):
        if IS_WIN:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.registered:
                self.callbacks[msg.wParam-4101]()
                return True, 0
        return False, 0

    def close(self):
        if IS_WIN:
            for ident in self.registered: user32.UnregisterHotKey(None, ident)
        self.registered.clear()
