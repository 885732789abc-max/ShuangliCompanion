"""Credential-free native transport. The only secret is a local pairing key."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import socket
import struct
from ctypes import wintypes

MAX_MESSAGE = 900_000


def dpapi(data: bytes, decrypt=False):
    class BLOB(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    inp = BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out = BLOB()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 1, ctypes.byref(out))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(inp), 'Shuangli local bridge', None, None, None, 1, ctypes.byref(out))
    if not ok: raise ctypes.WinError(ctypes.get_last_error())
    try: return ctypes.string_at(out.data, out.size)
    finally:
        kernel = ctypes.WinDLL('kernel32'); kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(out.data)


def protect(value):
    return base64.b64encode(dpapi(value.encode())).decode()


def unprotect(value):
    return dpapi(base64.b64decode(value), True).decode()


def encode(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',',':')).encode('utf-8')
    if len(raw) > MAX_MESSAGE: raise ValueError('message too large')
    return struct.pack('<I',len(raw)) + raw


def read_exact(stream, length):
    result = bytearray()
    while len(result) < length:
        chunk = stream.read(length-len(result))
        if not chunk: raise EOFError()
        result.extend(chunk)
    return bytes(result)


def read_message(stream):
    length, = struct.unpack('<I',read_exact(stream,4))
    if length < 2 or length > MAX_MESSAGE: raise ValueError('invalid message length')
    value = json.loads(read_exact(stream,length))
    if not isinstance(value,dict): raise ValueError('invalid message')
    return value
